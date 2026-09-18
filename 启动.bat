@echo off
rem Build frontend then launch Electron (pure ASCII to avoid codepage issues)
cd /d "%~dp0\gui"
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found in PATH. Install Node.js first.
  pause
  exit /b 1
)
echo [1/2] Building frontend...
call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed. See messages above.
  pause
  exit /b 1
)
if not exist "node_modules\electron\dist\electron.exe" (
  echo [ERROR] electron.exe not found. Run: npm install
  pause
  exit /b 1
)
echo [1.5/2] Refreshing code map...
python _gen_code_map.py >nul 2>nul
echo [2/2] Starting Electron...
start "" "node_modules\electron\dist\electron.exe" .
exit /b 0
