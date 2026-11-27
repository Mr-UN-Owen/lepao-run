@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
rem ============================================================
rem  校园跑协议研究 / 救急：一键修复网络
rem  症状：抓包窗口被强关后，浏览器 / 微信上不了网、小程序报「网络接口错误」
rem  比旧版多做三件事：按备份还原你原有的代理、删掉残留 PAC、重置 WinHTTP
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
  echo [x] 没有找到 Python。手动作业：Win+R 输入 inetcpl.cpl
  echo     -^> 「连接」-^> 局域网设置 -^> 取消勾选「为 LAN 使用代理服务器」
  pause
  exit /b 1
)

pushd "%APP%"
%PY% -u 工具\fix_network.py
set "RC=%ERRORLEVEL%"
popd
echo.
if not "%RC%"=="0" echo [!] 修复脚本异常退出，请看上面最后几行报错。
pause
