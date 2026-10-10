"""Genera el recurso de version de Windows que PyInstaller incrusta en el .exe."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    version = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    destination = Path(sys.argv[2])
    parts = [int(piece) for piece in version.split(".")]
    if len(parts) != 3 or any(piece < 0 for piece in parts):
        raise SystemExit("VERSION debe tener el formato MAJOR.MINOR.PATCH")

    filevers = (parts[0], parts[1], parts[2], 0)
    original = f"YouTubeDownloader-{version}.exe"
    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={filevers},
    mask=0x3F,
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
        [
          StringStruct('CompanyName', 'edokope4'),
          StringStruct('FileDescription', 'Descargador de videos de YouTube'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'YouTubeDownloader'),
          StringStruct('OriginalFilename', '{original}'),
          StringStruct('ProductName', 'YouTube Downloader'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
