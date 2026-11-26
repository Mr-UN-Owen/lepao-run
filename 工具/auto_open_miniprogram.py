# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""auto_open_miniprogram.py —— 零依赖无人值守拉起电脑微信里的小程序。

用途：`cli.py capture` 起了 mitm 之后调本模块，自动把「数体智慧体育」小程序
     点到跑步首页，让 loginByCode 自己发出来 —— 人不用守着点。

原理（Windows 原生 API，不装任何第三方库）：
  1. 枚举顶层窗口，找微信主窗（WeChatMainWndForPC / Qt*QWindowIcon / 标题含「微信」）
  2. 前置窗口 → Ctrl+F 唤起微信搜索 → 剪贴板写入小程序名 → Ctrl+V → 回车
  3. 微信会打开命中项；若首项不是小程序，用 --fallback-url 或手动点一次

用法:
  python 工具/auto_open_miniprogram.py --name 数体智慧体育          # 直接开
  python 工具/auto_open_miniprogram.py --list-windows              # 只打印窗口标题
  python 工具/auto_open_miniprogram.py --dry --name 数体智慧体育     # 只演示不按键

注意:
  - 需要微信 PC 版已登录，且该小程序在「最近使用」里出现过（首次需手动开过一次）。
  - 若系统开了「以管理员身份运行」，本脚本也要用同样权限，否则按键注入无效。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import sys
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

VK_CONTROL, VK_RETURN, VK_V = 0x11, 0x0D, 0x56
KEYEVENTF_KEYUP = 0x0002
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

WECHAT_CLASSES = ("WeChatMainWndForPC", "Qt51514QWindowIcon", "Qt5QWindowIcon",
                  "Qt652_QLocalSocket", "WeChatLoginWndForPC")


def list_windows():
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 2)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if buf.value.strip():
            out.append((hwnd, cls.value, buf.value.strip()))
        return True

    user32.EnumWindows(cb, 0)
    return out


def find_wechat():
    ws = list_windows()
    for hwnd, cls, title in ws:
        if cls in WECHAT_CLASSES:
            return hwnd, cls, title
    for hwnd, cls, title in ws:
        if "微信" in title and "WeChat" not in cls:
            return hwnd, cls, title
    for hwnd, cls, title in ws:
        if "WeChat" in cls or "WeChat" in title:
            return hwnd, cls, title
    return None, None, None


def set_clipboard(text):
    user32.OpenClipboard(0)
    try:
        user32.EmptyClipboard()
        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, buf, size)
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        user32.CloseClipboard()


def get_clipboard():
    user32.OpenClipboard(0)
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def key(vk, up=False):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if up else 0, 0)
    time.sleep(0.03)


def tap(vk):
    key(vk)
    key(vk, up=True)


def chord(mod, vk):
    key(mod)
    tap(vk)
    key(mod, up=True)


def open_miniprogram(name, delay=1.2, dry=False, restore_clipboard=True):
    hwnd, cls, title = find_wechat()
    if not hwnd:
        raise RuntimeError("未找到微信窗口：请先登录电脑微信（4.x/3.x 均可）")
    print(f"[auto] 微信窗口 hwnd={hwnd} class={cls} title={title!r}")
    if dry:
        return True
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(delay)

    old = ""
    try:
        old = get_clipboard()
    except Exception:  # noqa: BLE001
        pass
    set_clipboard(name)
    time.sleep(0.3)

    chord(VK_CONTROL, ord("F"))         # 唤出微信搜索
    time.sleep(delay)
    chord(VK_CONTROL, VK_V)             # 粘贴小程序名
    time.sleep(delay * 1.2)
    tap(VK_RETURN)                      # 打开命中项（首项通常就是小程序）
    time.sleep(delay)

    if restore_clipboard and old:
        try:
            set_clipboard(old)
        except Exception:  # noqa: BLE001
            pass
    print(f"[auto] 已向微信搜索发送: {name}（若首项不是小程序，手动点一次即可）")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="无人值守打开电脑微信小程序")
    ap.add_argument("--name", default="数体智慧体育", help="小程序名（微信搜索词）")
    ap.add_argument("--delay", type=float, default=1.2, help="每步等待秒数")
    ap.add_argument("--dry", action="store_true", help="只找窗口，不按键")
    ap.add_argument("--list-windows", action="store_true", help="打印所有可见窗口")
    a = ap.parse_args(argv)
    if a.list_windows:
        for hwnd, cls, title in list_windows():
            print(f"{hwnd:>10}  {cls:<32} {title}")
        return 0
    try:
        open_miniprogram(a.name, a.delay, a.dry)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[auto] 失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
