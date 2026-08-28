@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ========================================
echo   BunkrDownloader 一键打包脚本
echo ========================================
echo.

REM 1. 打包 Python 后端（含所有 Python 依赖）
echo [1/3] 打包 Python 后端...
python -m pip install pyinstaller --quiet 2>nul
python -m PyInstaller gui_bridge.spec --noconfirm --clean
if errorlevel 1 (
    echo [错误] Python 后端打包失败！
    pause
    exit /b 1
)
echo        Python 后端打包完成
echo.

REM 2. 复制后端到项目根目录（供 electron-builder 引用）
echo [2/3] 整理后端目录...
if exist "bunkr_bridge" rmdir /s /q "bunkr_bridge"
xcopy /e /i /q "dist\bunkr_bridge" "bunkr_bridge"
echo        后端目录就绪
echo.

REM 3. 打包 Electron 应用（含前端 + 后端）
echo [3/3] 打包 Electron 应用...
cd gui
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
set ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
call npm install
call npx electron-builder --win portable
if errorlevel 1 (
    echo [错误] Electron 打包失败！
    pause
    exit /b 1
)
cd ..

echo.
echo ========================================
echo   打包完成！输出目录: gui\release\
echo ========================================
echo.
pause
