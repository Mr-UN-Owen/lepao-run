# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
"""本地 Web 控制台（零依赖）：给 lepao 协议栈套一层可点的界面。

设计目标与 bupt-run 那类桌面 EXE 等价，但形态换成「本机网页」：
  - 不打包、不写注册表、不需要 Tk；双击 `启动控制台.bat` 或 `py -3 app/server.py` 即可
  - 界面只调 `lepao` 既有分层（AccountRegistry / AuthState / Pipeline / StateStore），不碰协议
  - 干跑默认零写入，提交必须显式点「提交」并二次确认

接口：
  GET  /                  控制台页面
  GET  /api/state         成员表 / token 状态 / 运行态 / AES 后端
  GET  /api/log?since=N   增量日志
  POST /api/account/add   {name, student_num}
  POST /api/account/remove{sel}
  POST /api/account/active{sel}
  POST /api/token         {member, token}      人工装载（调试用）
  POST /api/run           {member, submit}     submit=false 为干跑
  POST /api/stop          中止当前任务
"""
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lepao import crypto                                    # noqa: E402
from lepao.accounts import AccountRegistry, AccountError    # noqa: E402
from lepao.auth import AuthState                             # noqa: E402
from lepao.h5api import H5Client                             # noqa: E402
from lepao.pipeline import Pipeline                          # noqa: E402
from lepao.state import StateStore                            # noqa: E402
from lepao.v3api import V3Error                               # noqa: E402

CONFIG = os.path.join(ROOT, "config.json")
STATE = os.path.join(ROOT, "state.json")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

LOG = []
LOG_LOCK = threading.Lock()
STOP = threading.Event()
TASK = {"running": False, "kind": "", "member": "", "started": 0, "code": None, "result": ""}
TASK_LOCK = threading.Lock()
MAX_LOG = 3000

# H5 面（账号密码登录）会话：单用户本地场景，进程内保存即可
H5 = {
    "client": None,      # H5Client 实例（持有 PHPSESSID）
    "v_token": "",       # 验证码 v-token
    "png": b"",          # 最近一张验证码 PNG
    "school_id": 0,
    "account": "",
    "logged_in": False,
    "info": "",
    "probe": {},         # 登录后各 H5 接口可达性
}


def log(msg):
    line = {"t": time.strftime("%H:%M:%S"), "m": str(msg)}
    with LOG_LOCK:
        LOG.append(line)
        if len(LOG) > MAX_LOG:
            del LOG[: MAX_LOG // 2]


def registry(create=True):
    return AccountRegistry(CONFIG, create=create, verbose=False)


def _snapshot():
    try:
        reg = registry(create=False)
    except Exception as e:  # 配置损坏也要能开界面
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "members": [],
                "active": "", "backend": crypto.backend()}
    members = []
    for key, prof in (reg.accounts or {}).items():
        a = (prof or {}).get("auth") or {}
        token = a.get("token") or ""
        if a.get("consumed_at"):
            tstate = "consumed"
        elif token:
            tstate = "ready"
        else:
            tstate = "empty"
        members.append({
            "key": key,
            "name": (prof or {}).get("name") or key,
            "alias": (prof or {}).get("alias") or "",
            "uid": (prof or {}).get("uid") or 0,
            "school_id": (prof or {}).get("school_id") or 0,
            "token": tstate,
            "issued_at": a.get("issued_at") or "",
            "enabled": bool((prof or {}).get("enabled", True)),
        })
    env = reg.environment or {}
    return {
        "ok": True,
        "members": members,
        "active": reg.active or "",
        "backend": crypto.backend(),
        "api_host": env.get("api_host") or "",
        "app_key": env.get("app_key") or "",
        "policy": reg.config.get("policy") or {},
        "task": dict(TASK),
        "h5": h5_state(),
    }


