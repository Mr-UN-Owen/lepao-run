# -*- coding: utf-8 -*-
"""run-sim.sim.store —— 本地记录库（文件型，零数据库依赖）。

目录布局（全部在本机，已 gitignore）：
  run-sim/data/records.json      索引（列表页只读这个）
  run-sim/data/tracks/<id>.json  单条完整记录（含轨迹，按需加载）
  run-sim/data/profile.json      跑者档案（姓名/性别/学期目标）

替换成 SQLite / 远端存储时只改本文件对外的 6 个函数，上层无感。
"""
import json
import os
import threading
import time
import uuid

from . import catalog

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
TRACK_DIR = os.path.join(DATA_DIR, "tracks")
INDEX_FILE = os.path.join(DATA_DIR, "records.json")
PROFILE_FILE = os.path.join(DATA_DIR, "profile.json")

LOCK = threading.RLock()


def _ensure():
    os.makedirs(TRACK_DIR, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, obj):
    _ensure()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------ 索引
def list_records():
    with LOCK:
        data = _read_json(INDEX_FILE, {"records": []})
    return list(reversed(data.get("records", [])))


def get_record(record_id):
    path = os.path.join(TRACK_DIR, f"{record_id}.json")
    if not os.path.isfile(path):
        return None
    return _read_json(path, None)


def save_record(payload):
    """payload: engine.generate() 的结果 + title；返回索引项。"""
    with LOCK:
        _ensure()
        rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        metrics = payload.get("metrics") or {}
        day = time.strftime("%Y-%m-%d", time.localtime(int(metrics.get("start_ts") or time.time())))
        try:
            cname = catalog.campus(payload["params"]["campus_id"])["name"]
            rname = catalog.route(payload["params"]["campus_id"], payload["params"]["route_id"])["name"]
        except Exception:  # noqa: BLE001
            cname = payload.get("params", {}).get("campus_id", "")
            rname = payload.get("params", {}).get("route_id", "")
        full = dict(payload)
        full["id"] = rid
        full["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        full["day"] = day
        full["title"] = (payload.get("title") or "").strip() or f"{cname} · {rname}"
        _write_json(os.path.join(TRACK_DIR, f"{rid}.json"), full)

        index = _read_json(INDEX_FILE, {"records": []})
        item = {
            "id": rid,
            "created_at": full["created_at"],
            "day": day,
            "title": full["title"],
            "campus": cname,
            "route": rname,
            "distance_km": metrics.get("distance_km"),
            "duration_s": metrics.get("duration_s"),
            "avg_pace": metrics.get("avg_pace"),
            "engine": (payload.get("meta") or {}).get("engine"),
            "verdict": (payload.get("validation") or {}).get("verdict"),
        }
        index.setdefault("records", []).append(item)
        _write_json(INDEX_FILE, index)
        return item


def delete_record(record_id):
    with LOCK:
        index = _read_json(INDEX_FILE, {"records": []})
        keep = [r for r in index.get("records", []) if r.get("id") != record_id]
        removed = len(keep) != len(index.get("records", []))
        index["records"] = keep
        _write_json(INDEX_FILE, index)
        path = os.path.join(TRACK_DIR, f"{record_id}.json")
        if os.path.isfile(path):
            os.remove(path)
            removed = True
        return removed


# ------------------------------------------------------------------ 档案
DEFAULT_PROFILE = {"name": "", "student_num": "", "gender": "male", "target_km": None}


def get_profile():
    prof = dict(DEFAULT_PROFILE)
    prof.update(_read_json(PROFILE_FILE, {}))
    if not prof.get("target_km"):
        prof["target_km"] = catalog.semester_target(prof.get("gender"))
    return prof


def set_profile(data):
    prof = get_profile()
    for k in ("name", "student_num", "gender"):
        if k in data:
            prof[k] = str(data[k])[:32]
    if data.get("target_km") not in (None, ""):
        try:
            prof["target_km"] = float(data["target_km"])
        except (TypeError, ValueError):
            pass
    if data.get("gender") and data.get("target_km") in (None, ""):
        prof["target_km"] = catalog.semester_target(data["gender"])
    _write_json(PROFILE_FILE, prof)
    return prof


def progress():
    """学期进度：总里程 / 目标 / 条数 / 最近一次。"""
    prof = get_profile()
    recs = list_records()
    total = sum(float(r.get("distance_km") or 0) for r in recs)
    target = float(prof.get("target_km") or 0) or 1.0
    return {
        "profile": prof,
        "total_km": round(total, 2),
        "target_km": round(target, 1),
        "count": len(recs),
        "ratio": round(min(1.0, total / target), 4),
        "last": recs[0] if recs else None,
    }
