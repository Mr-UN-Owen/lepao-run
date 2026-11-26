@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PORT=8770"
set "PYEXE=python"
where python >nul 2>nul
if errorlevel 1 set "PYEXE=py -3"
echo [lepao] starting console on http://127.0.0.1:%PORT%
start "lepao-console" cmd /c "%PYEXE% app\server.py --port %PORT%"
timeout /t 2 >nul
start "" http://127.0.0.1:%PORT%
echo [lepao] if browser shows nothing, wait 2s and refresh. Close the black window to stop.
