@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
rem ============================================================
rem  校园跑协议研究 / 步骤 2（可选）：局域网模式
rem  手机、另一台电脑在同一 WiFi 下也能打开控制台
rem ============================================================
setlocal
cd /d "%~dp0.."
set "APP=%CD%\程序"
set "PORT=8780"

set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=%%~C"
  )
)
if not defined PY (
  echo [x] 没有找到 Python，请先安装 Python 3.8+ 并勾选 Add to PATH。
  pause
  exit /b 1
)

echo ============================================================
echo   校园跑协议研究 · 网页控制台（局域网模式）
echo ============================================================
echo.
echo 本机地址:   http://127.0.0.1:%PORT%
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=1" %%b in ("%%a") do echo 局域网地址: http://%%b:%PORT%
)
echo.
echo 手机 / 其他电脑连同一个 WiFi，用上面的「局域网地址」打开。
echo 首次启动 Windows 防火墙会弹窗，点【允许访问】。
echo.
echo 注意：本模式没有登录密码，同一网络里只要知道地址就能点提交。
echo       只在自己家 WiFi / 手机热点下使用。切换 WiFi 后地址会变，重新看本窗口。
echo.
echo 关掉本窗口即停止服务。
echo ============================================================
echo.
pushd "%APP%"
%PY% -u 程序\webapp\server.py --port %PORT% --host 0.0.0.0
popd
echo.
pause
