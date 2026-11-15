# -*- mode: python ; coding: utf-8 -*-
# Windows IPC worker only (no Tk UI). Consumed by WinUI shell.
import sys
from pathlib import Path
root = Path(SPECPATH)
sys.path.insert(0, str(root))
a = Analysis(
    [str(root / "core_worker.py")],
    pathex=[str(root)],
    datas=[(str(root / "docs/icon-1024.png"), "docs")],
    hiddenimports=[],
    excludes=["tkinter", "pystray", "mac", "windows.main", "windows.tray", "PIL._tkinter_finder", "AppKit", "Foundation", "objc"],
    noarchive=False,
)
pyz = PYZ(a.pure)
# console=True so redirected stdio IPC is reliable under Wine/Windows;
# WinUI parent starts us with CreateNoWindow=true (no console flash).
_icon = root / "build/GoldTicker.ico"
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="GoldTicker.Core",
    console=True,
    icon=str(_icon) if _icon.exists() else None,
)
