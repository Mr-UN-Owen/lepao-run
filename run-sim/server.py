# -*- coding: utf-8 -*-
"""run-sim/server.py —— 北邮校园跑模拟台 · 本地 Web 服务（零依赖，标准库）。

    py -3 run-sim/server.py --port 8771
    # 或双击 run-sim/启动模拟器.bat

与仓库里 app/server.py（乐跑控制台）是两套东西：
  - app/     研究协议栈的控制台（抓号 / 干跑 / 提交）
  - run-sim/ 面向同学的「校园跑模拟台」：选跑区 → 生成轨迹 → 预检 → 导出/存档

本文件只做 HTTP 编排，业务全在 sim/ 里；加接口就加一个 if 分支。
"""
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)  # 仓库根，供 lepao 等上层模块用
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim import catalog, credentials, engine, exporters, store, submit, sync, validate  # noqa: E402

WEB = os.path.join(HERE, "web")
LOG_LOCK = threading.Lock()


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with LOG_LOCK:
        print(line, flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "run-sim/0.1"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- 基础
    def log_message(self, fmt, *args):  # 静默掉默认访问日志
        return

    def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8", extra=None):
        if raw is None:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        elif isinstance(raw, str):
            raw = raw.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _json_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {}

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(WEB, rel))
        if not full.startswith(WEB) or not os.path.isfile(full):
            self._send(404, {"ok": False, "error": "not found"})
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, raw=f.read(), ctype=ctype)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path in ("/", "/index.html"):
                self._static("index.html")
                return
            if path == "/favicon.ico":
                self._send(204, raw=b"")
                return
            if path.startswith("/api/"):
                self._api_get(path, urllib.parse.parse_qs(parsed.query))
                return
            self._static(path)
        except BrokenPipeError:
            return
        except Exception as e:  # noqa: BLE001
            log(f"GET {path} 失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def _api_get(self, path, qs):
        if path == "/api/health":
            self._send(200, {"ok": True, "version": engine_version(), "time": time.time()})
            return
        if path == "/api/bootstrap":
            pol = catalog.policy()
            self._send(200, {
                "ok": True,
                "app": {
                    "name": "北邮校园跑 · 模拟台",
                    "version": engine_version(),
                    "tagline": "选跑区 → 生成轨迹 → 预检 → 导出",
                },
                "campuses": catalog.public_catalog(),
                "policy": pol,
                "progress": store.progress(),
                "engines": engine.engine_list(),
                "exporters": exporters.exporter_list(),
                "submitters": submit.adapter_list(),
                "syncers": sync.adapter_list(),
                "sync": sync.status(),
                "credentials": credentials.public(),
                "dashboard": sync.dashboard(),
                "notes": [
                    "所有数据只在本机，不联网、不上传",
                    "坐标为演示 fixture，需按学校最新跑区校准 config/bupt_routes.json",
                    "生成结果仅供训练/演示，不代表平台一定判有效",
                ],
            })
            return
        if path == "/api/dashboard":
            self._send(200, {"ok": True, **sync.dashboard()})
            return
        if path == "/api/sync/status":
            self._send(200, {"ok": True, "sync": sync.status()})
            return
        if path == "/api/credentials":
            self._send(200, {"ok": True, "credentials": credentials.public()})
            return
        if path == "/api/records":
            self._send(200, {"ok": True, "records": store.list_records()})
            return
        if path.startswith("/api/records/"):
            rest = path[len("/api/records/"):]
            parts = [p for p in rest.split("/") if p]
            rid = parts[0] if parts else ""
            if len(parts) >= 3 and parts[1] == "export":
                fmt = parts[2]
                rec = store.get_record(rid)
                if not rec:
                    self._send(404, {"ok": False, "error": "记录不存在"})
                    return
                exp = exporters.EXPORTERS.get(fmt)
                if not exp:
                    self._send(400, {"ok": False, "error": f"未知导出格式: {fmt}"})
                    return
                body, ctype, fname = exp["fn"](rec)
                self._send(200, raw=body, ctype=ctype, extra={
                    "Content-Disposition": f'attachment; filename="{urllib.parse.quote(fname)}"'
                })
                return
            rec = store.get_record(rid)
            if not rec:
                self._send(404, {"ok": False, "error": "记录不存在"})
                return
            self._send(200, {"ok": True, "record": rec})
            return
        if path == "/api/policy":
            self._send(200, {"ok": True, "policy": catalog.policy()})
            return
        if path == "/api/profile":
            self._send(200, {"ok": True, "progress": store.progress()})
            return
        self._send(404, {"ok": False, "error": "not found"})

    # --------------------------------------------------------------- POST
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._json_body()
        try:
            self._api_post(path, body)
        except BrokenPipeError:
            return
        except (KeyError, ValueError) as e:
            self._send(400, {"ok": False, "error": f"{type(e).__name__}: {e}"})
        except FileNotFoundError as e:
            self._send(409, {"ok": False, "error": f"引擎依赖缺失: {e}"})
        except Exception as e:  # noqa: BLE001
            log(f"POST {path} 失败: {type(e).__name__}: {e}")
            traceback.print_exc()
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/records/"):
                rid = path[len("/api/records/"):].strip("/")
                ok = store.delete_record(rid)
                self._send(200 if ok else 404, {"ok": ok,
                                                "records": store.list_records()})
                return
            self._send(404, {"ok": False, "error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def _api_post(self, path, body):
        if path == "/api/generate":
            t0 = time.time()
            campus_id = (body.get("campus_id") or "").strip()
            route_id = (body.get("route_id") or "").strip()
            if not campus_id or not route_id:
                raise ValueError("缺少 campus_id / route_id")
            distance_km = float(body.get("distance_km") or 3.0)
            pace_sec = int(body.get("pace_sec") or 330)
            pol = catalog.policy()
            if distance_km < 0.4 or distance_km > 21.0:
                raise ValueError("distance_km 需在 0.4 ~ 21.0 之间")
            if pace_sec < 120 or pace_sec > 900:
                raise ValueError("pace_sec 需在 120 ~ 900 秒/公里之间")
            res = engine.generate(
                campus_id, route_id, distance_km, pace_sec,
                start_at=body.get("start_at") or "",
                seed=body.get("seed"),
                engine=(body.get("engine") or "math"),
            )
            res["validation"] = validate.validate(res, store.list_records())
            res["elapsed_ms"] = int((time.time() - t0) * 1000)
            res["ok"] = True
            log(f"生成 {campus_id}/{route_id} {distance_km}km 配速{pace_sec}s → "
                f"{res['metrics']['distance_km']}km/{res['metrics']['duration_s']}s "
                f"判定={res['validation']['verdict']} {res['elapsed_ms']}ms")
            self._send(200, res)
            return

        if path == "/api/records":
            draft = body.get("draft") or body
            if not draft.get("track") or not draft.get("metrics"):
                raise ValueError("缺少 track / metrics")
            item = store.save_record(draft)
            self._send(200, {"ok": True, "record": item, "progress": store.progress()})
            return

        if path == "/api/sync":
            adapter = (body.get("adapter") or "auto").strip()
            t0 = time.time()
            try:
                out = sync.pull(adapter)
            except sync.SyncError as e:
                self._send(409, {"ok": False, "error": str(e), "sync": sync.status()})
                return
            out["elapsed_ms"] = int((time.time() - t0) * 1000)
            out["sync"] = sync.status()
            out["dashboard"] = sync.dashboard()
            log(f"同步 adapter={adapter} +{out['added']}/~{out['updated']} 共{out['total']}条 "
                f"({out['elapsed_ms']}ms) {out['note'][:60]}")
            self._send(200, out)
            return

        if path == "/api/credentials":
            prof = credentials.save(body)
            if body.get("student_num"):
                store.set_profile({"student_num": body["student_num"],
                                   "name": body.get("name") or ""})
            self._send(200, {"ok": True, "credentials": prof})
            return

        if path == "/api/credentials/clear-token":
            self._send(200, {"ok": True, "credentials": credentials.clear_token()})
            return

        if path == "/api/profile":
            prof = store.set_profile(body)
            self._send(200, {"ok": True, "profile": prof, "progress": store.progress()})
            return

        if path == "/api/verify":
            rid = body.get("id") or ""
            rec = body.get("draft") or store.get_record(rid)
            if not rec:
                raise ValueError("需要 draft 或已存在的 id")
            self._send(200, {"ok": True, "validation": validate.validate(
                rec, store.list_records(), exclude_id=rid)})
            return

        if path == "/api/submit":
            rec = body.get("draft") or store.get_record(body.get("id") or "")
            if not rec:
                raise ValueError("需要 draft 或已存在的 id")
            out = submit.submit(rec, body.get("adapter") or "offline",
                               {"day_count": len([r for r in store.list_records()
                                                  if r.get("day") == rec.get("day")])})
            self._send(200, dict(out, ok=True))
            return

        self._send(404, {"ok": False, "error": "not found"})


def engine_version():
    import sim
    return sim.__version__


def main():
    port = 8771
    host = "127.0.0.1"
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if a == "--host" and i + 1 < len(args):
            host = args[i + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    log(f"北邮校园跑 · 模拟台 v{engine_version()} → http://{host}:{port}")
    log(f"配置 {catalog.CONFIG_FILE}")
    log(f"记录库 {store.DATA_DIR}")
    log("Ctrl+C 退出")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
