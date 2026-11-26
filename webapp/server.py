# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
"""webapp —— 乐跑网页控制台（登录 → 看数据 → 生成轨迹 → 提交）

启动：python webapp/server.py --port 8780
形态对标 bupt.run 那类「输入账号/凭证就能登进来看数据」的网页，但逻辑全部走本仓库自己的
v3 协议实现（不依赖任何第三方服务）。

登录方式：
  · Token 登录（推荐）—— 填 host / school_id / uid / token，直接可用
  · 账号密码登录 —— H5 面（PHPSESSID），只能查成绩，不能提交 v3 轨迹
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from lplib import Session, V3Error            # noqa: E402
from lepao import crypto                      # noqa: E402

SESSION_FILE = os.path.join(REPO, "_private", "webapp_session.json")
INDEX = os.path.join(HERE, "index.html")

S = {"sess": None, "lock": threading.Lock()}


def save_session(sess):
    if sess is None:
        try:
            os.remove(SESSION_FILE)
        except OSError:
            pass
        return
    data = {
        "host": sess.host, "school_id": sess.school_id, "uid": sess.uid,
        "token": sess.token, "student_num": sess.student_num,
        "term_id": sess.term_id, "school_name": sess.school_name,
        "refresh_token": getattr(sess, "refresh_token", ""),
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_session():
    if not os.path.isfile(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            d = json.load(f)
        s = Session(host=d.get("host", "api3.lptiyu.com"), school_id=d.get("school_id", 816),
                    uid=d.get("uid", ""), token=d.get("token", ""),
                    student_num=d.get("student_num", ""))
        s.term_id = int(d.get("term_id") or 0)
        s.school_name = d.get("school_name") or ""
        s.refresh_token = d.get("refresh_token") or ""
        return s
    except Exception:
        return None


# ---------------------------------------------------------------- 一键抓凭证
# 复刻 capture_launcher 的安全顺序：先起 MITM 确认监听，才设代理；任何退出路径都恢复原值。
MITM = os.path.join(REPO, "工具", "mitm_debug_proxy.py")
CAP = {"proc": None, "orig": None, "started": 0.0, "running": False,
       "baseline": 0, "port": 8086, "msg": "", "pending": None}
CAP_LOCK = threading.Lock()


PS_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _read_proxy():
    """读代理设置：优先 reg query（不依赖 winreg 权限）。"""
    out = {"enable": 0, "server": "", "override": ""}
    try:
        r = subprocess.run(["reg", "query", PS_KEY], capture_output=True, text=True, timeout=10)
        for line in (r.stdout or "").splitlines():
            parts = [p for p in line.split("    ") if p.strip()]
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
    except Exception:
        pass
    return out


def _write_proxy(enable, server=None, override=None):
    """写代理设置：用 reg.exe（winreg 直连常被安全软件拦成 WinError 5）。"""

    def reg(*args):
        r = subprocess.run(["reg", *args], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            msg = ((r.stdout or "") + (r.stderr or "")).strip()
            raise RuntimeError(msg or f"reg 返回 {r.returncode}")
        return r

    reg("add", PS_KEY, "/v", "ProxyEnable", "/t", "REG_DWORD", "/d", str(int(enable)), "/f")
    if server is not None:
        reg("add", PS_KEY, "/v", "ProxyServer", "/t", "REG_SZ", "/d", server, "/f")
    if override is not None:
        reg("add", PS_KEY, "/v", "ProxyOverride", "/t", "REG_SZ", "/d", override, "/f")
    try:
        import ctypes
        w = ctypes.windll.wininet
        w.InternetSetOptionW(0, 39, 0, 0)
        w.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass


def _port_open(port, timeout=0.4):
    import socket as _s
    try:
        c = _s.create_connection(("127.0.0.1", port), timeout=timeout)
        c.close()
        return True
    except Exception:
        return False


def _log_lines():
    path = os.path.join(REPO, "_private", "capture_log.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [ln for ln in f if ln.strip()]


def capture_start(port=8086, skip_proxy=False):
    with CAP_LOCK:
        if CAP["running"]:
            return {"ok": False, "error": "已经在抓取中"}
        if _port_open(port):
            return {"ok": False, "error": f"端口 {port} 被占用，先关掉之前的抓包窗口"}
        CAP["orig"] = _read_proxy()
        CAP["baseline"] = len(_log_lines())
        CAP["port"] = port
        env = dict(os.environ)
        env["PATH"] = r"D:\msys2\mingw64\bin;D:\msys2\usr\bin;" + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-u", MITM, "--port", str(port)],
                                cwd=REPO, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 先确认监听，才动系统代理
        ok = False
        for _ in range(100):
            if _port_open(port):
                ok = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.15)
        if not ok:
            try:
                proc.kill()
            except Exception:
                pass
            return {"ok": False, "error": "MITM 没起来，代理设置一个字都没动"}

        if not skip_proxy:
            try:
                _write_proxy(1, f"127.0.0.1:{port}")
            except Exception as e:  # noqa: BLE001 - 权限不足时给手动兜底
                try:
                    proc.kill()
                except Exception:
                    pass
                return {"ok": False, "need_manual": True,
                        "error": f"自动改系统代理失败（{e}）。",
                        "hint": f"手动把 Windows 代理设为 127.0.0.1:{port}，然后点「我已设好代理」。"}
        CAP.update(proc=proc, running=True, started=time.time(),
                   msg="MITM 已就绪，请打开小程序")
        threading.Thread(target=_capture_watch, daemon=True).start()
        return {"ok": True, "port": port}


def capture_stop(reason=""):
    with CAP_LOCK:
        if not CAP["running"] and CAP["proc"] is None:
            return
        CAP["running"] = False
        try:
            if CAP["orig"]:
                _write_proxy(CAP["orig"]["enable"], CAP["orig"]["server"], CAP["orig"]["override"])
        except Exception:
            pass
        p = CAP["proc"]
        CAP["proc"] = None
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if reason:
            CAP["msg"] = reason


def _capture_watch():
    """轮询抓包日志，一出现带 token 的 v3 明文就收工；**先恢复代理再验证**。"""
    deadline = time.time() + 240
    cand = None
    while CAP["running"] and time.time() < deadline:
        time.sleep(1.0)
        lines = _log_lines()
        if len(lines) <= CAP["baseline"]:
            continue
        for ln in lines[CAP["baseline"]:]:
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            pl = rec.get("plain") or {}
            c = _extract_cred(pl)
            if not c:
                continue
            # 只记候选，取最后一条（最新的登录状态）
            cand = {"host": rec.get("host") or "api3.lptiyu.com",
                    "school_id": c["school_id"], "uid": c["uid"], "token": c["token"],
                    "refresh_token": c["refresh_token"],
                    "refresh_expire": c["refresh_expire"],
                    "student_num": c["student_num"]}
        CAP["baseline"] = len(lines)
        if cand:
            break

    capture_stop("已抓到凭证")          # 先恢复代理、杀掉 MITM
    if not cand:
        CAP["msg"] = "超时未抓到凭证，已恢复代理"
        return
    time.sleep(0.6)                      # 等代理设置真正生效
    sess = Session(host=cand["host"], school_id=cand["school_id"], uid=cand["uid"],
                   token=cand["token"], student_num=cand["student_num"])
    sess.refresh_token = cand.get("refresh_token") or ""
    try:
        sess.get_terms()
        sess.profile()
    except V3Error as e:
        CAP["msg"] = f"抓到了凭证但验证失败：{e}"
        return
    # 验证通过：不直接登录，把凭证交给前端填进登录框（用户自己点「登录」）
    CAP["pending"] = cand
    CAP["msg"] = "凭证已获取，已填入登录框"


def _extract_cred(pl):
    """从 v3 明文里取凭证。loginByCode 的 token 在 token_data 里，不是顶层 token。

    返回 dict(token, uid, refresh_token, refresh_expire, student_num, school_id) 或 None。
    """
    if not isinstance(pl, dict):
        return None
    pools = [pl]
    for k in ("token_data", "data", "user", "auth_data"):
        v = pl.get(k)
        if isinstance(v, dict):
            pools.append(v)
    tok = uid = rt = ""
    exp = 0
    for p in pools:
        tok = tok or str(p.get("token") or p.get("access_token") or "")
        uid = uid or str(p.get("uid") or p.get("user_id") or "")
        rt = rt or str(p.get("refresh_token") or "")
        try:
            exp = exp or int(p.get("refresh_expire") or 0)
        except (TypeError, ValueError):
            pass
    if not tok or not uid:
        return None
    return {"token": tok, "uid": uid, "refresh_token": rt, "refresh_expire": exp,
            "student_num": str(pl.get("student_num") or ""),
            "school_id": pl.get("school_id") or 0}


def last_capture():
    """从抓包日志里翻出最近一条带 token 的 v3 明文，供登录页自动预填。"""
    path = os.path.join(REPO, "_private", "capture_log.jsonl")
    if not os.path.isfile(path):
        return None
    best = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                c = _extract_cred(rec.get("plain") or {})
                if not c:
                    continue
                best = {
                    "host": rec.get("host") or "api3.lptiyu.com",
                    "school_id": c["school_id"],
                    "uid": c["uid"],
                    "token": c["token"],
                    "refresh_token": c["refresh_token"],
                    "refresh_expire": c["refresh_expire"],
                    "student_num": c["student_num"],
                    "at": rec.get("t") or "",
                }
    except OSError:
        return None
    return best


def today_count(sess):
    """今天已经提交过几条（含无效）。翻页统计——服务端每页固定 10 条，只数第一页会漏。"""
    today = datetime.date.today()
    n = 0
    for page in range(1, 7):
        try:
            data = sess.records(page=page, limit=10)
        except V3Error:
            break
        lst = data.get("list") if isinstance(data, dict) else data
        if not lst:
            break
        for r in lst:
            ts = r.get("start_time") or r.get("time") or r.get("run_time")
            try:
                ts = int(float(ts))
            except (TypeError, ValueError):
                continue
            try:
                if datetime.datetime.fromtimestamp(ts).date() == today:
                    n += 1
            except (OSError, ValueError):
                continue
        if len(lst) < 10:
            break
    return n


# ---------------------------------------------------------------- 轨迹合成
def haversine_m(lat1, lng1, lat2, lng2):
    import math
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _stadium_loop(points):
    """跑道几何（一圈）—— 移植自 run.bupt.app 的 Qt() 模型。

    原版：
        Bt = 6371e3*PI/180           每度纬度米数
        Vt = Bt*cos(lat)             每度经度米数
        A  = Wt/2                    半直道（Wt = 两端点距离）
        R  = 40.82                   弯道半径
        Jt(e,t) 局部坐标 → 经纬度
        Qt()    上半圈 41 点 + 下半圈 41 点 + 闭合
    返回 (loop, acc, per)：loop 为一圈经纬度，acc 为累积弧长，per 为周长。
    """
    import math
    if not points:
        raise ValueError("没有打卡点")
    if len(points) >= 2:
        lat1, lng1 = points[0]["lat"], points[0]["lng"]
        lat2, lng2 = points[-1]["lat"], points[-1]["lng"]
    else:
        lat1, lng1 = points[0]["lat"], points[0]["lng"]
        lat2, lng2 = lat1 + 0.0009, lng1

    clat, clng = (lat1 + lat2) / 2.0, (lng1 + lng2) / 2.0
    Bt = 6371000.0 * math.pi / 180.0
    Vt = Bt * math.cos(math.radians(clat))
    Ht = (lng1 - lng2) * Vt
    Ut = (lat1 - lat2) * Bt
    Wt = math.hypot(Ht, Ut)
    if Wt < 20:
        Ht, Ut, Wt = 0.0, 120.0, 120.0
    A = Wt / 2.0
    R = 40.82
    ux, uy = Ht / Wt, Ut / Wt

    def to_ll(e, t):
        return [clat + (uy * t - ux * e) / Bt, clng + (ux * t + uy * e) / Vt]

    loop = []
    for i in range(41):
        ang = math.pi * i / 40
        loop.append(to_ll(R * math.cos(ang), A + R * math.sin(ang)))
    for i in range(41):
        ang = math.pi + math.pi * i / 40
        loop.append(to_ll(R * math.cos(ang), -A + R * math.sin(ang)))
    loop.append(loop[0])

    acc = [0.0]
    for i in range(1, len(loop)):
        acc.append(acc[-1] + haversine_m(loop[i - 1][0], loop[i - 1][1],
                                         loop[i][0], loop[i][1]))
    return loop, acc, acc[-1]


def build_run(points, target_km, pace, seed=None):
    """生成一条"像真人跑"的轨迹。

    关键：**按时间采样（1 Hz）而不是按距离采样**。
    速度由 realism.speed_curve 给出（含热身/冷却/±6% 抖动/偶发停顿），
    再沿跑道弧长推进 → 点间距、时间轴、步频分布自然变得不规则。

    返回 (pts, km, used, speeds)，pts 元素：{"a":lat, "o":lng, "t":秒}
    """
    import bisect
    import math as _m
    import random as _rnd
    from lepao import realism

    rnd = _rnd.Random(seed)
    loop, acc, per = _stadium_loop(points)
    base_v = 1000.0 / float(pace)                 # m/s
    target_m = float(target_km) * 1000.0
    total_s = max(int(target_m / base_v), 30)
    speeds = realism.speed_curve(base_v, total_s, rnd)

    noise_m = float(realism.REALISM["gps_noise_m"])
    drift_m = float(realism.REALISM["lap_drift_m"])

    pts = []
    cum = 0.0
    for t, v in enumerate(speeds):
        cum += v
        s0 = cum % per
        lap = int(cum // per)
        i = bisect.bisect_right(acc, s0) - 1
        i = max(0, min(i, len(loop) - 2))
        seg = acc[i + 1] - acc[i]
        f = (s0 - acc[i]) / seg if seg > 0 else 0.0
        lat = loop[i][0] + (loop[i + 1][0] - loop[i][0]) * f
        lng = loop[i][1] + (loop[i + 1][1] - loop[i][1]) * f
        # 每圈横向漂移（真人不会踩同一条线）
        if drift_m:
            off = drift_m * (((lap % 3) - 1) / 1.5)
            lat += off / 111320.0
        # GPS 噪声（远小于点间距，否则画出来是锯齿）
        lat += rnd.uniform(-noise_m, noise_m) / 111320.0
        lng += rnd.uniform(-noise_m, noise_m) / (111320.0 * _m.cos(_m.radians(lat)))
        pts.append({"a": round(lat, 6), "o": round(lng, 6), "t": t})
        if cum >= target_m:
            break

    real_m = 0.0
    for i in range(1, len(pts)):
        real_m += haversine_m(pts[i - 1]["a"], pts[i - 1]["o"],
                              pts[i]["a"], pts[i]["o"])
    return pts, real_m / 1000.0, len(pts), speeds


def build_loop(points, target_m, step_m=8.0, seed=None):
    """兼容旧调用：只要坐标序列。"""
    pts, _km, _used, _sp = build_run(points, target_m / 1000.0, 310, seed)
    return [(p["a"], p["o"]) for p in pts]


def make_track(preview):
    """兼容旧调用：给了 coords 就按配速补时间轴（新代码请直接用 build_run）。"""
    coords = preview["coords"]
    pace = preview["pace"]
    dist_m = 0.0
    pts = []
    t = 0.0
    for i, (lat, lng) in enumerate(coords):
        if i:
            pl, pg = coords[i - 1]
            d = haversine_m(pl, pg, lat, lng)
            dist_m += d
            t += d / 1000.0 * pace
        pts.append({"a": lat, "o": lng, "t": int(t)})
    return pts, dist_m / 1000.0, int(t)


def cover_points(coords, points, radius_m):
    hit = []
    for p in points:
        for (lat, lng) in coords:
            if haversine_m(p["lat"], p["lng"], lat, lng) <= radius_m:
                hit.append(p)
                break
    return hit


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "lepao-webapp"
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
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

    def log_message(self, fmt, *args):
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
        if path == "/auto":
            # 绕过前端：用最近抓到的凭证直接登录，然后跳回主页
            cand = CAP.get("pending") or last_capture()
            if not cand:
                self._send(200, "还没抓到凭证。先点「一键获取凭证」。", "text/plain; charset=utf-8")
                return
            sess = Session(host=cand.get("host") or "api3.lptiyu.com",
                           school_id=cand.get("school_id") or 816,
                           uid=str(cand.get("uid") or ""),
                           token=cand.get("token") or "",
                           student_num=str(cand.get("student_num") or ""))
            try:
                sess.get_terms()
                sess.profile()
            except V3Error as e:
                self._send(200, f"用最近凭证登录失败：{e}\n\n请重新点「一键获取凭证」。",
                           "text/plain; charset=utf-8")
                return
            S["sess"] = sess
            save_session(sess)
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/api/me":
            sess = S["sess"]
            if not sess:
                self._send(401, {"ok": False, "error": "未登录"})
                return
            try:
                prof = sess.profile()
                prof["today_count"] = today_count(sess)
            except V3Error as e:
                self._send(200, {"ok": False, "error": str(e), "need_login": e.status == 101})
                return
            self._send(200, {"ok": True, "profile": prof})
            return
        if path == "/api/last-capture":
            self._send(200, {"ok": True, "capture": last_capture()})
            return
        if path == "/api/records":
            sess = S["sess"]
            if not sess:
                self._send(401, {"ok": False, "error": "未登录"})
                return
            try:
                data = sess.records()
            except V3Error as e:
                self._send(200, {"ok": False, "error": str(e)})
                return
            self._send(200, {"ok": True, "records": data})
            return
        self._send(404, {"ok": False, "error": "not found"})

    # ---------------------------------------------------------- POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        data = self._body()

        if path == "/api/login":
            token = (data.get("token") or "").strip()
            uid = str(data.get("uid") or "").strip()
            school = data.get("school_id") or 0
            host = (data.get("host") or "api3.lptiyu.com").strip()
            stu = (data.get("student_num") or "").strip()
            if not token or not uid:
                self._send(400, {"ok": False, "error": "token 和 uid 都要填"})
                return
            sess = Session(host=host, school_id=school or 0, uid=uid, token=token,
                           student_num=stu, card_id=stu)
            sess.refresh_token = (data.get("refresh_token") or "").strip()
            try:
                sess.get_terms()
                prof = sess.profile()
                prof["today_count"] = today_count(sess)
            except V3Error as e:
                self._send(401, {"ok": False, "error": str(e)})
                return
            S["sess"] = sess
            save_session(sess)
            self._send(200, {"ok": True, "profile": prof,
                             "refresh_saved": bool(sess.refresh_token)})
            return

        if path == "/api/refresh":
            sess = S["sess"]
            if not sess:
                self._send(401, {"ok": False, "error": "未登录"})
                return
            rt = (data.get("refresh_token") or "").strip() or getattr(
                sess, "refresh_token", "")
            if not rt:
                self._send(400, {"ok": False,
                                 "error": "无 refresh_token：请在抓号后填入，或重新 capture 一次"})
                return
            try:
                at, new_rt, exp = sess.refresh(rt)
                sess.refresh_token = new_rt
                sess.get_terms()
                prof = sess.profile()
                prof["today_count"] = today_count(sess)
            except V3Error as e:
                self._send(200, {"ok": False, "error": str(e), "need_recapture": True})
                return
            save_session(sess)
            self._send(200, {"ok": True, "profile": prof,
                             "token_mask": at[:6] + "…" + at[-4:],
                             "refresh_expire": exp})
            return

        if path == "/api/capture/start":
            r = capture_start(int(data.get("port") or 8086), bool(data.get("skip_proxy")))
            self._send(200 if r.get("ok") else 409, r)
            return
        if path == "/api/capture/status":
            self._send(200, {"ok": True, "running": CAP["running"],
                             "msg": CAP["msg"],
                             "pending": CAP["pending"],
                             "elapsed": int(time.time() - CAP["started"]) if CAP["started"] else 0,
                             "logged_in": bool(S["sess"])})
            return
        if path == "/api/capture/stop":
            capture_stop("已手动停止，代理已恢复")
            self._send(200, {"ok": True})
            return
        if path == "/api/logout":
            S["sess"] = None
            save_session(None)
            self._send(200, {"ok": True})
            return

        if path == "/api/preview":
            sess = S["sess"]
            if not sess:
                self._send(401, {"ok": False, "error": "未登录"})
                return
            br = sess.last_before_run
            if not br:
                try:
                    br = sess.before_run() or {}
                except V3Error as e:
                    self._send(200, {"ok": False, "error": str(e)})
                    return
            rule = (br.get("run_line_info") or {})
            all_pts = []
            for p in rule.get("point_list") or []:
                jw = str(p.get("jingwei") or "")
                if "," not in jw:
                    continue
                try:
                    lat, lng = float(jw.split(",")[0]), float(jw.split(",")[1])
                except ValueError:
                    continue
                all_pts.append({"id": str(p.get("id")), "name": p.get("address") or "",
                                "lat": lat, "lng": lng})
            if len(all_pts) < 2:
                self._send(400, {"ok": False, "error": "打卡点不足 2 个，无法规划"})
                return
            want = int((rule.get("point_num") or 2))
            picked = random.sample(all_pts, min(want, len(all_pts)))
            dist_km = float(data.get("distance_km") or 2.6)
            pace = int(data.get("pace") or 330)          # 秒/公里，330 = 5'30"
            pts, real_km, used, speeds = build_run(picked, dist_km, pace,
                                                   seed=data.get("seed"))
            coords = [(p["a"], p["o"]) for p in pts]
            radius = float((rule.get("log_max_distance") or 100))
            hit = cover_points([(c["a"], c["o"]) for c in pts], picked, radius)
            S["last_preview"] = {
                "pts": pts, "points": picked, "distance_km": real_km,
                "used_time": used, "pace": pace, "game_id": str(br.get("game_id") or "7"),
                "zone_id": str(br.get("run_zone_id") or ""),
                "speeds": speeds,
            }
            from lepao import realism as _R
            _sum = _R.summarize(speeds)
            self._send(200, {"ok": True, "preview": {
                "points": picked,
                "coords": [[c["a"], c["o"]] for c in pts[:2000]],
                "n": len(pts),
                "distance_km": round(real_km, 3),
                "used_time": used,
                "pace": pace,
                "covered": [h["id"] for h in hit],
                "covered_all": len(hit) == len(picked),
                "radius": radius,
                "speed_stats": _sum,
            }})
            return

        if path == "/api/submit":
            sess = S["sess"]
            if not sess:
                self._send(401, {"ok": False, "error": "未登录"})
                return
            if not data.get("confirm"):
                self._send(400, {"ok": False, "error": "缺少 confirm=true（真实写入）"})
                return
            # 当天保护：只认服务端的 run_num（今日已跑**有效**次数）。
            # 今天提交过但被判无效的记录不该拦——名额还在。
            try:
                sess.before_run()
            except V3Error:
                pass
            eff_today = int((sess.last_before_run or {}).get("run_num") or 0)
            if eff_today > 0 and not data.get("force"):
                self._send(409, {
                    "ok": False,
                    "error": f"服务端显示你今天已经有 {eff_today} 条【有效】记录，"
                             f"每天只关联 1 次成绩，再提交不会计入。确认要继续请勾选强制提交。",
                    "today_count": eff_today,
                })
                return
            lpv = S.get("last_preview")
            if not lpv:
                self._send(400, {"ok": False, "error": "先生成一次轨迹预览"})
                return
            # ---- 真机顺序：beforeRun → getTimestamp → beforeRun → stopFreeRun ----
            # 中间那次 beforeRun 会刷新服务端侧的“本次跑步”上下文，漏掉会报「跑步时间异常」
            try:
                sess.before_run()
            except V3Error:
                pass
            try:
                ts = sess.server_ts()
            except V3Error:
                ts = int(time.time())
            used = int(lpv["used_time"])
            start_ts = ts - used
            pts = lpv["pts"]

            # ---- 1) 轨迹点数组：a/o/s/l/d（与真机 OSS 文件同构）----
            data_arr = []
            prev = None
            acc_m = 0.0
            for i, p in enumerate(pts):
                seg = 0.0
                if prev:
                    seg = haversine_m(prev["a"], prev["o"], p["a"], p["o"])
                    acc_m += seg
                ms = int((start_ts + int(p.get("t") or 0)) * 1000)
                item = {"a": p["a"], "o": p["o"], "l": 1,
                        "d": f"{ms} {seg:.1f}_{i}"}
                if i:
                    item["s"] = round(seg, 2)
                data_arr.append(item)
                prev = p

            # 时间轴两端留富余：真机首点在 start_time 之后、末点在 end_time 之后（样本 724ms / 244ms）
            # 少这几十~几百毫秒，服务端会认为轨迹没覆盖 [start_time, end_time] → 判「跑步时间异常」
            if data_arr:
                tail0 = str(data_arr[0]["d"]).split(" ", 1)[1]
                data_arr[0]["d"] = f"{int(start_ts * 1000) + random.randint(100, 900)} {tail0}"
                if len(data_arr) > 1:
                    taill = str(data_arr[-1]["d"]).split(" ", 1)[1]
                    data_arr[-1]["d"] = f"{int(ts * 1000) + random.randint(100, 900)} {taill}"

            # ---- 2) log_data：打卡点首通过记录 ----
            log = []
            for p in lpv["points"]:
                best = None
                for i, c in enumerate(pts):
                    d = haversine_m(p["lat"], p["lng"], c["a"], c["o"])
                    if best is None or d < best[0]:
                        best = (d, i)
                if not best:
                    continue
                i = best[1]
                a2 = 0.0
                for k in range(1, i + 1):
                    a2 += haversine_m(pts[k - 1]["a"], pts[k - 1]["o"], pts[k]["a"], pts[k]["o"])
                log.append({
                    "latitude": pts[i]["a"],
                    "longitude": pts[i]["o"],          # 真机两套键都写
                    "longtitude": pts[i]["o"],         # （服务端历史拼写）
                    "point_id": p["id"],
                    "time": start_ts + int(pts[i]["t"]),   # 绝对 Unix 时间戳
                    "distance": round(a2 / 1000.0, 2),
                    "point_index": i + 1,
                })

            # ---- 3) 轨迹文件（base64(AES(json))）----
            track = {
                "start_time": start_ts,
                "end_time": ts,
                "distance": round(float(lpv["distance_km"]), 2),
                "log_data": json.dumps(log, ensure_ascii=False, separators=(",", ":")),
                "data": data_arr,
                "run_zone_id": str(lpv.get("zone_id") or ""),
            }
            txt = crypto.encrypt_data(json.dumps(track, ensure_ascii=False,
                                                separators=(",", ":")))

            from lepao.record import make_record_file
            now_ms, record_file, _fname = make_record_file()

            # ---- 4) STS + 上传 ----
            sts = sess.get_oss_sts()
            up_status, up_body = sess.upload_track(txt, sts, record_file, now_ms,
                                                   use_callback=False)
            if up_status not in (200, 203, 204):
                self._send(200, {"ok": False,
                                 "error": f"OSS 上传失败 HTTP {up_status}: {str(up_body)[:200]}",
                                 "record_file": record_file})
                return

            # ---- 5) 提交前再刷一次 beforeRun（真机在 stop 前必调）----
            try:
                sess.before_run()
            except V3Error:
                pass
            # 步频按速度曲线反推（与距离/配速自洽），不再随机
            from lepao import realism as _R
            _sp = lpv.get("speeds") or []
            if _sp:
                steps_obj = _R.step_info_of(_sp)
                steps = steps_obj["list"]
            else:
                buckets = max(used // 60 + 1, 1)
                steps = []
                for b in range(buckets):
                    steps.append(random.randint(150, 182) if b < buckets - 1
                                 else random.randint(20, 60))
            biz = {
                "term_id": sess.term_id,          # 跑区模式必须有学期，否则不关联成绩
                "game_id": lpv["game_id"],
                "start_time": start_ts,
                "end_time": ts,
                "distance": f"{float(lpv['distance_km']):.2f}",
                "record_img": "",
                "log_data": json.dumps(log, ensure_ascii=False, separators=(",", ":")),
                "file_img": "",
                "is_running_area_valid": 1,
                "mobileDeviceId": 1,
                "mobileModel": 1,
                "mobileOsVersion": 1,
                "step_info": json.dumps({"interval": 60, "list": steps}, separators=(",", ":")),
                "step_num": sum(steps),
                "used_time": used,
                "record_file": record_file,
            }
            try:
                j = sess.stop_run_v278(biz)
            except V3Error as e:
                self._send(200, {"ok": False, "error": str(e), "biz": biz,
                                 "record_file": record_file})
                return

            # ---- 6) 复核 ----
            rid = None
            dd = j.get("data")
            if isinstance(dd, dict):
                rid = dd.get("record_id") or dd.get("id")
            review = None
            if rid:
                try:
                    review = sess.record_detail(rid).get("data")
                except V3Error:
                    review = None
            self._send(200, {"ok": j.get("status") == 1, "resp": j, "biz": biz,
                             "record_file": record_file, "record_id": rid,
                             "review": review})
            return

        self._send(404, {"ok": False, "error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="启动后自动用默认浏览器打开")
    a = ap.parse_args()
    s = load_session()
    if s:
        S["sess"] = s
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"[lepao-webapp] http://{a.host}:{a.port}  AES后端={crypto.backend()}")
    if s:
        print(f"[lepao-webapp] 已恢复会话 uid={s.uid} host={s.host}")
    print("[lepao-webapp] Ctrl+C 退出")
    if a.open:
        def _open():
            time.sleep(0.8)
            url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '') else a.host}:{a.port}"
            try:
                import webbrowser
                webbrowser.open(url)
                print(f"[lepao-webapp] 已打开浏览器 {url}")
            except Exception as e:  # noqa: BLE001
                print(f"[lepao-webapp] 打开浏览器失败({e})，请手动访问 {url}")
        threading.Thread(target=_open, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
