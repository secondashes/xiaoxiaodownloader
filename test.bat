@echo off
cd /d "%~dp0\gui"
echo test > ..\logs\bat_test.txt
"node_modules\electron\dist\electron.exe" .
