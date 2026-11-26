# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""抓包启动器 —— 保证「代理绝不会指向一个没人监听的端口」。

上一版的教训：先设代理、再起 MITM，用户一关窗口 MITM 就死，代理却留着 → 整机断网。
这个启动器的顺序是反的，并且退出路径全部兜住：

    备份原代理 → 起 MITM → 探端口确认监听 → 才设代理 → 等用户按回车
    finally: 恢复原代理（原值，不是一律关闭）→ 结束 MITM

用法：
    python 工具/capture_launcher.py --check     # 只看当前代理设置，不改任何东西
    python 工具/capture_launcher.py --port 8086 # 正常抓包
"""
import argparse
import ctypes
import os
import socket
import subprocess
import sys
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


# ---------------------------------------------------------------- 代理读写
def read_proxy():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        def get(name, default):
            try:
                return winreg.QueryValueEx(k, name)[0]
            except OSError:
                return default
        return {
            "enable": int(get("ProxyEnable", 0)),
            "server": get("ProxyServer", ""),
            "override": get("ProxyOverride", ""),
        }


def write_proxy(enable, server=None, override=None):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, int(enable))
        if server is not None:
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        if override is not None:
            winreg.SetValueEx(k, "ProxyOverride", 0, winreg.REG_SZ, override)


def refresh_wininet():
    """通知 WinINet 重新读设置，否则已运行的浏览器/微信不会生效。"""
    try:
        w = ctypes.windll.wininet
        w.InternetSetOptionW(0, 39, 0, 0)   # SETTINGS_CHANGED
        w.InternetSetOptionW(0, 37, 0, 0)   # REFRESH
    except Exception:
        pass


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
    a = ap.parse_args()

    cur = read_proxy()
    if a.check:
        print("当前系统代理：")
        print(f"  ProxyEnable = {cur['enable']}")
        print(f"  ProxyServer = {cur['server'] or '(空)'}")
        print(f"  ProxyOverride = {cur['override'] or '(空)'}")
        print(f"  本机 {a.port} 端口: {'已在监听' if port_busy(a.port) else '没人监听'}")
        return

    if port_busy(a.port):
        print(f"[x] 端口 {a.port} 已被占用，先关掉之前的抓包窗口。")
        return

    mitm = os.path.join(HERE, "mitm_debug_proxy.py")
    print(f"[1/4] 备份当前代理: enable={cur['enable']} server={cur['server'] or '(空)'}")
    proc = None
    try:
        print("[2/4] 启动 MITM …")
        env = dict(os.environ)
        env["PATH"] = r"D:\msys2\mingw64\bin;D:\msys2\usr\bin;" + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-u", mitm, "--port", str(a.port)], env=env)

        if not wait_port(a.port, timeout=20):
            print("[x] MITM 没能在 20 秒内监听 —— 代理设置一个字都没动，你的网络不受影响。")
            return
        print(f"[3/4] MITM 已监听 127.0.0.1:{a.port}，现在才设代理")

        write_proxy(1, f"127.0.0.1:{a.port}")
        refresh_wininet()
        print("      代理已生效（微信若已运行，请完全退出后重开）")
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
        print("\n[4/4] 恢复代理 …")
        try:
            write_proxy(cur["enable"], cur["server"], cur["override"])
            refresh_wininet()
            print(f"      已还原: enable={cur['enable']} server={cur['server'] or '(空)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! 还原失败({e})，请手动在「设置-网络-代理」里关掉代理")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        print("完成。抓到的明文: _private/capture_log.jsonl")


if __name__ == "__main__":
    main()
