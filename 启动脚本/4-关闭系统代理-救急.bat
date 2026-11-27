@echo off
chcp 936 >nul
set "PYTHONIOENCODING=gbk"
rem ============================================================
rem  校园跑协议研究 / 救急：立刻关闭系统代理
rem  症状：抓包窗口被强关后，浏览器 / 微信上不了网
rem ============================================================
setlocal
echo ============================================================
echo   正在恢复 / 关闭 Windows 系统代理 ...
echo ============================================================
echo.

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer /f >nul 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v AutoConfigURL /f >nul 2>nul
netsh winhttp reset proxy >nul 2>&1

echo 当前代理状态（ProxyEnable 应为 0x0）：
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2>nul
echo.
echo 如果上面显示 0x1，说明这次改注册表被拦下来了（安全软件 / 组策略）。
echo 那就手动改：Win+R → 输入 inetcpl.cpl → 回车 → 「连接」标签
echo          → 局域网设置 → 取消勾选「为 LAN 使用代理服务器」→ 确定。
echo.
echo 浏览器 / 微信如果还打不开网页，按同样的路径再确认一次：
echo   设置 - 网络和 Internet - 代理 - 「使用代理服务器」= 关
echo.
pause
