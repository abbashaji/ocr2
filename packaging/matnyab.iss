; Inno Setup 6 script for MatnYab. Compile with ISCC (see packaging/build_windows.ps1):
;   ISCC.exe /DAppVersion=0.1.0 [/DBundleDir=..\dist\MatnYab] [/DOutputDir=..\dist] [/DWithFarsi=1] packaging\matnyab.iss
; Paths below are relative to this file ({#SourcePath}); nothing machine specific.

#ifndef AppVersion
  #error AppVersion is not defined. Pass /DAppVersion=<version from src/matnyab/__init__.py>.
#endif
#ifndef BundleDir
  #define BundleDir SourcePath + "..\dist\MatnYab"
#endif
#ifndef OutputDir
  #define OutputDir SourcePath + "..\dist"
#endif

#define AppName "MatnYab"
#define AppExe "MatnYab.exe"

[Setup]
; Fixed forever: changing it makes Windows treat an upgrade as a different program.
AppId={{D8D1D334-3C8A-411E-9B5D-99D1870994A0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=MatnYab
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default; the dialog lets the user choose all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=MatnYab-Setup-{#AppVersion}
SetupIconFile={#SourcePath}matnyab.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; No file association is registered on purpose.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
#ifdef WithFarsi
; Farsi.isl is downloaded next to this script by build_windows.ps1; best effort.
Name: "farsi"; MessagesFile: "{#SourcePath}Farsi.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
