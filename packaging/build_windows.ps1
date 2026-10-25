<#
.SYNOPSIS
  Builds the MatnYab Windows bundle, portable zip and installer.

.DESCRIPTION
  Stages: venv, pip install, tesseract, pyinstaller, size report, portable zip,
  inno setup. Run from anywhere; paths are resolved from this script's folder.
  Exits non-zero on the first failure after printing a summary block.
  Outputs (in <repo>\dist):
    MatnYab\                        the onedir bundle
    MatnYab-<version>-portable.zip
    MatnYab-Setup-<version>.exe
    build-summary.json              machine-readable summary (used by the workflow)
    size-report.txt

.PARAMETER Version
  Product version. Default: __version__ from src\matnyab\__init__.py.
.PARAMETER Python
  Python used to create the build venv (default: python).
.PARAMETER TesseractDir
  Folder holding tesseract.exe. Default: auto-detect, else choco install tesseract.
.PARAMETER SkipInstaller
  Build the bundle and the portable zip only.
#>
param(
    [string]$Version = "",
    [string]$Python = "python",
    [string]$TesseractDir = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build\pyi"
$Venv = Join-Path $Root ".venv"
$Bundle = Join-Path $Dist "MatnYab"
$TargetSizeMB = 120

$script:Stages = [ordered]@{}
$script:Summary = [ordered]@{
    ok = $false
    version = ""
    tesseract_version = ""
    tesseract_dir = ""
    bundle_mb = 0
    bundle_files = 0
    portable_zip = ""
    portable_mb = 0
    installer = ""
    installer_mb = 0
    installer_language = "english"
    warnings = @()
    error = ""
}

function Write-Step([string]$Name) { Write-Host ""; Write-Host "=== $Name ===" }

function Invoke-Native([string]$Exe, [string[]]$Arguments) {
    # Runs a native command and throws on a non-zero exit code.
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Invoke-Retry([scriptblock]$Action, [int]$Attempts = 3, [int]$DelaySeconds = 10) {
    for ($i = 1; $i -le $Attempts; $i++) {
        try { & $Action; return } catch {
            Write-Host "Attempt $i of $Attempts failed: $($_.Exception.Message)"
            if ($i -eq $Attempts) { throw }
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Measure-Stage([string]$Name, [scriptblock]$Body) {
    Write-Step $Name
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try { & $Body } finally {
        $sw.Stop()
        $script:Stages[$Name] = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    }
}

function Get-DirSizeMB([string]$Path) {
    $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File | Measure-Object -Property Length -Sum).Sum
    return [math]::Round($sum / 1MB, 1)
}

function Find-Tesseract {
    if ($TesseractDir -ne "") {
        $candidate = Join-Path $TesseractDir "tesseract.exe"
        if (Test-Path $candidate) { return $candidate }
        throw "tesseract.exe not found in -TesseractDir '$TesseractDir'"
    }
    if ($env:MATNYAB_TESSERACT -and (Test-Path $env:MATNYAB_TESSERACT)) { return $env:MATNYAB_TESSERACT }
    $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in @("$env:ProgramFiles\Tesseract-OCR", "${env:ProgramFiles(x86)}\Tesseract-OCR")) {
        $candidate = Join-Path $dir "tesseract.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Find-Iscc {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in @("${env:ProgramFiles(x86)}\Inno Setup 6", "$env:ProgramFiles\Inno Setup 6",
                       "$env:LOCALAPPDATA\Programs\Inno Setup 6")) {
        $candidate = Join-Path $dir "ISCC.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

try {
    $total = [System.Diagnostics.Stopwatch]::StartNew()
    Set-Location $Root

    # ---- version -----------------------------------------------------------
    if ($Version -eq "") {
        $init = Get-Content (Join-Path $Root "src\matnyab\__init__.py") -Raw
        if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { throw "__version__ not found in src\matnyab\__init__.py" }
        $Version = $Matches[1]
    }
    $script:Summary.version = $Version
    Write-Host "MatnYab $Version, root $Root"

    # ---- stage 1: venv -----------------------------------------------------
    Measure-Stage "venv" {
        if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
            Invoke-Native $Python @("-m", "venv", $Venv)
        }
    }
    $Py = Join-Path $Venv "Scripts\python.exe"

    # ---- stage 2: pip install ----------------------------------------------
    Measure-Stage "pip install" {
        Invoke-Retry { Invoke-Native $Py @("-m", "pip", "install", "--upgrade", "pip") }
        Invoke-Retry { Invoke-Native $Py @("-m", "pip", "install", "-e", ".[build]") }
    }

    # ---- stage 3: tesseract ------------------------------------------------
    Measure-Stage "tesseract" {
        $exe = Find-Tesseract
        if (-not $exe) {
            if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
                throw "tesseract not found and chocolatey is not available. Install Tesseract 5 (UB Mannheim build) or pass -TesseractDir."
            }
            Invoke-Retry { Invoke-Native "choco" @("install", "tesseract", "-y", "--no-progress") } 3 15
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
            $exe = Find-Tesseract
            if (-not $exe) { throw "tesseract.exe not found after choco install" }
        }
        $exe = (Resolve-Path $exe).Path
        $prev = $ErrorActionPreference
        $ErrorActionPreference = "Continue"   # tesseract may print its version on stderr
        $line = (& $exe --version 2>&1 | Select-Object -First 1)
        $ErrorActionPreference = $prev
        if ("$line" -notmatch 'tesseract\s+v?(\d+)\.(\d+)') { throw "cannot parse tesseract version from: $line" }
        if ([int]$Matches[1] -lt 5) { throw "tesseract >= 5.0 is required, found: $line" }
        $script:Summary.tesseract_version = ("$line").Trim()
        $script:Summary.tesseract_dir = Split-Path $exe -Parent
        $env:MATNYAB_TESSERACT = $exe
        Write-Host "Using $exe ($($script:Summary.tesseract_version))"
    }

    # ---- stage 4: pyinstaller ----------------------------------------------
    Measure-Stage "pyinstaller" {
        if (Test-Path $Bundle) { Remove-Item -LiteralPath $Bundle -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $Dist | Out-Null
        # The spec copies tesseract.exe + its DLLs (never tessdata) from the folder of
        # MATNYAB_TESSERACT into _internal\tesseract, which is where paths.tesseract_cmd() looks.
        Invoke-Native $Py @("-m", "PyInstaller", "packaging\matnyab.spec", "--noconfirm", "--clean",
                            "--workpath", $Work, "--distpath", $Dist)
        $required = @("MatnYab.exe", "matnyab-cli.exe", "_internal\model\fas.traineddata",
                      "_internal\assets\fonts", "_internal\samples\client_clean.png",
                      "_internal\samples\client_ref.txt", "_internal\tesseract\tesseract.exe")
        foreach ($rel in $required) {
            if (-not (Test-Path (Join-Path $Bundle $rel))) { throw "bundle is missing $rel" }
        }
    }

    # ---- stage 5: size report ----------------------------------------------
    Measure-Stage "size report" {
        $files = Get-ChildItem -LiteralPath $Bundle -Recurse -File
        $script:Summary.bundle_files = @($files).Count
        $script:Summary.bundle_mb = Get-DirSizeMB $Bundle
        $lines = @("Bundle: $($script:Summary.bundle_mb) MB in $($script:Summary.bundle_files) files (target <= $TargetSizeMB MB)", "", "Top-level folders and files by size (MB):")
        $top = Get-ChildItem -LiteralPath (Join-Path $Bundle "_internal") | ForEach-Object {
            if ($_.PSIsContainer) { [pscustomobject]@{ Name = $_.Name; MB = Get-DirSizeMB $_.FullName } }
            else { [pscustomobject]@{ Name = $_.Name; MB = [math]::Round($_.Length / 1MB, 1) } }
        } | Sort-Object MB -Descending | Select-Object -First 15
        $lines += ($top | ForEach-Object { "{0,8}  {1}" -f $_.MB, $_.Name })
        $lines | Set-Content -Encoding ASCII (Join-Path $Dist "size-report.txt")
        $lines | ForEach-Object { Write-Host $_ }
        if ($script:Summary.bundle_mb -gt $TargetSizeMB) {
            $script:Summary.warnings += "bundle is $($script:Summary.bundle_mb) MB, above the $TargetSizeMB MB target"
            Write-Host "WARNING: $($script:Summary.warnings[-1])"
        }
    }

    # ---- stage 6: portable zip ---------------------------------------------
    Measure-Stage "portable zip" {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = Join-Path $Dist "MatnYab-$Version-portable.zip"
        if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
        # includeBaseDirectory = $true: the archive holds one top-level folder MatnYab\.
        [System.IO.Compression.ZipFile]::CreateFromDirectory($Bundle, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)
        $script:Summary.portable_zip = $zip
        $script:Summary.portable_mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
        Write-Host "$zip ($($script:Summary.portable_mb) MB)"
    }

    # ---- stage 7: inno setup -----------------------------------------------
    if ($SkipInstaller) {
        Write-Host "Skipping the installer (-SkipInstaller)."
    } else {
        Measure-Stage "inno setup" {
            $iscc = Find-Iscc
            if (-not $iscc) {
                if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { throw "Inno Setup 6 not found and chocolatey is not available" }
                Invoke-Retry { Invoke-Native "choco" @("install", "innosetup", "-y", "--no-progress") } 3 15
                $iscc = Find-Iscc
                if (-not $iscc) { throw "ISCC.exe not found after choco install innosetup" }
            }

            # Persian wizard text is best effort: try to fetch Farsi.isl, never fail the build for it.
            $farsi = Join-Path $PSScriptRoot "Farsi.isl"
            $haveFarsi = $false
            try {
                Invoke-Retry {
                    Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -OutFile $farsi `
                        -Uri "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/Unofficial/Farsi.isl"
                } 3 5
                $haveFarsi = (Test-Path $farsi) -and ((Get-Item $farsi).Length -gt 1000)
            } catch { Write-Host "Farsi.isl download failed, using the English wizard: $($_.Exception.Message)" }

            $issArgs = @("/Qp", "/DAppVersion=$Version", "/DBundleDir=$Bundle", "/DOutputDir=$Dist")
            $issFile = Join-Path $PSScriptRoot "matnyab.iss"
            $built = $false
            if ($haveFarsi) {
                & $iscc @issArgs "/DWithFarsi=1" $issFile
                if ($LASTEXITCODE -eq 0) { $built = $true; $script:Summary.installer_language = "english+farsi" }
                else {
                    $script:Summary.warnings += "ISCC failed with Farsi.isl (exit $LASTEXITCODE); rebuilt with the English wizard"
                    Write-Host "WARNING: $($script:Summary.warnings[-1])"
                }
            }
            if (-not $built) { Invoke-Native $iscc ($issArgs + @($issFile)) }
            if (Test-Path $farsi) { Remove-Item -LiteralPath $farsi -Force }

            $setup = Join-Path $Dist "MatnYab-Setup-$Version.exe"
            if (-not (Test-Path $setup)) { throw "installer not found: $setup" }
            $script:Summary.installer = $setup
            $script:Summary.installer_mb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
            Write-Host "$setup ($($script:Summary.installer_mb) MB)"
        }
    }

    $total.Stop()
    $script:Summary.ok = $true
    $script:Summary["total_seconds"] = [math]::Round($total.Elapsed.TotalSeconds, 1)
}
catch {
    $script:Summary.ok = $false
    $script:Summary.error = $_.Exception.Message
    Write-Host "BUILD FAILED: $($_.Exception.Message)"
}
finally {
    $script:Summary["stages_seconds"] = $script:Stages
    if (Test-Path $Dist) {
        $script:Summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Dist "build-summary.json")
    }
    Write-Host ""
    Write-Host "================ MatnYab build summary ================"
    Write-Host ("Result            : " + $(if ($script:Summary.ok) { "OK" } else { "FAILED" }))
    Write-Host "Version           : $($script:Summary.version)"
    Write-Host "Tesseract         : $($script:Summary.tesseract_version)"
    Write-Host "Bundle            : $($script:Summary.bundle_mb) MB, $($script:Summary.bundle_files) files"
    Write-Host "Portable zip      : $($script:Summary.portable_zip) ($($script:Summary.portable_mb) MB)"
    Write-Host "Installer         : $($script:Summary.installer) ($($script:Summary.installer_mb) MB, $($script:Summary.installer_language))"
    foreach ($w in $script:Summary.warnings) { Write-Host "Warning           : $w" }
    foreach ($k in $script:Stages.Keys) { Write-Host ("Stage {0,-12}: {1} s" -f $k, $script:Stages[$k]) }
    if ($script:Summary.error) { Write-Host "Error             : $($script:Summary.error)" }
    Write-Host "======================================================="
}
if (-not $script:Summary.ok) { exit 1 }
