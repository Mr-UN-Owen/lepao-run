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
echo  乐跑网页控制台 —— 局域网模式
echo ============================================================
echo.
echo 本机地址:  http://127.0.0.1:%PORT%
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=1" %%b in ("%%a") do echo 局域网地址: http://%%b:%PORT%
)
echo.
echo  手机 / 其他电脑在同一个 WiFi 下，用上面的「局域网地址」打开
echo  首次启动 Windows 防火墙会弹窗，选「允许访问」
echo.
echo  注意：这个模式没有登录密码，同一网络里的人只要知道地址就能打开。
echo        只在你自己家的 WiFi / 手机热点下用。
echo.
echo 关闭这个窗口即停止服务
echo ============================================================
echo.
"%PY%" -u webapp\server.py --port %PORT% --host 0.0.0.0
pause
