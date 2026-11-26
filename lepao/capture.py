# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.capture —— 抓号会话（ProxyGuard + mitm 起停 + 等新 token + 身份归位）

模型（R3 实证）:
  - 不自动操作微信: 人开小程序产生 loginByCode, addon **被动**落 `凭证.json`。
  - addon 只放行注册表登记成员（白名单在 addon 内二次校验），未登记凭证不落盘。
  - 抓到后按 uid/学号/卡号归位到该成员槽, 再交给 auth.AuthState.set_token。
  - 系统代理在会话开始设置、结束/异常一律复原（proxy_backup.json 为复原依据）。

环境变量:
  LEPAO_MITM_EXE   mitmdump/mitmweb 可执行文件（缺省在 PATH 里找）
  LEPAO_MITM_PORT  mitm 监听端口（默认 8081, 与 config.environment.api_proxy 一致）
  LEPAO_MITM_UPSTREAM  mitm 上游代理（默认读系统代理, 无则直连）
"""
import json
import os
import shutil
import subprocess
import sys
import time

from .accounts import AccountError, _atomic_write_json
from .auth import AuthState

CRED_FILE = "凭证.json"
BACKUP_FILE = "proxy_backup.json"
MITM_LOG = "mitm_流量.log"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def addon_path():
    """抓号 addon 位置：仓库 `工具/mitm_lptiyu_token.py`。"""
    p = os.path.join(repo_root(), "工具", "mitm_lptiyu_token.py")
    if not os.path.isfile(p):
        raise AccountError(f"找不到抓号插件: {p}（发行包须包含 工具/ 目录）")
    return p


def find_mitm():
    exe = os.environ.get("LEPAO_MITM_EXE", "").strip()
    if exe:
        if os.path.isfile(exe):
            return exe
        raise AccountError(f"LEPAO_MITM_EXE 指向的文件不存在: {exe}")
    for name in ("mitmweb", "mitmdump"):
        w = shutil.which(name)
        if w:
            return w
    # 常见 pip --user 脚本目录兜底
    for base in (os.path.expanduser("~/.local/bin"),
                 os.path.join(os.environ.get("APPDATA", ""), "Python")):
        if not base or not os.path.isdir(base):
            continue
        for name in ("mitmdump.exe", "mitmweb.exe"):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                return p
    raise AccountError(
        "未找到 mitmproxy 可执行文件（mitmdump/mitmweb）。\n"
        "→ pip install mitmproxy, 或用环境变量 LEPAO_MITM_EXE 指定完整路径")


# ================================================================ 系统代理
class ProxyGuard:
    """系统代理的设置/复原。Windows 走注册表; 其他平台只提示不自动改。"""

    REG = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

    def __init__(self, data_dir=".", proxy="127.0.0.1:8081", verbose=True):
        self.data_dir = os.path.abspath(data_dir)
        self.proxy = proxy
        self.verbose = verbose
        self.backup_path = os.path.join(self.data_dir, BACKUP_FILE)
        self._applied = False

    # -------------------------------------------------- 注册表读写
    def _read(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG) as k:
            def g(name, dflt=None):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except FileNotFoundError:
                    return dflt
            return {"ProxyEnable": int(g("ProxyEnable", 0) or 0),
                    "ProxyServer": str(g("ProxyServer", "") or ""),
                    "ProxyOverride": str(g("ProxyOverride", "") or "")}

    def _write(self, enable, server):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG,
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, int(enable))
            winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, server)
        self._notify()

    @staticmethod
    def _notify():
        """通知系统代理设置已变更（IE/WinINet 缓存刷新）。失败不影响主流程。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, 39, 0, 0)  # SETTINGS_CHANGED
            wininet.InternetSetOptionW(0, 37, 0, 0)  # REFRESH
        except Exception:
            pass

    # -------------------------------------------------- 对外
    def backup(self):
        """把当前系统代理原值写入 proxy_backup.json（幂等: 已有备份不覆盖）。"""
        if os.path.isfile(self.backup_path):
            return self.backup_path
        if sys.platform != "win32":
            return None
        try:
            cur = self._read()
        except Exception as e:
            if self.verbose:
                print(f"[proxy] 读取系统代理失败（跳过备份）: {e}")
            return None
        _atomic_write_json(self.backup_path,
                           {"platform": sys.platform, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "original": cur})
        if self.verbose:
            print(f"[proxy] 原值已备份 → {self.backup_path} "
                  f"(enable={cur['ProxyEnable']} server={cur['ProxyServer'] or '-'})")
        return self.backup_path

    def enable(self):
        """把系统代理指向本地 mitm。非 Windows 仅提示。"""
        if sys.platform != "win32":
            if self.verbose:
                print(f"[proxy] 非 Windows: 请手动把系统代理设为 {self.proxy}")
            return False
        if not os.path.isfile(self.backup_path):
            self.backup()
        self._write(1, self.proxy)
        self._applied = True
        if self.verbose:
            print(f"[proxy] 系统代理 → {self.proxy}")
        return True

    def restore(self):
        """复原系统代理（幂等；无备份时只关代理，不动服务器字段）。"""
        if sys.platform != "win32":
            if self.verbose:
                print("[proxy] 非 Windows: 请手动复原系统代理")
            return False
        original = None
        if os.path.isfile(self.backup_path):
            try:
                with open(self.backup_path, encoding="utf-8") as f:
                    original = (json.load(f) or {}).get("original")
            except (json.JSONDecodeError, OSError):
                original = None
        try:
            if isinstance(original, dict):
                self._write(int(original.get("ProxyEnable") or 0),
                            str(original.get("ProxyServer") or ""))
                if self.verbose:
                    print("[proxy] 已复原系统代理（原值）")
            else:
                self._write(0, "")
                if self.verbose:
                    print("[proxy] 无备份, 已关闭系统代理")
            if os.path.isfile(self.backup_path):
                os.replace(self.backup_path, self.backup_path + ".restored")
        except Exception as e:
            print(f"[proxy] 复原失败(需手动处理): {e}")
            return False
        self._applied = False
        return True


