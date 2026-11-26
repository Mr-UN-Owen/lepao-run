@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
rem ============================================================
rem  校园跑协议研究 / 进阶：旧版控制台（端口 8770）
rem  需要先有 程序\config.json（从 示例配置 复制）
rem  config 默认站点写的是 api2，本案例要改成 api3.lptiyu.com
rem ============================================================
setlocal
cd /d "%~dp0.."
set "APP=%CD%\程序"
set "PORT=8770"

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

if not exist "%APP%\config.json" (
  echo [!] 还没有 config.json。
  echo     把 示例配置\config-案例816.json 复制到 程序\config.json 再运行本文件。
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   旧版控制台（进阶）：http://127.0.0.1:%PORT%
echo   服务起来后，手动在浏览器输入上面这个网址
echo   关掉本窗口即停止服务
echo ============================================================
echo.
pushd "%APP%"
%PY% -u app\server.py --port %PORT%
popd
echo.
pause
