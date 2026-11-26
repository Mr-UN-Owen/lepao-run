# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.certctl —— mitmproxy 根证书体检 / 安装

"抓不到登录流量"的头号原因（异地/新机 100% 命中）:
  mitm 能起、代理已生效, 但小程序 TLS 握手拒绝 mitm 签发的证书 →
  loginByCode 根本不发生 → 表现为一直"等待登录流量"直到超时。

体检项:
  1. ~/.mitmproxy/mitmproxy-ca-cert.cer 是否存在（CA 是否已生成）
  2. 该证书是否在「当前用户 → 受信任的根证书颁发机构」中（仅 Windows 可自动判定）

安装: certutil -addstore -user Root <cer>（免管理员，只影响当前用户）
"""
import os
import subprocess
import sys

CA_DIR = os.path.join(os.path.expanduser("~"), ".mitmproxy")
CA_CER = os.path.join(CA_DIR, "mitmproxy-ca-cert.cer")


def ca_exists():
    return os.path.isfile(CA_CER)


def _run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001 - 诊断路径需要吞掉所有异常
        return -1, str(e)


def _cert_thumbprint():
    """用 certutil 算 SHA1 指纹（Windows）。失败返回空串。"""
    if sys.platform != "win32" or not ca_exists():
        return ""
    rc, out = _run(["certutil", "-hashfile", CA_CER, "SHA1"])
    if rc != 0:
        return ""
    for line in out.splitlines():
        s = line.strip().replace(" ", "")
        if len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s):
            return s.lower()
    return ""


def trusted():
    """证书是否已在当前用户受信任根中。非 Windows 无法自动判定，返回 None。"""
    if sys.platform != "win32":
        return None
    tp = _cert_thumbprint()
    if not tp:
        return False
    rc, out = _run(["certutil", "-user", "-store", "Root"])
    if rc != 0:
        return None
    return tp in out.replace(" ", "").lower()


def status():
    return {
        "platform": sys.platform,
        "ca_dir": CA_DIR,
        "ca_file": CA_CER,
        "exists": ca_exists(),
        "trusted": trusted(),
    }


def install(verbose=True):
    """安装到当前用户受信任根。返回 True/False。"""
    if not ca_exists():
        if verbose:
            print(f"[cert] 未找到 mitmproxy CA: {CA_CER}")
            print("[cert] 先跑一次 mitmdump/mitmweb（任意参数）让它生成 CA, 再回来安装")
        return False
    if sys.platform != "win32":
        if verbose:
            print(f"[cert] 非 Windows: 请手动把 {CA_CER} 加入系统/浏览器受信根")
        return False
    rc, out = _run(["certutil", "-addstore", "-user", "Root", CA_CER])
    ok = rc == 0
    if verbose:
        print(f"[cert] 安装{'成功' if ok else '失败'}: {CA_CER}")
        if not ok:
            print(out.strip()[:400])
        else:
            print("[cert] 提示: 用毕可在 certmgr.msc 的「受信任的根证书颁发机构」中删除该证书")
    return ok


def report(verbose=True):
    st = status()
    if verbose:
        print(f"[cert] 平台={st['platform']}  CA={st['ca_file']}")
        print(f"[cert] CA 存在={st['exists']}  受信={st['trusted']}"
              + ("（非 Windows 不判定）" if st["trusted"] is None else ""))
        if not st["exists"]:
            print("[cert] ⇒ 抓不到号的第一步: 先启动一次 mitm 生成 CA, 再 `cli.py cert --install`")
        elif st["trusted"] is False:
            print("[cert] ⇒ 证书未受信: `cli.py cert --install`（免管理员）")
        elif st["trusted"] is True:
            print("[cert] ⇒ 证书链正常")
    return st
