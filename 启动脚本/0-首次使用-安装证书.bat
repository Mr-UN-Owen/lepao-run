@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
rem ============================================================
rem  校园跑协议研究 / 步骤 0：生成并安装本机抓包证书（只需一次）
rem  证书与私钥都只生成在这台电脑上，不随仓库/压缩包分发
rem ============================================================
setlocal
cd /d "%~dp0.."
set "APP=%CD%\程序"
set "CA=%APP%\_private\mitm_ca\ca.crt"

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
echo   生成并安装本机抓包证书（当前用户，免管理员）
echo   私钥会写在本机 程序\_private\mitm_ca\，不上传、不要外发
echo ============================================================
echo.
echo 下面会弹出「安全警告」窗口：
echo     请点【是】按钮 —— 只点一次，装到当前用户，不需要管理员权限。
echo.
echo 正在生成证书（首次约 3~10 秒，需要本机有 openssl）...
echo.

pushd "%APP%"
%PY% -u 工具\mitm_debug_proxy.py --init
set "RC=%ERRORLEVEL%"
popd

if not "%RC%"=="0" (
  echo.
  echo [x] 生成或安装失败。最常见的原因是本机没有 openssl：
  echo     装一个 Git for Windows（自带 openssl）或 OpenSSL 后，重开本窗口再试。
  echo     也可以先双击 5-环境自检.bat 看 openssl 那一行是不是 [!]。
  echo.
  pause
  exit /b 1
)

if not exist "%CA%" (
  echo.
  echo [x] 命令跑完了但没找到证书文件：
  echo     %CA%
  echo     请双击 5-环境自检.bat 看具体是哪一步失败。
  echo.
  pause
  exit /b 1
)

echo.
echo [OK] 安装完成。下一步：双击 1-启动网页控制台.bat
echo      证书只在本机有效，别人拿到这个文件夹也签不出同样的证书。
echo      用完后想删掉：Win+R 输入 certmgr.msc → 受信任的根证书颁发机构
echo      → 证书 → 找到 lepao-debug-ca → 右键删除。
echo.
pause
