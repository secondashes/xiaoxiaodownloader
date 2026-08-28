# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 把 patch_runtime.py + update/ 文件夹打包为单文件"补丁.exe"
# 使用方式: pyinstaller patch_runtime.spec --noconfirm --clean
#
# 产物: dist/patch_runtime/patch_runtime.exe（单文件）
# 用户使用: 把 patch_runtime.exe 放到本体目录（与 小小下载器/ 文件夹同级）双击

import os

block_cipher = None

a = Analysis(
    ['patch_runtime.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        # 内嵌本次全部改动文件：update/ 整体打包到 _MEIPASS/update/
        # 运行时遍历 update/ → 复制到本体目录同名相对路径
        ('update', 'update'),
    ],
    hiddenimports=[
        # Tkinter GUI（PyInstaller 默认会自动检测，但显式声明更稳妥）
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        # _tkinter 是 C 扩展，PyInstaller 会自动收集 tcl/tk 数据
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='补丁',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # 无控制台黑框（用 Tkinter GUI 显示进度）
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # 单文件自解压模式（运行时解压到 sys._MEIPASS 临时目录）
    onefile=True,
)
