# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# --- end lepao-research-notice ---
"""一键修复网络 —— 抓包 / 控制台异常退出之后，把系统代理恢复成「能正常上网」的状态。

症状对应：
    打开启动脚本后，浏览器打不开网页、微信小程序报「网络接口错误」、什么都访问不了。

它只做四件事，全部只在当前用户范围内，不需要管理员：
    1) 有 _private/proxy_backup.json → 按备份原样还原（用户自己的 Clash / 公司代理不会被抹掉）
    2) 没有备份 → 关掉指向本机抓包端口的固定代理
    3) 删掉指向本机的 PAC（AutoConfigURL）
    4) 重置 WinHTTP 代理 + 清空 DNS 缓存

用法：
    python 工具/fix_network.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.dirname(HERE)
PS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
BACKUP = os.path.join(PROG, "_private", "proxy_backup.json")
LOCAL_PORTS = (8081, 8086, 8090)


def reg(*args):
    return subprocess.run(["reg", *args], capture_output=True, text=True, timeout=15)


def read_proxy():
    out = {"enable": 0, "server": "", "override": "", "pac": ""}
    got = False
    try:
        r = reg("query", PS_KEY)
        if r.returncode == 0 and (r.stdout or "").strip():
            got = True
            for line in (r.stdout or "").splitlines():
                p = line.split(None, 2)
                if len(p) < 3:
                    continue
                name, kind, val = p[0].strip(), p[1].strip(), p[2].strip()
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
    except Exception:
        got = False
    if got:
        return out
    try:                                     # reg.exe 被拦时回退到 winreg
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as k:
            def _g(name, dflt=""):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except OSError:
                    return dflt
            out["enable"] = int(_g("ProxyEnable", 0) or 0)
            out["server"] = str(_g("ProxyServer", "") or "")
            out["override"] = str(_g("ProxyOverride", "") or "")
            out["pac"] = str(_g("AutoConfigURL", "") or "")
    except Exception:
        pass
    return out


def set_value(name, kind, val):
    r = reg("add", PS_KEY, "/v", name, "/t", kind, "/d", str(val), "/f")
    return r.returncode == 0


def del_value(name):
    r = reg("delete", PS_KEY, "/v", name, "/f")
    return r.returncode == 0


def refresh():
    """通知 WinINET 重读设置，否则已经开着的浏览器/微信还在用旧代理。"""
    try:
        import ctypes
        w = ctypes.windll.wininet
        w.InternetSetOptionW(0, 39, 0, 0)   # SETTINGS_CHANGED
        w.InternetSetOptionW(0, 37, 0, 0)   # REFRESH
    except Exception:
        pass


def is_local_server(server):
    """ProxyServer 是否指向本工程的抓包端口（8081/8086/8090）。"""
    s = (server or "").strip().replace("http://", "").replace("https://", "")
    if not s:
        return False
    host, _, port = s.rpartition(":")
    host = (host or "").strip("[] ").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    try:
        return int(port) in LOCAL_PORTS
    except ValueError:
        return False


def main():
    print("=" * 62)
    print(" 一键修复网络（系统代理 / WinHTTP / DNS）")
    print("=" * 62)
    cur = read_proxy()
    print("修复前：")
    print(f"  ProxyEnable   = {cur['enable']}")
    print(f"  ProxyServer   = {cur['server'] or '(空)'}")
    print(f"  ProxyOverride = {cur['override'] or '(空)'}")
    print(f"  AutoConfigURL = {cur['pac'] or '(空)'}")
    print()

    actions = []
    fails = []
    bak = None
    if os.path.isfile(BACKUP):
        try:
            with open(BACKUP, encoding="utf-8") as f:
                bak = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"[!] 备份文件读不出来（{e}），按「关闭代理」处理")
            bak = None
    if not isinstance(bak, dict):
        bak = None

    if bak is not None:
        ok = set_value("ProxyEnable", "REG_DWORD", int(bak.get("enable") or 0))
        ok &= set_value("ProxyServer", "REG_SZ", str(bak.get("server") or ""))
        ok &= set_value("ProxyOverride", "REG_SZ", str(bak.get("override") or ""))
        if bak.get("pac"):
            ok &= set_value("AutoConfigURL", "REG_SZ", str(bak["pac"]))
        else:
            del_value("AutoConfigURL")          # 不存在也算成功
        if ok:
            actions.append(f"按备份还原（enable={bak.get('enable')} "
                           f"server={bak.get('server') or '-'}）")
        else:
            fails.append("按备份写回注册表被拒")
        try:
            os.replace(BACKUP, BACKUP + ".restored")
        except OSError:
            pass
    else:
        if cur["enable"] and (not cur["server"] or is_local_server(cur["server"])):
            if set_value("ProxyEnable", "REG_DWORD", 0):
                actions.append("关闭指向本机的系统代理")
            else:
                fails.append("关闭 ProxyEnable 被拒")
        pac = (cur["pac"] or "").lower()
        if pac and ("127.0.0.1" in pac or "localhost" in pac):
            if del_value("AutoConfigURL"):
                actions.append(f"删除残留 PAC {cur['pac']}")
            else:
                fails.append("删除 AutoConfigURL 被拒")

    r = subprocess.run(["netsh", "winhttp", "reset", "proxy"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode == 0:
        actions.append("重置 WinHTTP 代理（Windows 更新 / 商店用那一套）")

    r = subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=20)
    if r.returncode == 0:
        actions.append("清空 DNS 缓存")

    refresh()

    print("已执行：")
    for a in actions or ["（没发现需要改的东西）"]:
        print("  - " + a)
    if fails:
        print()
        print("[!] 下面这些被系统拒绝了（安全软件 / 组策略拦注册表写入）：")
        for f in fails:
            print("  - " + f)
        print("    手动改：Win+R → inetcpl.cpl → 「连接」→ 局域网设置 →")
        print("    取消勾选「为 LAN 使用代理服务器」；同窗口「高级」里把自动配置脚本清空。")
        print("    也可以右键本 bat「以管理员身份运行」再试一次。")
    print()
    after = read_proxy()
    print("修复后：")
    print(f"  ProxyEnable   = {after['enable']}   ← 0 表示不走代理，正常上网")
    print(f"  ProxyServer   = {after['server'] or '(空)'}")
    print(f"  AutoConfigURL = {after['pac'] or '(空)'}")
    print()
    print("现在先打开 https://www.baidu.com 试一下。")
    print("还不行就按顺序查：")
    print("  1) 设置 → 网络和 Internet → 代理：确认「使用代理服务器」是关的")
    print("  2) 关掉所有抓包/控制台黑窗口，再跑一次 5-环境自检.bat")
    print("  3) 微信仍报「网络接口错误」→ 先双击 0-首次使用-安装证书.bat")
    print("     （证书没进「受信任的根证书颁发机构」，所有 HTTPS 握手都会失败）")
    print("  4) 仍然异常 → 禁用再启用一次网络适配器，或者重启电脑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
