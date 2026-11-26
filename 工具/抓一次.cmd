@echo off
chcp 65001 >nul
setlocal
set "PATH=D:\msys2\mingw64\bin;D:\msys2\usr\bin;%PATH%"
cd /d "%~dp0.."
set "PY=D:\msys2\mingw64\bin\python.exe"
set "PORT=8086"

if not exist "%PY%" (
  echo [x] 找不到 python: %PY%
  echo     用记事本打开本文件，把 PY= 改成你自己的 python.exe 路径
  pause
  exit /b 1
)

rem ---------- CA：已装则跳过 ----------
certutil -user -store Root 2>nul | findstr /i "lepao-debug-ca" >nul
if errorlevel 1 (
  echo [0/4] 安装本地 CA —— 会弹「安全警告」，点「是」
  certutil -addstore -user Root "_private\mitm_ca\ca.crt" >nul
  if errorlevel 1 (
    echo [x] CA 安装失败，右键本文件「以管理员身份运行」再试
    pause
    exit /b 1
  )
) else (
  echo [0/4] CA 已受信，跳过
)
echo.

rem ---------- 交给启动器：先起 MITM、确认监听、才设代理 ----------
"%PY%" -u 工具\capture_launcher.py --port %PORT%

echo.
pause
