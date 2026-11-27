@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
rem ============================================================
rem  校园跑协议研究 / 一键修复网络（抓包后整机断网就用这个）
rem  它会：按备份还原原代理 -^> 关掉指向本机的代理 -^> 删残留 PAC
rem        -^> 重置 WinHTTP -^> 清 DNS 缓存
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
%PY% -u 工具\fix_network.py
set "RC=%ERRORLEVEL%"
popd
echo.
echo 相关脚本：
echo   4-关闭系统代理-救急.bat    只做最快的那一步（关代理）
echo   5-环境自检.bat             检查 Python / 证书 / 端口 / 代理状态
echo   0-首次使用-安装证书.bat    证书没装时 HTTPS 抓包必失败
echo.
pause