def _do_run(member, submit):
    try:
        STOP.clear()
        with TASK_LOCK:
            TASK.update({"running": True, "member": member, "started": int(time.time()),
                         "code": None, "result": ""})
        reg = registry()
        key = reg.resolve(member)
        st = AuthState(reg, key)
        pipe = Pipeline(st, StateStore(STATE), policy=reg.policy_of(key),
                        verbose=True, log_fn=log, stop_event=STOP)
        log("=" * 46)
        log(f"{'提交' if submit else '干跑'} 开始：{reg.describe(key)}")
        summary, code = pipe.run(submit=submit)
        with TASK_LOCK:
            TASK.update({"code": code, "result": summary if isinstance(summary, str) else str(summary)})
        log(f"结束，退出码 {code}")
    except V3Error as e:
        with TASK_LOCK:
            TASK.update({"code": getattr(e, "code", -1), "result": str(e)})
        log(f"[FATAL] V3Error {getattr(e, 'code', '')}: {e}")
    except AccountError as e:
        log(f"[FATAL] {e}")
        with TASK_LOCK:
            TASK.update({"code": -2, "result": str(e)})
    except Exception as e:  # noqa: BLE001 - 界面要把任何异常显示出来
        log(f"[FATAL] {type(e).__name__}: {e}")
        log(traceback.format_exc(limit=6))
        with TASK_LOCK:
            TASK.update({"code": -3, "result": f"{type(e).__name__}: {e}"})
    finally:
        with TASK_LOCK:
            TASK["running"] = False


def h5_state():
    return {
        "logged_in": H5["logged_in"],
        "account": H5["account"] if H5["logged_in"] else "",
        "school_id": H5["school_id"],
        "info": H5["info"],
        "has_captcha": bool(H5["png"]),
        "probe": H5["probe"],
    }


def h5_ensure_client(school_id=0):
    sid = int(school_id or 0)
    if H5["client"] is None or (sid and sid != H5["school_id"]):
        H5["client"] = H5Client(school_id=sid or 837)
        H5["school_id"] = sid or 837
        H5["logged_in"] = False
        H5["probe"] = {}
    return H5["client"]


def h5_captcha(school_id=0):
    """取一张新验证码（v-token + PNG）。返回 data URL 供前端 <img> 直接显示。"""
    c = h5_ensure_client(school_id)
    st, j = c.get("/index/Login/getToken")
    v_token = (j or {}).get("code") if isinstance(j, dict) else ""
    if not v_token:
        raise RuntimeError(f"取 v-token 失败: {st} {str(j)[:120]}")
    H5["v_token"] = v_token
    st, png = c.get(f"/index/Login/verify?token={v_token}&random={int(time.time() * 1000)}", raw=True)
    if not isinstance(png, (bytes, bytearray)) or len(png) < 200:
        raise RuntimeError(f"取验证码失败: {st} {str(png)[:120]}")
    H5["png"] = bytes(png)
    import base64
    return "data:image/png;base64," + base64.b64encode(H5["png"]).decode()


def h5_login(account, password, verify, school_id=0):
    """账号 + 密码 + 验证码 → PHPSESSID 会话（login_type=2 = 学号/账号密码）。"""
    c = h5_ensure_client(school_id)
    st, j = c.call("Login", "login", {
        "school_id": c.school_id,
        "student_num": account,
        "password": password,
        "verify": verify,
        "login_type": 2,
        "token": H5["v_token"],
    })
    ok = isinstance(j, dict) and j.get("status") == 1
    H5["logged_in"] = bool(ok)
    H5["account"] = account if ok else ""
    H5["info"] = ((j or {}).get("info") if isinstance(j, dict) else str(j)[:150]) or ""
    log(f"[H5] 登录{'成功' if ok else '失败'}: {account} → {H5['info'] or 'status=' + str((j or {}).get('status'))}")
    return ok, j


def h5_probe():
    """登录后用 PHPSESSID 探一遍 H5 接口可达性 —— 直接回答“能不能改数据”。"""
    if not H5["logged_in"] or H5["client"] is None:
        raise RuntimeError("尚未登录，先取验证码并登录")
    c = H5["client"]
    out = {}
    for name, mod, meth, params in [
        ("checkLogin", "Index", "checkLogin", {}),
        ("getStudentScore", "Report", "getStudentScore", {"year_num": "2025"}),
        ("Offline_index", "Offline", "index", {}),
    ]:
        try:
            st, j = c.call(mod, meth, dict(params))
            if isinstance(j, dict):
                out[name] = {"status": j.get("status"), "info": (j.get("info") or "")[:120],
                             "keys": list(j.keys())[:6]}
            else:
                out[name] = {"http": st, "raw": str(j)[:120]}
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": f"{type(e).__name__}: {e}"}
    H5["probe"] = out
    return out


