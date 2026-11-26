# -*- coding: utf-8 -*-
"""run-sim.sim.sync —— 数据同步：平台记录 ←→ 本地记录。

适配器注册表（前端自动出现）：
  demo   演示数据（合成，零网络；用来看界面与对齐逻辑）
  lepao  真实拉取：lepao.v3api.V3Client → beforeRunV260 拿 term_id → getTermRunRecord 分页
         → 最近若干条再打 recordDetailV270 拿权威状态
  auto   有 token 走 lepao，没有回落 demo

原则：
  - 只读（getTermRunRecord / recordDetail），不写平台；提交仍归 sim/submit.py
  - 落盘 `run-sim/data/platform.json`（已 gitignore），按 record_id 去重合并
  - 同步失败不吞异常，把原因原样带回前端
"""
import datetime as _dt
import json
import os
import random
import time

from . import credentials, store

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
FILE = os.path.join(DATA, "platform.json")

ADAPTERS = {}


class SyncError(Exception):
    pass


def register(name, label, description, fn, live=False):
    ADAPTERS[name] = {"name": name, "label": label, "description": description,
                      "fn": fn, "live": live}


def adapter_list():
    return [{"name": a["name"], "label": a["label"], "description": a["description"],
             "live": a["live"]} for a in ADAPTERS.values()]


# ------------------------------------------------------------------ 归一化
def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _norm(row, source):
    """平台/演示记录 → 统一结构。字段名按 lepao 实证口径，缺了就用默认值兜底。"""
    rid = row.get("record_id") or row.get("id") or ""
    start = _int(row.get("start_time"))
    end = _int(row.get("end_time"))
    used = _int(row.get("used_time") or row.get("time"))
    if not used and start and end:
        used = max(0, end - start)
    dist = round(_float(row.get("distance")), 2)
    status = row.get("record_status", row.get("status"))
    reason = str(row.get("record_failed_reason") or "").strip()
    positive = (not reason) or ("有效" in reason and "无效" not in reason
                                and "不" not in reason and "异常" not in reason)
    valid = str(status) in ("0", "1") and positive and dist > 0
    return {
        "record_id": str(rid),
        "start_time": start,
        "end_time": end,
        "used_time": used,
        "distance_km": dist,
        "pace": int(round(used / dist)) if dist > 0 and used > 0 else 0,
        "status": "" if status is None else str(status),
        "status_text": reason,
        "valid": bool(valid),
        "source": source,
        "synced_at": int(time.time()),
        "raw_keys": sorted(k for k in row.keys())[:24],
    }


def key_of(rec):
    if rec.get("record_id"):
        return f"id:{rec['record_id']}"
    return f"t:{_int(rec.get('start_time'))}:{round(_float(rec.get('distance_km')), 2)}"


# ------------------------------------------------------------------ 适配器
def _adapter_demo(ctx):
    """演示数据：过去 21 天里挑 11 天造记录，看起来像真学期。"""
    rnd = random.Random(20261124)
    today = _dt.date.today()
    rows = []
    total = 0
    day = today
    for back in range(21, 0, -1):
        day = today - _dt.timedelta(days=back)
        if rnd.random() < 0.45:
            continue
        dist = round(rnd.uniform(2.0, 4.6), 2)
        pace = rnd.randint(300, 480)
        used = int(dist * pace)
        ts = int(_dt.datetime.combine(day, _dt.time(rnd.randint(7, 21), rnd.randint(0, 59))).timestamp())
        bad = rnd.random() < 0.12
        rows.append({
            "record_id": f"DEMO{ts}",
            "start_time": ts,
            "end_time": ts + used,
            "used_time": used,
            "distance": dist,
            "record_status": 0 if bad else 1,
            "record_failed_reason": "打卡点异常" if bad else "自动确认有效",
        })
        total += dist
    return {
        "records": rows,
        "source": "demo",
        "live": False,
        "account": {"uid": 0, "student_num": credentials.load().get("student_num") or "DEMO"},
        "note": f"演示数据 {len(rows)} 条 / {total:.2f} km（合成，非平台真实数据）",
    }


