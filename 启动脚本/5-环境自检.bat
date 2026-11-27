@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
rem ============================================================
rem  校园跑协议研究 / 环境自检
rem  换电脑、装完 Python 后先跑这个，全绿再往下走
rem ============================================================
setlocal
cd /d "%~dp0.."
set "APP=%CD%\程序"

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

pushd "%APP%"
%PY% -u selfcheck.py
set "RC=%ERRORLEVEL%"
popd
echo.
if "%RC%"=="0" (
  echo 自检通过，可以双击 1-启动网页控制台.bat 了。
) else (
  echo 上面有 [X] 项，按提示处理后再跑一次自检。
)
pause
