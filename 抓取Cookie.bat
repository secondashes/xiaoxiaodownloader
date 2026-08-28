@echo off
chcp 65001 >nul
title Cookie 一键抓取
cd /d "%~dp0"

REM 自动请求管理员权限（Chrome 127+ 新版加密需要，用于解密 Cookie）
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限解密 Chrome 新版 Cookie，请在弹出的窗口中点击"是"...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

REM 优先找已安装的 Python（排除 Windows 商店假 python）
set "PYCMD="
where python 2>nul | findstr /v /i "WindowsApps" > "%TEMP%\_pyfind.txt"
for /f "usebackq delims=" %%i in (`type "%TEMP%\_pyfind.txt" 2^>nul`) do (
    if not defined PYCMD set "PYCMD=%%i"
)
del "%TEMP%\_pyfind.txt" 2>nul

if not defined PYCMD (
    echo [错误] 未找到 Python！请安装 Python 3.10+ 并勾选 Add to PATH。
    pause
    exit /b 1
)

"%PYCMD%" -X utf8 fetch_cookies.py
set EXITCODE=%ERRORLEVEL%

echo.
pause
exit /b %EXITCODE%
