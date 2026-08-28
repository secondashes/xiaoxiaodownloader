@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  打包 Python 后端为内置 exe（bunkr_bridge）
echo ============================================
echo.
echo 需已安装 Python + PyInstaller（pip install pyinstaller）
echo 修改 gui_bridge.py 后，重新运行本脚本，
echo 再压缩整个文件夹分享，对方无需安装 Python。
echo.
python -m PyInstaller gui_bridge.spec --noconfirm --clean
if errorlevel 1 (
  echo.
  echo [失败] 打包出错，请检查上方日志
  pause
  exit /b 1
)
echo.
echo 正在替换根目录 bunkr_bridge ...
if exist bunkr_bridge_old rd /s /q bunkr_bridge_old
if exist bunkr_bridge ren bunkr_bridge bunkr_bridge_old
xcopy /e /i /y dist\bunkr_bridge bunkr_bridge >nul
if exist bunkr_bridge_old rd /s /q bunkr_bridge_old
echo.
echo [完成] 已生成 bunkr_bridge\bunkr_bridge.exe
echo 压缩整个文件夹分享即可，对方无需安装 Python。
pause
