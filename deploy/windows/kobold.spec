# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: the `kobold` command as a one-folder Windows program.

    uv sync
    uv run --with pyinstaller pyinstaller --noconfirm deploy/windows/kobold.spec
    # -> dist/kobold/kobold.exe (+ _internal/)

One folder rather than one file: a one-file exe unpacks itself to a temp
directory on every start, which is slow and what antivirus heuristics dislike
most. The Inno Setup script in this directory wraps the folder into
KleverKoboldSetup.exe. The same recipe freezes on Linux and macOS for a smoke
test; only the icon is Windows-specific.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

here = Path(SPECPATH)  # noqa: F821 -- a PyInstaller global

a = Analysis(  # noqa: F821
    [str(here / "launcher.py")],
    pathex=[],
    binaries=[],
    # The two fonts the page embeds, and build_info.json when the workflow wrote one.
    datas=collect_data_files("kleverkobold"),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "_tkinter", "pydoc_data", "test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kobold",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=[str(here.parent / "icon" / "kobold.ico")] if sys.platform == "win32" else None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="kobold",
)
