# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 将 gui_bridge.py 打包为 exe
# 使用方式: pyinstaller gui_bridge.spec

import os

block_cipher = None

a = Analysis(
    ['gui_bridge.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        # 打包 src 目录
        ('src', 'src'),
    ],
    hiddenimports=[
        'bs4',
        'requests',
        'rich',
        'aiohttp',
        'tomllib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='bunkr_bridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 需要 stdin/stdout 通信；窗口由 Electron windowsHide 隐藏
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='bunkr_bridge',
)
