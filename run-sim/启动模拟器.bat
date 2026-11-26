@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PORT=8771"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

echo [run-sim] 启动 http://127.0.0.1:%PORT%
start "" "http://127.0.0.1:%PORT%"
%PY% server.py --port %PORT%
if errorlevel 1 pause
