# -*- coding: utf-8 -*-
"""run-sim/selftest.py —— 不启服务的自检：生成 → 预检 → 导出，四条跑区全跑一遍。

    py -3 run-sim/selftest.py
    py -3 run-sim/selftest.py -v        # 打印每个用例的预检明细

退出码：0 全绿 ｜ 1 有失败（用于 CI / 提交前门禁）。
"""
import argparse
import os
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)      # lepao 协议栈

from sim import catalog, engine, exporters, submit, sync, validate  # noqa: E402

CASES = [
    # (campus, route, distance_km, pace_sec)
    ("xitucheng", "xtc-track", 2.0, 330),
    ("xitucheng", "xtc-track", 3.0, 300),
    ("xitucheng", "xtc-loop", 3.0, 360),
    ("shahe", "sh-track", 5.0, 420),
    ("shahe", "sh-loop", 3.0, 330),
]


def check(cond, msg, fails):
    if not cond:
        fails.append(msg)
    return cond


class _FakeV3:
    """假平台客户端：验证 lepao 同步适配器的解析/归一化链路，不联网。"""

    def __init__(self, **kw):
        self.kw = kw

    def before_run(self):
        return {"term_id": "2026-1", "run_zone_id": "1"}

    def get_term_run_record(self, term_id, page=1):
        if page > 1:
            return {"list": []}
        now = int(time.time()) - 86400
        return {"list": [
            {"record_id": "FAKE-1", "start_time": now, "end_time": now + 990,
             "distance": 3.01, "used_time": 990, "record_status": 1,
             "record_failed_reason": "自动确认有效"},
            {"record_id": "FAKE-2", "start_time": now - 86400, "end_time": now - 86400 + 1200,
             "distance": 4.0, "used_time": 1200, "record_status": 0,
             "record_failed_reason": "打卡点异常"},
        ]}

    def record_detail(self, record_id):
        return {}


def sync_checks(fails, verbose):
    """同步面自检：demo 适配器 + 假 client 跑 lepao 适配器（不联网、不碰真数据）。"""
    tmp = os.path.join(HERE, "data", "_selftest_sync")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    old = (sync.FILE, sync.DATA)
    sync.FILE = os.path.join(tmp, "platform.json")
    sync.DATA = tmp
    try:
        out = sync.pull("demo")
        check(out["total"] > 0, "demo 同步没有产出记录", fails)
        check(out["live"] is False, "demo 不应标记为 live", fails)
        if verbose:
            print(f"        demo 同步: {out['total']} 条 / {out['note']}")
        recs = sync.load()["records"]
        keys = [sync.key_of(r) for r in recs]
        check(len(keys) == len(set(keys)), "同步记录存在重复键（去重失效）", fails)
        again = sync.pull("demo")
        check(again["added"] == 0, "重复同步不应新增记录", fails)

        import lepao.v3api as v3
        from sim import credentials
        old_load = credentials.load
        old_client = v3.V3Client
        credentials.load = lambda: {"token": "T", "uid": 1, "student_num": "S",
                                    "api_host": "h", "proxy": ""}
        v3.V3Client = _FakeV3
        try:
            out2 = sync.pull("lepao")
        finally:
            credentials.load = old_load
            v3.V3Client = old_client
        check(out2["live"] is True, "lepao 适配器应标记 live", fails)
        check(out2["total"] == 2, f"lepao 适配器记录数异常: {out2['total']}", fails)
        got = {r["record_id"]: r for r in sync.load()["records"]}
        check(got.get("FAKE-1", {}).get("valid") is True, "FAKE-1 应判为有效", fails)
        check(got.get("FAKE-2", {}).get("valid") is False, "FAKE-2 应判为无效", fails)
        check(got.get("FAKE-1", {}).get("pace") == 329, "配速推导异常", fails)

        dash = sync.dashboard()
        for k in ("records", "stats", "sync", "profile"):
            check(k in dash, f"dashboard 缺字段 {k}", fails)
        check(dash["stats"]["total_km"] > 0, "dashboard 里程为 0", fails)
        if verbose:
            print(f"        lepao 假 client: 2 条 / 判定 {[(k, v['valid']) for k, v in got.items()]}")
            print(f"        dashboard: {dash['stats']}")
    finally:
        sync.FILE, sync.DATA = old
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    fails = []
    print(f"run-sim selftest · 引擎 {[e['name'] for e in engine.engine_list()]}")
    print(f"跑区 {len(catalog.public_catalog())} 个校区 / "
          f"{sum(len(c['routes']) for c in catalog.public_catalog())} 条路线")
    print("-" * 96)

    for cid, rid, km, pace in CASES:
        try:
            res = engine.generate(cid, rid, km, pace, start_at="2026-11-24T07:30", seed="2026")
        except Exception:  # noqa: BLE001
            fails.append(f"{cid}/{rid} 生成抛异常")
            traceback.print_exc()
            continue
        m = res["metrics"]
        v = validate.validate(res)
        dist_err = abs(m["distance_km"] - km)
        pace_err = abs(m["avg_pace"] - pace)
        cp_hit = sum(1 for c in res["checkins"] if c["hit"])
        cp_total = len(res["checkins"])
        tag = "OK " if v["verdict"] == "pass" else v["verdict"].upper()
        print(f"[{tag:4s}] {cid:10s} {rid:9s} {km}km@{pace}s → "
              f"{m['distance_km']:.3f}km {m['duration_s']}s {m['avg_pace']}s/km "
              f"pts={m['points']} cp={cp_hit}/{cp_total} "
              f"Δdist={dist_err * 1000:.0f}m Δpace={pace_err}s")
        if args.verbose:
            for it in v["items"]:
                print(f"        {it['level']:4s} {it['title']} — {it['detail']}")

        check(dist_err <= 0.02, f"{rid}: 里程偏差 {dist_err:.3f} km 超容差", fails)
        check(pace_err <= 3, f"{rid}: 配速偏差 {pace_err}s 超容差", fails)
        check(cp_hit == cp_total, f"{rid}: 打卡点未全覆盖 {cp_hit}/{cp_total}", fails)
        check(v["verdict"] == "pass", f"{rid}: 预检未通过 {v['verdict']}", fails)
        check(len(res["track"]) >= 40, f"{rid}: 轨迹点过少 {len(res['track'])}", fails)

        # 导出器逐个跑一遍
        for name in exporters.EXPORTERS:
            try:
                body, ctype, fname = exporters.EXPORTERS[name]["fn"](res)
                check(bool(body) and bool(fname), f"{rid}: 导出 {name} 产出为空", fails)
                if args.verbose:
                    print(f"        导出 {name}: {len(body)}B {ctype} {fname}")
            except Exception as e:  # noqa: BLE001
                fails.append(f"{rid}: 导出 {name} 失败 {type(e).__name__}: {e}")
        try:
            plan = submit.submit(res, "offline")
            check(plan["ok"] and plan["steps"], f"{rid}: 提交预演无步骤", fails)
        except Exception as e:  # noqa: BLE001
            fails.append(f"{rid}: 提交预演失败 {type(e).__name__}: {e}")

    sync_checks(fails, args.verbose)

    print("-" * 96)
    if fails:
        print(f"FAIL {len(fails)} 项：")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS 全部用例通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