def _adapter_lepao(ctx):
    """真实拉取。需要 token（抓号得来）与出口链；只读记录接口。"""
    try:
        from lepao.v3api import V3Client, V3Error
    except Exception as e:  # noqa: BLE001
        raise SyncError(f"lepao 协议栈不可用: {e}")

    cred = credentials.load()
    if not cred.get("token"):
        raise SyncError("未配置 token：先在设置里粘贴，或用 cli.py capture 抓号")
    if not cred.get("uid"):
        raise SyncError("缺少 uid：抓号后会自动回填，或手动填写")

    client = V3Client(
        uid=cred["uid"], token=cred["token"], school_id=cred.get("school_id") or 0,
        student_num=cred.get("student_num") or "", card_id=cred.get("student_num") or "",
        host=cred.get("api_host") or "api2.lptiyu.com",
        proxy=cred.get("proxy") or None, pace=0.8,
    )
    try:
        cfg = client.before_run()          # 同时充当真门校验（101 = token 死）
        if isinstance(cfg, dict) and cfg.get("status") == 101:
            raise SyncError("token 已失效（101）：重新抓号")
        term_id = str((cfg or {}).get("term_id") or "0")
        rows = []
        for page in range(1, 6):
            r = client.get_term_run_record(term_id, page)
            if not isinstance(r, dict):
                raise SyncError(f"getTermRunRecord 返回异常: {str(r)[:120]}")
            lst = r.get("list") or []
            rows.extend(lst)
            if len(lst) < 10:
                break
        # 最近 5 条补 recordDetail（权威状态来源）
        for row in rows[:5]:
            rid = row.get("record_id") or row.get("id")
            if not rid:
                continue
            try:
                d = client.record_detail(rid)
                if isinstance(d, dict):
                    for k in ("record_status", "record_failed_reason", "distance", "used_time"):
                        if d.get(k) not in (None, ""):
                            row[k] = d[k]
            except V3Error as e:
                if e.code == 101:
                    raise SyncError("token 已失效（101）：重新抓号")
        return {
            "records": rows,
            "source": "lepao",
            "live": True,
            "account": {"uid": cred["uid"], "student_num": cred.get("student_num") or "",
                        "term_id": term_id},
            "note": f"平台真实记录 {len(rows)} 条（term {term_id}）",
        }
    except SyncError:
        raise
    except V3Error as e:
        raise SyncError(f"平台接口错误 code={e.code}: {e.msg[:160]}")
    except OSError as e:
        raise SyncError(f"出口链不通（mitm/代理未起？）: {e}")


def _adapter_auto(ctx):
    if credentials.load().get("token"):
        return _adapter_lepao(ctx)
    return _adapter_demo(ctx)


register("auto", "自动", "有 token 走真实拉取，没有则演示数据", _adapter_auto)
register("lepao", "平台真实拉取", "V3Client 只读记录接口，需要 token 与出口链", _adapter_lepao, live=True)
register("demo", "演示数据", "合成记录，零网络，用于看界面与对齐逻辑", _adapter_demo)


# ------------------------------------------------------------------ 存储
def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("records", [])
    data.setdefault("synced_at", 0)
    data.setdefault("source", "")
    data.setdefault("note", "")
    data.setdefault("account", {})
    return data


