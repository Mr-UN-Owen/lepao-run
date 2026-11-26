@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=D:\msys2\mingw64\bin\python.exe"
set "PORT=8780"

if not exist "%PY%" (
  echo [x] 找不到 python: %PY%
  echo     用记事本打开本文件，把 PY= 改成你自己的 python.exe 路径
  pause
  exit /b 1
)

echo ============================================================
echo  乐跑网页控制台
echo  网址： http://127.0.0.1:%PORT%
echo  启动后会自动用 Edge 打开，关掉这个窗口即停止服务
echo ============================================================
echo.

"%PY%" -u webapp\server.py --port %PORT% --open
pause