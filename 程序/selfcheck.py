# -*- coding: utf-8 -*-
"""环境自检 —— 换电脑、重装 Python 后先跑这个。

用法（在 程序 目录下）：
    python 环境自检.py

检查项：Python 版本 / 核心库导入 / 加密后端 / 抓包证书 / openssl / 端口 / 系统代理。
退出码 0 = 全部通过，可以启动网页控制台；1 = 有硬性缺失。
"""
import os
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OK, BAD, WARN = "OK", "X", "!"
PS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def mark(ok, warn=False):
    return WARN if warn else (OK if ok else BAD)


def check_python():
    v = sys.version_info
    ok = v >= (3, 8)
    print(f"[{mark(ok)}] Python 版本 {v.major}.{v.minor}.{v.micro}  "
          f"{'（>=3.8 可用）' if ok else '（太旧，请装 3.8+）'}")
    print(f"      解释器：{sys.executable}")
    return ok


def check_imports():
    good = True
    try:
        from lepao import crypto
        print(f"[{OK}] lepao 核心库导入成功，AES 后端 = {crypto.backend()}")
    except Exception as e:  # noqa: BLE001
        print(f"[{BAD}] lepao 导入失败：{e}")
        good = False
    try:
        sys.path.insert(0, os.path.join(HERE, "webapp"))
        import lplib  # noqa: F401
        print(f"[{OK}] webapp 协议客户端（lplib）导入成功")
    except Exception as e:  # noqa: BLE001
        print(f"[{BAD}] webapp/lplib 导入失败：{e}")
        good = False
    return good


def check_ca():
    ca_dir = os.path.join(HERE, "_private", "mitm_ca")
    crt = os.path.join(ca_dir, "ca.crt")
    key = os.path.join(ca_dir, "ca.key")
    pem = os.path.join(ca_dir, "ca.pem")
    have = all(os.path.isfile(p) for p in (crt, key, pem))
    if not have:
        print(f"[{WARN}] 抓包根证书尚未生成（私钥只在本机生成，不随仓库分发，这是正常的）")
        print("      需要抓包时双击 启动脚本\\0-首次使用-安装证书.bat，会现场生成并装进当前用户")
        return True
    print(f"[{OK}] 抓包根证书已生成：_private/mitm_ca/")
    leaf = os.path.join(ca_dir, "leaf")
    n = len([f for f in os.listdir(leaf) if f.endswith(".crt")]) if os.path.isdir(leaf) else 0
    print(f"      已按域名现签叶证书 {n} 个（新域名在首次访问时自动签）")
    trusted = False
    try:
        p = subprocess.run(["certutil", "-user", "-store", "Root"],
                           capture_output=True, text=True, timeout=20)
        trusted = "lepao-debug-ca" in (p.stdout or "")
    except Exception:  # noqa: BLE001
        pass
    print(f"[{mark(trusted)}] 根证书{'已' if trusted else '尚未'}装入当前用户受信任根"
          f"{'' if trusted else ' —— 先双击 0-首次使用-安装证书.bat'}")
    if have and not trusted:
        print("      证书没进受信任根时，HTTPS 全部握手失败，小程序会报「网络接口错误」")
    return have and trusted


def check_openssl():
    found = shutil.which("openssl") is not None
    if not found:
        for cand in (r"C:\Program Files\Git\usr\bin\openssl.exe",
                     r"C:\Program Files (x86)\Git\usr\bin\openssl.exe",
                     r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe"):
            if os.path.isfile(cand):
                found = True
                break
    print(f"[{mark(found, warn=not found)}] openssl "
          f"{'可用' if found else '未找到（步骤 0 生成抓包证书需要它；装 Git for Windows 或 OpenSSL 后重开窗口）'}")
    return True


def check_ports():
    good = True
    for port, why in ((8780, "网页控制台"), (8086, "抓包端口")):
        s = socket.socket()
        s.settimeout(0.6)
        busy = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        print(f"[{mark(not busy)}] 端口 {port}（{why}）{'被占用，先关掉旧窗口' if busy else '空闲'}")
        if busy:
            good = False
    return good


def _read_proxy_reg():
    """读 HKCU Internet Settings 的四项（含 PAC）。

    优先 reg.exe（不受某些 Python 版本的 winreg 权限问题影响），失败回落到 winreg。
    """
    out = {"enable": 0, "server": "", "override": "", "pac": ""}
    try:
        p = subprocess.run(["reg", "query", PS_KEY], capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and (p.stdout or "").strip():
            for line in (p.stdout or "").splitlines():
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                name, kind, val = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if name == "ProxyEnable":
                    try:
                        out["enable"] = int(val, 16) if kind == "REG_DWORD" else int(val)
                    except ValueError:
                        out["enable"] = 0
                elif name == "ProxyServer":
                    out["server"] = val
                elif name == "ProxyOverride":
                    out["override"] = val
                elif name == "AutoConfigURL":
                    out["pac"] = val
            return out
    except Exception:
        pass

    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_SUBKEY) as k:
        def g(name, default=""):
            try:
                return winreg.QueryValueEx(k, name)[0]
            except OSError:
                return default
        out["enable"] = int(g("ProxyEnable", 0) or 0)
        out["server"] = str(g("ProxyServer", "") or "")
        out["override"] = str(g("ProxyOverride", "") or "")
        out["pac"] = str(g("AutoConfigURL", "") or "")
    return out


def check_proxy():
    """系统代理 / PAC 残留检查 —— 这是「开脚本后整机断网」最常见的现场。"""
    try:
        cur = _read_proxy_reg()
    except Exception as e:  # noqa: BLE001
        print(f"[{WARN}] 读不到系统代理设置：{e}")
        return True

    server = (cur["server"] or "").strip()
    local = any(server.replace("http://", "").lower().startswith(h)
                for h in ("127.0.0.1", "localhost", "[::1]"))
    bad = bool(cur["enable"] and local)
    print(f"[{mark(not bad, warn=bad)}] 固定代理：ProxyEnable={cur['enable']} "
          f"ProxyServer={server or '(空)'}"
          f"{'  ← 指向本机抓包端口，双击 6-一键修复网络.bat' if bad else ''}")

    pac = (cur["pac"] or "").strip()
    pac_local = bool(pac and ("127.0.0.1" in pac or "localhost" in pac))
    if pac:
        print(f"[{mark(not pac_local, warn=pac_local)}] PAC：{pac}"
              f"{'  ← 本机 PAC；控制台没开时会取不到，用 6-一键修复网络.bat 清掉' if pac_local else ''}")
    else:
        print(f"[{OK}] PAC：空（正常）")

    bak = os.path.join(HERE, "_private", "proxy_backup.json")
    if os.path.isfile(bak):
        print(f"[{WARN}] 发现代理备份 proxy_backup.json（说明上次抓包没有正常收尾）")
        print("      双击 启动脚本\\6-一键修复网络.bat 会按它把原代理还原回去")
    return True


def main():
    print("=" * 62)
    print(" 校园跑协议研究 · 环境自检")
    print("=" * 62)
    results = [check_python(), check_imports(), check_ca(), check_openssl(),
               check_ports(), check_proxy()]
    print("=" * 62)
    if all(results):
        print(" 结论：环境可用。下一步双击 启动脚本\\1-启动网页控制台.bat")
        return 0
    print(" 结论：有硬性缺失（[X] 项），按上面提示处理后再跑一次。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
