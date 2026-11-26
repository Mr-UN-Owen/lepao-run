@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
rem ============================================================
rem  校园跑协议研究 / 步骤 3（备用）：命令行抓一次凭证
rem  网页上的「一键获取凭证」不好使时，用这个窗口手动抓
rem ============================================================
setlocal
cd /d "%~dp0.."
set "APP=%CD%\程序"
set "PORT=8086"

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

certutil -user -store Root 2>nul | findstr /i "lepao-debug-ca" >nul
if errorlevel 1 (
  echo [!] 抓包证书还没装，先去双击 0-首次使用-安装证书.bat
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo   校园跑协议研究 · 命令行抓凭证（端口 %PORT%）
echo ============================================================
echo.
echo 抓包会自动做三件事：
echo   1) 先把系统代理备份下来
echo   2) 起本机抓包端口，确认监听成功后才改代理
echo   3) 你按回车结束，它一定把代理原样还原
echo.
echo 现在去：微信 → 小程序「公大跑者」→ 进跑步页 → 点一次开始跑步
echo 然后回到本窗口按【回车】结束抓包。
echo ============================================================
echo.
pushd "%APP%"
%PY% -u 工具\capture_launcher.py --port %PORT%
popd
echo.
echo 抓到的明文：程序\_private\capture_log.jsonl
echo 想立刻去掉系统代理：双击 4-关闭系统代理-救急.bat
echo.
pause