def start_task(member, submit):
    with TASK_LOCK:
        if TASK["running"]:
            raise RuntimeError("已有任务在跑，先停止或等待结束")
        TASK.update({"running": True, "kind": "submit" if submit else "dryrun",
                     "member": member, "started": int(time.time()), "code": None, "result": ""})
    t = threading.Thread(target=_do_run, args=(member, submit), daemon=True)
    t.start()


class Handler(BaseHTTPRequestHandler):
    server_version = "lepao-console"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------- 基础
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):  # 静音默认访问日志
        pass

    # ---------------------------------------------------------- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(INDEX, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError as e:
                self._send(500, f"index.html 缺失: {e}", "text/plain; charset=utf-8")
            return
        if path == "/api/state":
            self._send(200, _snapshot())
            return
        if path == "/api/h5/state":
            self._send(200, {"ok": True, "h5": h5_state()})
            return
        if path == "/api/h5/captcha":
            sid = 0
            if "school_id=" in self.path:
                try:
                    sid = int(self.path.split("school_id=", 1)[1].split("&")[0])
                except ValueError:
                    sid = 0
            try:
                img = h5_captcha(sid)
            except Exception as e:  # noqa: BLE001
                self._send(502, {"ok": False, "error": f"{type(e).__name__}: {e}"})
                return
            self._send(200, {"ok": True, "image": img, "h5": h5_state()})
            return
        if path == "/api/log":
            since = 0
            if "since=" in self.path:
                try:
                    since = int(self.path.split("since=", 1)[1].split("&")[0])
                except ValueError:
                    since = 0
            with LOG_LOCK:
                chunk = LOG[since:]
                total = len(LOG)
            self._send(200, {"total": total, "lines": chunk})
            return
        self._send(404, {"error": "not found"})

    # ---------------------------------------------------------- POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        data = self._body()
        try:
            if path == "/api/account/add":
                reg = registry()
                key = reg.add(data.get("name") or "", data.get("student_num") or "")
                self._send(200, {"ok": True, "key": key, "state": _snapshot()})
                return
            if path == "/api/account/remove":
                reg = registry()
                key = reg.remove(data.get("sel") or "")
                self._send(200, {"ok": True, "key": key, "state": _snapshot()})
                return
            if path == "/api/account/active":
                reg = registry()
                reg.active = reg.resolve(data.get("sel") or "")
                reg.persist()
                self._send(200, {"ok": True, "state": _snapshot()})
                return
            if path == "/api/token":
                reg = registry()
                key = reg.resolve(data.get("member") or "")
                st = AuthState(reg, key)
                st.token = (data.get("token") or "").strip()
                st.source = "manual"
                st.issued_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                st.consumed_at = ""
                reg.persist()
                self._send(200, {"ok": True, "state": _snapshot()})
                return
            if path == "/api/run":
                member = data.get("member") or ""
                submit = bool(data.get("submit"))
                start_task(member, submit)
                log(f"任务已排队：{'提交' if submit else '干跑'} / {member or '(active)'}")
                self._send(200, {"ok": True})
                return
            if path == "/api/h5/login":
                ok, j = h5_login(
                    (data.get("account") or "").strip(),
                    data.get("password") or "",
                    (data.get("verify") or "").strip(),
                    data.get("school_id") or 0,
                )
                self._send(200 if ok else 401, {
                    "ok": ok,
                    "info": H5["info"],
                    "raw": j if isinstance(j, dict) else str(j)[:200],
                    "h5": h5_state(),
                })
                return
            if path == "/api/h5/probe":
                try:
                    probe = h5_probe()
                except Exception as e:  # noqa: BLE001
                    self._send(400, {"ok": False, "error": f"{type(e).__name__}: {e}"})
                    return
                self._send(200, {"ok": True, "probe": probe, "h5": h5_state()})
                return
            if path == "/api/stop":
                STOP.set()
                log("已请求停止（当前任务在下一个检查点退出）")
                self._send(200, {"ok": True})
                return
        except AccountError as e:
            self._send(400, {"ok": False, "error": str(e)})
            return
        except RuntimeError as e:
            self._send(409, {"ok": False, "error": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            log(f"[UI] {type(e).__name__}: {e}")
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})
            return
        self._send(404, {"ok": False, "error": "not found"})


def main():
    port = 8770
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    host = "127.0.0.1"
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"[lepao-console] http://{host}:{port}  AES后端={crypto.backend()}")
    print(f"[lepao-console] 配置 {CONFIG}")
    print("[lepao-console] Ctrl+C 退出")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[lepao-console] 已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
