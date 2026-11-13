# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
root = Path(SPECPATH)
sys.path.insert(0, str(root))
from core.product import VERSION
mac = sys.platform == "darwin"
a = Analysis([str(root / "goldticker.py")], pathex=[str(root)],
    datas=[(str(root / "docs/icon-1024.png"), "docs")],
    hiddenimports=["mac.main", "PyObjCTools.AppHelper"] if mac else ["windows.main", "pystray._win32", "PIL._tkinter_finder"],
    excludes=["windows", "tkinter", "pystray"] if mac else ["mac", "AppKit", "Foundation", "objc", "PyObjCTools"],
    noarchive=False)
pyz = PYZ(a.pure)
if mac:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="GoldTicker", console=False,
              icon=str(root / "build/AppIcon.icns"), target_arch=None)
    coll = COLLECT(exe, a.binaries, a.datas, name="GoldTicker")
    app = BUNDLE(coll, name="GoldTicker.app", icon=str(root / "build/AppIcon.icns"),
        bundle_identifier="com.superj.goldticker", version=VERSION,
        info_plist={"LSUIElement": True, "NSHighResolutionCapable": True,
                    "CFBundleShortVersionString": VERSION})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="GoldTicker", console=False,
              icon=str(root / "build/GoldTicker.ico"), version=str(root / "windows/version.txt"), upx=False)
