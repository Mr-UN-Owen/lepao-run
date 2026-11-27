# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""抓包启动器 —— 保证「代理绝不会指向一个没人监听的端口」，也绝不拖垮整机网络。

两条硬规则：

1. 顺序：备份原代理 → 起 MITM → 探端口确认监听 → 才设代理 → 等用户按回车
   finally 里恢复原值（原值，不是一律关闭），用户的 Clash / 公司代理原封不动。

2. 默认只代理乐跑域名（PAC）：本进程自己托管一个 PAC，只有 *.lptiyu.com 这些域名
   走 127.0.0.1:8086，其余网站全部 DIRECT。所以哪怕 MITM 挂了，别的网页照样打得开。
   需要用全局代理时加 --global（仍会排除本机与局域网）。

用法：
    python 工具/capture_launcher.py --check        # 只看当前代理设置，不改任何东西
    python 工具/capture_launcher.py --port 8086    # 正常抓包（PAC，只代理乐跑域名）
    python 工具/capture_launcher.py --global       # 兼容模式：系统全局代理
"""
import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROG = os.path.dirname(HERE)                     # 程序/
PS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
BACKUP = os.path.join(PROG, "_private", "proxy_backup.json")

PAC_HOSTS = ("lptiyu.com", "weixin.qq.com", "wx.qq.com", "servicewechat.com")
PAC_PORT = 8091
PROXY_OVERRIDE = "<local>;127.*;localhost;*.local;10.*;172.16.*;192.168.*"
CAP_PORT = {"v": 8086}


# ---------------------------------------------------------------- 代理读写
def _reg(*args):
    r = subprocess.run(["reg", *args], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError(((r.stdout or "") + (r.stderr or "")).strip()
                           or f"reg 返回 {r.returncode}")
    return r


def read_proxy():
    out = {"enable": 0, "server": "", "override": "", "pac": ""}
    got = False
    try:
        r = subprocess.run(["reg", "query", PS_KEY], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and (r.stdout or "").strip():
            got = True
            for line in (r.stdout or "").splitlines():
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


def write_proxy(enable, server=None, override=None, pac=None):
    _reg("add", PS_KEY, "/v", "ProxyEnable", "/t", "REG_DWORD", "/d", str(int(enable)), "/f")
    if server is not None:
        _reg("add", PS_KEY, "/v", "ProxyServer", "/t", "REG_SZ", "/d", server, "/f")
    if override is not None:
        _reg("add", PS_KEY, "/v", "ProxyOverride", "/t", "REG_SZ", "/d", override, "/f")
    if pac is not None:
        if pac:
            _reg("add", PS_KEY, "/v", "AutoConfigURL", "/t", "REG_SZ", "/d", pac, "/f")
        else:
            subprocess.run(["reg", "delete", PS_KEY, "/v", "AutoConfigURL", "/f"],
                           capture_output=True, text=True, timeout=10)
    refresh_wininet()


def restore_proxy(d):
    d = d if isinstance(d, dict) else {}
    write_proxy(int(d.get("enable") or 0),
                str(d.get("server") or ""),
                str(d.get("override") or ""),
                str(d.get("pac") or ""))


def refresh_wininet():
    """通知 WinINet 重新读设置，否则已运行的浏览器/微信不会生效。"""
    try:
        import ctypes
        w = ctypes.windll.wininet
        w.InternetSetOptionW(0, 39, 0, 0)   # SETTINGS_CHANGED
        w.InternetSetOptionW(0, 37, 0, 0)   # REFRESH
    except Exception:
        pass


# ---------------------------------------------------------------- PAC
def pac_text(port):
    hosts = ", ".join('"%s"' % h for h in PAC_HOSTS)
    return "\n".join([
        "function FindProxyForURL(url, host) {",
        f"  var d = [{hosts}];",
        "  host = (host || '').toLowerCase();",
        "  for (var i = 0; i < d.length; i++) {",
        "    var x = d[i];",
        "    if (host === x || host.slice(-(x.length + 1)) === '.' + x)",
        f"      return 'PROXY 127.0.0.1:{port}; DIRECT';",
        "  }",
        "  return 'DIRECT';",
        "}",
        "",
    ])


class _PacHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        if self.path.split("?", 1)[0] not in ("/proxy.pac", "/pac"):
            self.send_error(404)
            return
        body = pac_text(CAP_PORT["v"]).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ns-proxy-autoconfig; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):   # 静音
        pass


def start_pac_server(port=PAC_PORT):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _PacHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------- 端口探测
def wait_port(port, timeout=15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.4)
            s.close()
            return True
        except Exception:
            time.sleep(0.15)
    return False


def port_busy(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.4)
        s.close()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--check", action="store_true", help="只显示当前代理，不修改")
    ap.add_argument("--global", dest="global_mode", action="store_true",
                    help="兼容模式：设系统全局代理（仍排除本机/局域网）")
    a = ap.parse_args()
    CAP_PORT["v"] = a.port

    cur = read_proxy()
    if a.check:
        print("当前系统代理：")
        print(f"  ProxyEnable   = {cur['enable']}")
        print(f"  ProxyServer   = {cur['server'] or '(空)'}")
        print(f"  ProxyOverride = {cur['override'] or '(空)'}")
        print(f"  AutoConfigURL = {cur['pac'] or '(空)'}")
        print(f"  本机 {a.port} 端口: {'已在监听' if port_busy(a.port) else '没人监听'}")
        return

    if port_busy(a.port):
        print(f"[x] 端口 {a.port} 已被占用，先关掉之前的抓包窗口。")
        return

    mitm = os.path.join(HERE, "mitm_debug_proxy.py")
    print(f"[1/5] 备份当前代理：enable={cur['enable']} server={cur['server'] or '(空)'} "
          f"pac={cur['pac'] or '(空)'}")
    try:
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        with open(BACKUP, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
    except OSError as e:
        print(f"[!] 备份文件写不进去（{e}），退出兜底会失效，但主流程照走")

    proc = None
    pac_srv = None
    try:
        if not a.global_mode:
            if port_busy(PAC_PORT):
                print(f"[!] PAC 端口 {PAC_PORT} 被占用，退回全局模式")
                a.global_mode = True
            else:
                pac_srv = start_pac_server(PAC_PORT)
                print(f"[2/5] PAC 已就绪 http://127.0.0.1:{PAC_PORT}/proxy.pac"
                      "（只有乐跑域名走代理）")
        if a.global_mode:
            print("[2/5] 兼容模式：稍后设系统全局代理（排除本机与局域网）")

        print("[3/5] 启动 MITM …")
        env = dict(os.environ)
        env["PATH"] = r"D:\msys2\mingw64\bin;D:\msys2\usr\bin;" + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-u", mitm, "--port", str(a.port)], env=env)

        if not wait_port(a.port, timeout=20):
            print("[x] MITM 没能在 20 秒内监听 —— 代理设置一个字都没动，你的网络不受影响。")
            return
        print(f"[4/5] MITM 已监听 127.0.0.1:{a.port}，现在才动系统代理")

        if a.global_mode:
            write_proxy(1, f"127.0.0.1:{a.port}", PROXY_OVERRIDE, pac="")
            print("      已设全局代理（本机/局域网直连，不受影响）")
        else:
            write_proxy(0, override=PROXY_OVERRIDE,
                        pac=f"http://127.0.0.1:{PAC_PORT}/proxy.pac")
            print("      已设 PAC：只有 *.lptiyu.com 走抓包，其他网页直连，断不了网")

        def guard():
            while True:
                time.sleep(1.5)
                if proc.poll() is not None:
                    print("\n[!] MITM 进程退出了，正在自动还原系统代理 …")
                    try:
                        restore_proxy(cur)
                    except Exception:
                        pass
                    return

        threading.Thread(target=guard, daemon=True).start()

        print()
        print("=" * 60)
        print(" 现在去：打开微信 → 「公大跑者」→ 进跑步页")
        print(" 抓到你想要的报文后，回到这个窗口按回车结束")
        print("=" * 60)
        try:
            input("\n按回车结束抓包（会自动恢复代理）… ")
        except EOFError:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[5/5] 恢复代理 …")
        try:
            restore_proxy(cur)
            print(f"      已还原：enable={cur['enable']} server={cur['server'] or '(空)'} "
                  f"pac={cur['pac'] or '(空)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! 还原失败（{e}），请双击 启动脚本\\6-一键修复网络.bat")
        try:
            os.remove(BACKUP)
        except OSError:
            pass
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        if pac_srv is not None:
            try:
                pac_srv.shutdown()
            except Exception:
                pass
        print("完成。抓到的明文: 程序\\_private\\capture_log.jsonl")
        if os.environ.get("LEPAO_NO_PAUSE") != "1":
            pass


if __name__ == "__main__":
    main()