# ================================================================ 凭证文件
def _read_creds(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("records") or [])
    return []


def _fingerprint(rec):
    return f"{rec.get('at')}|{rec.get('uid')}|{str(rec.get('token'))[:12]}"


# ================================================================ 抓号会话
class CaptureSession:
    """抓号会话: 起 mitm → 等人开小程序 → 捕获 token → 归位 → 收链复原。"""

    def __init__(self, registry, data_dir=None, port=None, timeout=240, verbose=True):
        self.reg = registry
        self.data_dir = os.path.abspath(data_dir or os.path.dirname(registry.config_path))
        self.port = int(port or os.environ.get("LEPAO_MITM_PORT") or 8081)
        self.timeout = int(timeout)
        self.verbose = verbose
        self.cred_path = os.path.join(self.data_dir, CRED_FILE)
        self.log_path = os.path.join(self.data_dir, MITM_LOG)
        self.proc = None
        self.guard = ProxyGuard(self.data_dir, proxy=f"127.0.0.1:{self.port}",
                               verbose=verbose)
        self._seen = set()

    def _log(self, msg):
        if self.verbose:
            print(f"[capture] {msg}")

    # ------------------------------------------------------------ 起停
    def start(self, skip_proxy=False):
        exe = find_mitm()
        addon = addon_path()
        upstream = os.environ.get("LEPAO_MITM_UPSTREAM", "").strip()
        cmd = [exe, "-q", "-s", addon, "-p", str(self.port), "--ssl-insecure"]
        if upstream:
            cmd += ["--mode", f"upstream:http://{upstream}"]
        if not skip_proxy:
            self.guard.enable()
        os.makedirs(self.data_dir, exist_ok=True)
        logf = open(self.log_path, "a", encoding="utf-8", errors="replace")
        self._log(f"启动 mitm: {os.path.basename(exe)} -p {self.port}")
        try:
            env = dict(os.environ)
            env["LEPAO_CONFIG"] = self.reg.config_path
            env["LEPAO_DATA_DIR"] = self.data_dir
            self.proc = subprocess.Popen(
                cmd, stdout=logf, stderr=subprocess.STDOUT, env=env,
                creationflags=(0x08000000 if sys.platform == "win32" else 0))
        except Exception:
            logf.close()
            self.guard.restore()
            raise
        self._log(f"链已在位: 系统代理 → 127.0.0.1:{self.port} "
                  f"(日志 {os.path.basename(self.log_path)})")
        self._log("请打开电脑微信 → 小程序「数体智慧体育」→ 进入跑步首页（勿重复登录，会顶号）")
        self._seen = {_fingerprint(r) for r in _read_creds(self.cred_path)}
        return self

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            except Exception:
                pass
            self.proc = None
            self._log("mitm 已停止")
        self.guard.restore()

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    # ------------------------------------------------------------ 等号
    def wait_token(self, timeout=None):
        """轮询凭证文件，返回最新一条**本次会话新增**的凭证 dict；超时返回 None。"""
        deadline = time.time() + (timeout or self.timeout)
        last_note = 0.0
        while time.time() < deadline:
            recs = _read_creds(self.cred_path)
            fresh = [r for r in recs if _fingerprint(r) not in self._seen]
            if fresh:
                rec = fresh[-1]
                self._seen.add(_fingerprint(rec))
                self._log(f"捕获到登录凭证 uid={rec.get('uid')} "
                          f"学号={rec.get('student_num') or '-'} at={rec.get('at')}")
                return rec
            if self.proc is not None and self.proc.poll() is not None:
                raise AccountError(
                    f"mitm 进程已退出(exit={self.proc.returncode})，见 {self.log_path}")
            now = time.time()
            if now - last_note > 20:
                left = int(deadline - now)
                self._log(f"等待登录流量…（剩余 {left}s；抓不到先查 `cli.py cert`）")
                last_note = now
            time.sleep(1.0)
        self._log("等待超时：未捕获登录流量")
        return None

    # ------------------------------------------------------------ 归位
    def sync(self, cred):
        """把一份凭证归位到成员槽。返回 (member_key, AuthState)。"""
        if not isinstance(cred, dict) or not cred.get("token"):
            raise AccountError("凭证内容不完整（缺 token）")
        key = self.reg.key_of_cred(cred)
        if key is None:
            raise AccountError(
                f"该凭证的身份未登记（uid={cred.get('uid')} "
                f"学号={cred.get('student_num')}）→ 先 `account add <名字> <学号>` 登记")
        self.reg.fill_identity(key, uid=cred.get("uid"), school_id=cred.get("school_id"),
                              student_num=cred.get("student_num"),
                              card_id=cred.get("card_id"), name=cred.get("name"))
        st = AuthState(self.reg, key)
        st.set_token(cred["token"], issued_at=cred.get("at"),
                     source=cred.get("source") or "mitm",
                     refresh_token=cred.get("refresh_token"),
                     refresh_expire=cred.get("refresh_expire"))
        self._log(f"token 已归位 → [{st.label}]")
        return key, st

    def capture(self, timeout=None, probe=True, on_ready=None):
        """一键: 起链 → [可选自动开小程序] → 等号 → 归位 → 收链。
        返回 (key, AuthState) 或 (None, None)。
        on_ready: start 之后、等号之前调用的回调（用于无人值守拉起小程序）。"""
        try:
            self.start()
            if on_ready is not None:
                try:
                    on_ready()
                except Exception as e:  # noqa: BLE001 - 自动开失败退回人工开
                    self._log(f"自动打开小程序失败（改人工开）: {e}")
            cred = self.wait_token(timeout)
            if not cred:
                return None, None
            key, st = self.sync(cred)
            if probe:
                st.probe()
            return key, st
        finally:
            self.stop()
