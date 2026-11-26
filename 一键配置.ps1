# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
<#
一键配置（Windows）: Python/依赖/mitmproxy/根证书/配置 全链路体检与补齐。
用法: powershell -ExecutionPolicy Bypass -File .\一键配置.ps1
仅做本机环境准备，不联网上传任何数据。
#>
param([switch]$SkipCert)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Say($m)  { Write-Host "== $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  ok   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  warn $m" -ForegroundColor Yellow }
function Bad($m)  { Write-Host "  fail $m" -ForegroundColor Red }

Say '1/5 检查 Python'
$py = $null
foreach ($cand in @('py -3', 'python', 'python3')) {
  $parts = $cand.Split(' ')
  $exe = Get-Command $parts[0] -ErrorAction SilentlyContinue
  if ($exe) {
    try {
      $v = & $parts[0] $parts[1..($parts.Count-1)] --version 2>&1
      if ($v -match 'Python 3\.(\d+)') {
        if ([int]$Matches[1] -ge 10) { $py = $cand; Ok "$cand → $v"; break }
        else { Warn "$cand 版本过低: $v (需 3.10+)" }
      }
    } catch { }
  }
}
if (-not $py) { Bad '未找到 Python 3.10+，请先安装 https://www.python.org/downloads/'; exit 1 }
$pyExe = $py.Split(' ')[0]
$pyPrefix = $py.Split(' ')[1..($py.Count-1)]

Say '2/5 安装 Python 依赖'
$req = Join-Path $root 'requirements.txt'
if (Test-Path $req) {
  & $pyExe @pyPrefix -m pip install -r $req --quiet
  if ($LASTEXITCODE -eq 0) { Ok 'requirements.txt 已安装（pycryptodome 等）' }
  else { Warn 'pip 安装失败，请检查网络/镜像后重试: pip install -r requirements.txt' }
} else { Warn '缺少 requirements.txt' }

Say '3/5 检查 mitmproxy（抓号链路）'
$mitm = (Get-Command mitmdump -ErrorAction SilentlyContinue)
if (-not $mitm) { $mitm = (Get-Command mitmweb -ErrorAction SilentlyContinue) }
if ($mitm) {
  Ok "找到 $($mitm.Source)"
} else {
  Warn '未找到 mitmdump/mitmweb，尝试安装 mitmproxy'
  & $pyExe @pyPrefix -m pip install mitmproxy --quiet
  if ($LASTEXITCODE -eq 0) { Ok 'mitmproxy 已安装' }
  else {
    Bad 'mitmproxy 安装失败 → 手动: py -3 -m pip install mitmproxy'
    Warn '或用环境变量 LEPAO_MITM_EXE 指向已有的 mitmdump.exe'
  }
}

Say '4/5 检查 mitmproxy 根证书（抓不到号的头号原因）'
$caDir = Join-Path $env:USERPROFILE '.mitmproxy'
$ca = Join-Path $caDir 'mitmproxy-ca-cert.cer'
if (-not (Test-Path $ca)) {
  Warn "尚未生成 CA: $ca"
  Write-Host '  → 先启动一次 mitm（如 mitmdump -p 8081），退出后再跑本脚本'
} elseif ($SkipCert) {
  Warn '按参数跳过证书安装'
} else {
  $thumb = (& certutil -hashfile $ca SHA1) 2>$null | Where-Object { $_ -match '^[0-9a-fA-F ]{40,}$' }
  $thumb = ($thumb -replace ' ', '').ToLower()
  $store = (& certutil -user -store Root) 2>$null | Out-String
  if ($thumb -and $store.ToLower().Replace(' ', '').Contains($thumb)) {
    Ok 'CA 已受信（当前用户根库）'
  } else {
    Write-Host "  → 安装到当前用户受信任根（免管理员）"
    & certutil -addstore -user Root $ca | Out-Null
    if ($LASTEXITCODE -eq 0) { Ok 'CA 安装完成（用毕可在 certmgr.msc 删除）' }
    else { Bad 'CA 安装失败 → 双击 .cer 手动安装到「受信任的根证书颁发机构」' }
  }
}

Say '5/5 生成运行配置'
$cfg = Join-Path $root 'config.json'
$sample = Join-Path $root 'config.sample.json'
if (Test-Path $cfg) { Ok 'config.json 已存在（不覆盖）' }
elseif (Test-Path $sample) { Copy-Item $sample $cfg; Ok '已从 config.sample.json 生成 config.json' }
else { Warn '缺少 config.sample.json' }

Write-Host ''
Say '完成。下一步:'
Write-Host '  py -3 cli.py license                 # 署名/声明/构建戳'
Write-Host '  py -3 cli.py cert                    # 证书体检'
Write-Host '  py -3 cli.py account add 你的名字 你的学号'
Write-Host '  py -3 cli.py capture --member 你的名字'
Write-Host '  py -3 cli.py build   --member 你的名字   # 干跑（零写入）'
Write-Host '  py -3 cli.py submit  --member 你的名字   # 提交'
Write-Host ''
Write-Host '提醒: 只打卡本人或已明确同意的成员；凭证仅存本机; 数据目录请勿放云同步盘。' -ForegroundColor Yellow
