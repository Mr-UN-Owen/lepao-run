@echo off
chcp 65001 >nul
echo 正在关闭系统代理 ...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
netsh winhttp reset proxy >nul 2>&1
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable
echo.
echo 已关闭。若浏览器仍异常，打开「设置 - 网络和 Internet - 代理」确认「使用代理服务器」是关的。
pause
