"""Write the Windows "Details" tab of the exe (version, author, copyright) for PyInstaller --version-file."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usb_fixer import about  # noqa: E402

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', {author!r}),
      StringStruct('FileDescription', {desc!r}),
      StringStruct('FileVersion', {version!r}),
      StringStruct('InternalName', 'USB-Fixer'),
      StringStruct('LegalCopyright', {copyright!r}),
      StringStruct('OriginalFilename', 'USB-Fixer.exe'),
      StringStruct('ProductName', {name!r}),
      StringStruct('ProductVersion', {version!r}),
      StringStruct('Comments', {comments!r})])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def numbers(version: str) -> tuple:
    parts = [int(p) for p in version.split(".") if p.isdigit()][:4]
    return tuple(parts + [0] * (4 - len(parts)))


def render() -> str:
    return TEMPLATE.format(
        nums=numbers(about.VERSION),
        author=about.AUTHOR_EN,
        desc=f"{about.APP_NAME} - diagnose and fix USB problems",
        version=about.VERSION,
        copyright=f"Copyright (c) 2026 {about.AUTHOR_EN} - {about.GITHUB_PROFILE}",
        name=about.APP_NAME,
        comments=about.GITHUB_REPO,
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "version_info.txt"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render())
    print(f"{out}: {about.APP_NAME} {about.VERSION} by {about.AUTHOR_EN}")
