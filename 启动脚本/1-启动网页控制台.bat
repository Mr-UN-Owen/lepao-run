@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
rem ============================================================
rem  校园跑协议研究 / 步骤 1：启动网页控制台
rem  双击本文件即可；关掉这个黑窗口 = 停止服务
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
  echo [x] 没有找到 Python。
  echo     请先安装 Python 3.8 或更高版本，安装时务必勾选
  echo     "Add python.exe to PATH"，装完重开本窗口。
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   校园跑协议研究 · 网页控制台
echo   本机网址: http://127.0.0.1:%PORT%
echo   启动后浏览器会自动打开；关掉本窗口即停止服务
echo ============================================================
echo.
rem ---- 启动前清掉指向本机的系统代理（避免残留导致断网）----
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>&1
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2>nul | findstr /c:"0x0" >nul && (echo   已确认系统代理关闭) || (echo   [警告] 系统代理关闭失败，请手动运行 4-关闭系统代理-救急.bat)
echo.
pushd "%APP%"
%PY% -u webapp\server.py --port %PORT% --open
popd
echo.
echo 服务已退出。浏览器里点不动，重新双击本文件即可。
pause
