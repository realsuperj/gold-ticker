# -*- mode: python ; coding: utf-8 -*-
# GoldTicker Windows PyInstaller Spec
# 生成单文件夹可执行包，便于调试；如需 --onefile 改 EXE 的 console=False 即可

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['windows/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('core', 'core'),
        ('windows', 'windows'),
        ('windows/version.txt', '.'),
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'pystray._win32',
        'pystray._base',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'pkgutil',
        'urllib.request',
        'urllib.error',
        'json',
        'threading',
        'queue',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['AppKit', 'objc', 'Foundation', 'Quartz', 'PyObjCTools'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GoldTicker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='build/GoldTicker.ico',
)
