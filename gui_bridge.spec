# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 将 gui_bridge.py 打包为 exe
# 使用方式: pyinstaller gui_bridge.spec

import os

# pydivert（手动抓取透明重定向）：WinDivert 驱动+DLL 是包内二进制，PyInstaller 无 hook，手动带上
import pydivert as _pydivert_mod
_winivert_dir = os.path.join(os.path.dirname(_pydivert_mod.__file__), 'windivert_dll')

block_cipher = None

a = Analysis(
    ['gui_bridge.py'],
    pathex=[os.path.abspath('.'), os.path.abspath('_pylibs')],
    binaries=[
        # BT 下载内核（磁力/.torrent，bridge/bt_downloader.py RPC 调用；运行时 _MEIPASS/aria2/ 定位）
        (os.path.join('resources', 'aria2', 'aria2c.exe'), os.path.join('aria2')),
    ],
    datas=[
        # 打包 src 目录
        ('src', 'src'),
        # WinDivert 驱动（WinDivert64.sys/.dll）
        (_winivert_dir, os.path.join('pydivert', 'windivert_dll')),
    ],
    hiddenimports=[
        'bs4',
        'requests',
        'rich',
        'aiohttp',
        'tomllib',
        'curl_cffi',
        'curl_cffi.requests',
        # Pixiv 小说 word 下载（download_manager 函数内 import，显式声明防漏）
        'docx',
        'docx.oxml',
        'docx.oxml.ns',
        'docx.oxml.shared',
        # 手动抓取 mitm 代理（sniffer_proxy.py 动态 TLS 证书签发）
        'cryptography',
        'cryptography.x509',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.asymmetric',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.backends',
        # 流媒体 AES-128 分片解密（webcapture.py 函数内 import，显式声明防漏）
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.ciphers.algorithms',
        'cryptography.hazmat.primitives.ciphers.modes',
        # 手动抓取透明重定向（QQ/微信等不走系统代理的应用）
        'pydivert',
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
