"""Generate the Windows version resource (PyInstaller ``version=`` file).

Usage: python packaging/make_version_info.py OUT_FILE [VERSION]
The version defaults to ``__version__`` read from src/matnyab/__init__.py.
Pure standard library; imported by matnyab.spec and runnable on its own.
"""

from __future__ import annotations

import os
import re
import sys

COMPANY = "MatnYab"
DESCRIPTION = "MatnYab - offline Persian image-to-text"
COPYRIGHT = "MatnYab"


def read_version(init_file: str) -> str:
    with open(init_file, "r", encoding="utf-8") as handle:
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', handle.read(), re.M)
    if not match:
        raise ValueError("no __version__ in %s" % init_file)
    return match.group(1)


def version_tuple(version: str):
    nums = [int(x) for x in re.findall(r"\d+", version)[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def render(version: str) -> str:
    tup = version_tuple(version)
    dotted = ".".join(str(n) for n in tup)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tup!r},
    prodvers={tup!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{COMPANY}'),
         StringStruct('FileDescription', '{DESCRIPTION}'),
         StringStruct('FileVersion', '{dotted}'),
         StringStruct('InternalName', 'MatnYab'),
         StringStruct('LegalCopyright', '{COPYRIGHT}'),
         StringStruct('OriginalFilename', 'MatnYab.exe'),
         StringStruct('ProductName', 'MatnYab'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write(path: str, version: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(version))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    init = os.path.join(here, "..", "src", "matnyab", "__init__.py")
    ver = sys.argv[2] if len(sys.argv) > 2 else read_version(init)
    write(sys.argv[1], ver)
