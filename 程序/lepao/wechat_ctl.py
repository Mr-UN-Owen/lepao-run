# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.wechat_ctl —— 微信进程控制（只做进程级操作）

用途: 避免"同账号重复登录顶掉刚抓到的 token"。做法仅是结束客户端进程后由用户重新扫码。
**不读取、不修改、不导出**微信本地任何数据（聊天记录/数据库/内存一律不碰）。
可在 config.json 的 environment 中关闭: "wechat_logout_before_capture": false
"""
import os
import subprocess
import sys

PROCESS_NAMES = ("WeChat.exe", "Weixin.exe")

COMMON_PATHS = (
    r"C:\Program Files\Tencent\WeChat\WeChat.exe",
    r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    r"C:\Program Files\Tencent\Weixin\Weixin.exe",
    r"C:\Program Files (x86)\Tencent\Weixin\Weixin.exe",
)


def _reg_path():
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        for exe in PROCESS_NAMES:
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(
                            root,
                            rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                        p = winreg.QueryValueEx(k, "")[0]
                        if p and os.path.isfile(p):
                            return p
                except OSError:
                    continue
    except Exception:
        pass
    return ""


def find_wechat():
    """返回微信可执行文件路径（找不到返回空串）。"""
    env = os.environ.get("LEPAO_WECHAT", "").strip()
    if env and os.path.isfile(env):
        return env
    p = _reg_path()
    if p:
        return p
    for p in COMMON_PATHS:
        if os.path.isfile(p):
            return p
    return ""


def running():
    """微信是否在运行（仅 Windows 可判定，其他平台返回 None）。"""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WeChat.exe", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout or ""
        out2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/NH"],
                              capture_output=True, text=True, timeout=15).stdout or ""
        return ("WeChat.exe" in out) or ("Weixin.exe" in out2)
    except Exception:
        return None


def logout(verbose=True):
    """结束微信客户端进程（仅进程级）。返回 True=已结束/未在运行。"""
    if sys.platform != "win32":
        if verbose:
            print("[wechat] 非 Windows: 请手动退出微信后重试")
        return False
    killed = False
    for name in PROCESS_NAMES:
        try:
            p = subprocess.run(["taskkill", "/F", "/IM", name],
                               capture_output=True, text=True, timeout=20)
            if p.returncode == 0:
                killed = True
                if verbose:
                    print(f"[wechat] 已结束进程 {name}")
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"[wechat] 结束 {name} 失败: {e}")
    if verbose and not killed:
        print("[wechat] 未发现运行中的微信进程（可直接开始）")
    return True


def status(verbose=True):
    st = {"platform": sys.platform, "exe": find_wechat(), "running": running()}
    if verbose:
        print(f"[wechat] exe={st['exe'] or '未找到'}")
        print(f"[wechat] 运行中={st['running']}"
              + ("（非 Windows 不判定）" if st["running"] is None else ""))
        if not st["exe"]:
            print("[wechat] 提示: 可用环境变量 LEPAO_WECHAT 指定微信路径")
    return st