def _save(data):
    os.makedirs(DATA, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def pull(adapter="auto", ctx=None):
    a = ADAPTERS.get(adapter)
    if not a:
        raise KeyError(f"未知同步适配器: {adapter}")
    out = a["fn"](ctx or {})
    src = out.get("source") or a["name"]
    live = bool(out.get("live", a["live"]))
    incoming = [_norm(r, src) for r in (out.get("records") or [])]
    data = load()
    index = {key_of(r): r for r in data["records"]}
    added = updated = 0
    for rec in incoming:
        k = key_of(rec)
        if k in index:
            merged = dict(index[k])
            merged.update(rec)
            index[k] = merged
            updated += 1
        else:
            index[k] = rec
            added += 1
    # 演示数据与真实数据互斥：切源时清掉上一源的记录，避免混算
    if data.get("source") and data["source"] != src:
        index = {key_of(r): r for r in incoming}
        added, updated = len(incoming), 0
    data["records"] = sorted(index.values(), key=lambda r: r.get("start_time") or 0)
    data["synced_at"] = int(time.time())
    data["source"] = src
    data["live"] = live
    data["note"] = out.get("note") or ""
    data["account"] = out.get("account") or {}
    _save(data)
    return {"ok": True, "added": added, "updated": updated,
            "total": len(data["records"]), "source": src,
            "live": live, "note": data["note"], "synced_at": data["synced_at"]}


def status():
    data = load()
    return {
        "synced_at": data["synced_at"],
        "source": data["source"],
        "live": bool(data.get("live")),
        "note": data["note"],
        "account": data.get("account") or {},
        "records": len(data["records"]),
    }


# ------------------------------------------------------------------ 仪表盘
def _match(local, platform):
    """本地记录 ↔ 平台记录：起始时间 ±180s 且里程 ±0.08 km 视为同一次。"""
    for p in platform:
        if abs((p.get("start_time") or 0) - (local.get("metrics", {}).get("start_ts") or 0)) <= 180 \
                and abs((p.get("distance_km") or 0) - (local.get("metrics", {}).get("distance_km") or 0)) <= 0.08:
            return p
    return None


def dashboard():
    data = load()
    platform = data["records"]
    locals_ = store.list_records()

    merged, used_local = [], set()
    for p in platform:
        entry = {
            "origin": "platform",
            "valid": p.get("valid"),
            "record_id": p.get("record_id"),
            "start_time": p.get("start_time"),
            "distance_km": p.get("distance_km"),
            "used_time": p.get("used_time"),
            "pace": p.get("pace"),
            "status_text": p.get("status_text") or "",
            "local_id": "",
        }
        for l in locals_:
            m = l.get("metrics") or {}
            if abs((p.get("start_time") or 0) - (m.get("start_ts") or 0)) <= 180 \
                    and abs((p.get("distance_km") or 0) - (m.get("distance_km") or 0)) <= 0.08:
                entry["origin"] = "platform+local"
                entry["local_id"] = l.get("id")
                used_local.add(l.get("id"))
                break
        merged.append(entry)

    for l in locals_:
        if l.get("id") in used_local:
            continue
        m = l.get("metrics") or {}
        merged.append({
            "origin": "local",
            "valid": None,
            "record_id": "",
            "start_time": m.get("start_ts"),
            "distance_km": m.get("distance_km"),
            "used_time": m.get("duration_s"),
            "pace": m.get("avg_pace"),
            "status_text": "仅本地 · 未提交",
            "local_id": l.get("id"),
        })

    merged.sort(key=lambda r: r.get("start_time") or 0, reverse=True)

    now = _dt.datetime.now()
    week_start = (now - _dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    today = now.date()

    def _km(recs):
        return round(sum(float(r.get("distance_km") or 0) for r in recs), 2)

    valid = [r for r in merged if r.get("valid")]
    total = _km(valid)
    week = _km([r for r in valid
                if (r.get("start_time") or 0) >= int(week_start.timestamp())])
    today_km = _km([r for r in valid
                    if _dt.datetime.fromtimestamp(r.get("start_time") or 0).date() == today])
    prof = store.get_profile()
    target = float(prof.get("target_km") or 90)
    return {
        "records": merged[:60],
        "stats": {
            "total_km": total,
            "target_km": round(target, 1),
            "remaining_km": round(max(0.0, target - total), 2),
            "ratio": round(min(1.0, total / target), 4),
            "count": len(valid),
            "week_km": week,
            "today_km": today_km,
        },
        "sync": status(),
        "profile": prof,
    }
