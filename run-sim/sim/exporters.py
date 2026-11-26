# -*- coding: utf-8 -*-
"""run-sim.sim.exporters —— 导出器注册表（gpx / json / 协议形态）。

加一种格式 = 写一个 fn(record) -> (bytes, mimetype, filename)，再 register()。
前端「导出」下拉框自动出现，无需改前端。
"""
import datetime as _dt
import json
import xml.sax.saxutils as sx

EXPORTERS = {}


def register(name, label, ext, fn, mimetype="application/octet-stream"):
    EXPORTERS[name] = {"name": name, "label": label, "ext": ext,
                       "fn": fn, "mimetype": mimetype}


def exporter_list():
    return [{"name": e["name"], "label": e["label"], "ext": e["ext"]}
            for e in EXPORTERS.values()]


def _iso(ts):
    return _dt.datetime.fromtimestamp(int(ts)).astimezone().isoformat(timespec="seconds")


def to_gpx(record):
    track = record.get("track") or []
    name = record.get("title") or record.get("id") or "campus-run"
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="run-sim" xmlns="http://www.topografix.com/GPX/1/1">',
             '  <metadata>',
             f'    <name>{sx.escape(str(name))}</name>',
             f'    <time>{_iso(record["metrics"]["start_ts"])}</time>',
             '  </metadata>',
             '  <trk>',
             f'    <name>{sx.escape(str(name))}</name>',
             '    <trkseg>']
    start = record["metrics"]["start_ts"]
    for p in track:
        t = int(start + float(p.get("t") or 0))
        lines.append(f'      <trkpt lat="{p["a"]:.7f}" lon="{p["o"]:.7f}">')
        lines.append(f'        <time>{_iso(t)}</time>')
        lines.append('      </trkpt>')
    lines += ['    </trkseg>', '  </trk>']
    for cp in record.get("checkins") or []:
        lines.append(f'  <wpt lat="{cp["lat"]:.7f}" lon="{cp["lng"]:.7f}">')
        lines.append(f'    <name>{sx.escape(str(cp["point_id"]))}</name>')
        lines.append(f'    <time>{_iso(cp["time"])}</time>')
        lines.append('  </wpt>')
    lines.append('</gpx>')
    return ("\n".join(lines) + "\n").encode("utf-8"), "application/gpx+xml", f"{name}.gpx"


def to_json(record):
    body = json.dumps(record, ensure_ascii=False, indent=2)
    return body.encode("utf-8"), "application/json", f"{record.get('id', 'run')}.json"


def to_protocol(record):
    """真机形态草稿：log_data / step_info / 轨迹三件套 + 未填占位符。

    刻意不生成任何请求头、不生成 token、不发请求 —— 这是「离线导出」，
    真正对接平台是后续步骤（sim/submit.py 已留出接口）。
    """
    m = record.get("metrics") or {}
    log_data = []
    for cp in record.get("checkins") or []:
        log_data.append({
            "latitude": cp["lat"],
            "longitude": cp["lng"],
            "longtitude": cp["lng"],       # 平台字段拼写 quirk，保留
            "point_id": str(cp["point_id"]),
            "time": int(cp["time"]),
            "distance": cp["distance_km"],
        })
    payload = {
        "_note": "协议形态草稿：仅数据结构，不含鉴权/签名/网络动作；对接需自备 SDK 与合法账号",
        "_generated_at": _iso(_dt.datetime.now().timestamp()),
        "params": record.get("params"),
        "form": {
            "uid": "[UID]",
            "record_id": "[RECORD_ID]",
            "school_id": "[SCHOOL_ID]",
            "run_area_id": "[RUN_AREA_ID]",
            "start_time": _iso(m.get("start_ts", 0)),
            "end_time": _iso(m.get("end_ts", 0)),
            "used_time": m.get("duration_s"),
            "distance": m.get("distance_km"),
            "log_data": log_data,
            "step_info": record.get("steps"),
        },
        "track": record.get("track"),
        "checkins": record.get("checkins"),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return body.encode("utf-8"), "application/json", f"{record.get('id', 'run')}-protocol.json"


register("gpx", "GPX 轨迹", "gpx", to_gpx, "application/gpx+xml")
register("json", "完整记录 JSON", "json", to_json, "application/json")
register("protocol", "协议形态草稿", "json", to_protocol, "application/json")
