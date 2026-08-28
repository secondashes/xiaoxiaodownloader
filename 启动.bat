@echo off
cd /d "%~dp0\gui"
start "" "node_modules\electron\dist\electron.exe" .
exit
