# -*- coding: utf-8 -*-
"""run-sim.sim.catalog —— 站点数据目录：校区 / 跑区 / 打卡点 / 策略。

配置文件是唯一真源（config/bupt_routes.json），代码只做解释与校验：
  - 换学校 / 换跑区 / 加打卡点：只改 json
  - 加一种新跑区形态（比如折返、绕楼）：在 route_ring() 里加一个 type 分支
"""
import json
import os

from . import geo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONFIG_FILE = os.path.join(ROOT, "config", "bupt_routes.json")

DEFAULT_POLICY = {
    "dist_lo_km": 2.0,
    "dist_hi_km": 5.0,
    "pace_lo": 180,
    "pace_hi": 540,
    "max_per_day": 1,
    "checkin_radius_m": 40,
    "allowed_hours": [6.0, 22.5],
    "semester": {"male": 100, "female": 85, "other": 90},
}

_CACHE = {"mtime": None, "data": None}


def load(force=False):
    """读取并缓存配置（按 mtime 失效，改 json 不用重启服务）。"""
    mtime = os.path.getmtime(CONFIG_FILE)
    if not force and _CACHE["data"] is not None and _CACHE["mtime"] == mtime:
        return _CACHE["data"]
    with open(CONFIG_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    raw.setdefault("policy", {})
    merged = dict(DEFAULT_POLICY)
    merged.update(raw["policy"])
    merged.setdefault("semester", DEFAULT_POLICY["semester"])
    raw["policy"] = merged
    raw["campuses"] = [c for c in raw.get("campuses", []) if c.get("routes")]
    _CACHE.update(mtime=mtime, data=raw)
    return raw


def policy():
    return load()["policy"]


def campus(campus_id):
    for c in load()["campuses"]:
        if c["id"] == campus_id:
            return c
    raise KeyError(f"未知校区: {campus_id}")


def route(campus_id, route_id):
    c = campus(campus_id)
    for r in c["routes"]:
        if r["id"] == route_id:
            return r
    raise KeyError(f"校区 {campus_id} 下没有跑区 {route_id}")


def route_checkpoints(campus_id, route_id):
    """跑区 → 打卡点 [(lat, lng, point_id), ...]。

    两种写法（配置文件二选一，推荐第一种，几何与打卡点解耦）：
      checkpoints: [{"point_id":"24001","lat":39.9,"lng":116.3}, ...]
      anchors + point_ids: 旧写法，打卡点与路线拐点重合
      type=oval: 椭圆上按 phase_deg 均匀取 len(point_ids) 个点
    """
    r = route(campus_id, route_id)
    if r.get("checkpoints"):
        out = []
        for cp in r["checkpoints"]:
            out.append((float(cp["lat"]), float(cp["lng"]), str(cp["point_id"])))
        return out
    ids = [str(x) for x in r.get("point_ids") or []]
    if r.get("type") == "oval":
        pts = geo.oval_anchors(r["center"], float(r["rx_m"]), float(r["ry_m"]),
                               n=max(3, len(ids) or 4),
                               phase_deg=float(r.get("phase_deg", 45.0)))
    else:
        pts = [(float(a[0]), float(a[1])) for a in r.get("anchors") or []]
    if len(ids) != len(pts):
        raise ValueError(f"跑区 {route_id}: point_ids({len(ids)}) 与锚点数({len(pts)}) 不一致")
    return [(p[0], p[1], pid) for p, pid in zip(pts, ids)]


CARDINALS = ["东北", "东南", "西南", "西北"]


def route_checkpoint_views(campus_id, route_id):
    """打卡点视图（带名称）：给前端列表/地图用。"""
    r = route(campus_id, route_id)
    pts = route_checkpoints(campus_id, route_id)
    named = r.get("checkpoints") or []
    out = []
    for i, (lat, lng, pid) in enumerate(pts):
        label = ""
        if i < len(named):
            label = str(named[i].get("label") or "")
        if not label and r.get("type") == "oval":
            label = f"{r.get('poi') or '场地'}{CARDINALS[i % len(CARDINALS)]}"
        out.append({"point_id": pid, "lat": round(lat, 6), "lng": round(lng, 6),
                    "label": label or f"打卡点 {i + 1}"})
    return out


def route_ring(campus_id, route_id):
    """跑区几何环（决定"怎么走"），与打卡点解耦：
       oval      → 椭圆 n 点闭环（田径场）
       polyline  → geometry/anchors 拐点 + 轻量角切（贴路，拐角只磨一点点）
    """
    r = route(campus_id, route_id)
    kind = r.get("type", "polyline")
    if kind == "oval":
        n = max(12, int(360 / max(1.0, float(r.get("step_deg", 7.5)))))
        return geo.ellipse_ring(r["center"], float(r["rx_m"]), float(r["ry_m"]), n=n)
    if kind == "polyline":
        base = r.get("geometry") or r.get("anchors") or []
        pts = [(float(a[0]), float(a[1])) for a in base]
        if len(pts) < 3:
            raise ValueError(f"跑区 {route_id}: 几何点不足 3 个")
        return geo.chaikin_closed(pts, iterations=1, ratio=float(r.get("corner_ratio", 0.05)))
    raise ValueError(f"未支持的跑区类型: {kind}（在 catalog.route_ring 里加分支）")


def min_cover_m(ring, checkpoints):
    """覆盖全部打卡点所需的最小里程 = 周长 - 相邻打卡点间最大间隙。"""
    if len(checkpoints) < 2 or len(ring) < 2:
        return 0.0
    cum = geo.cumulative_m(ring)
    total = cum[-1]
    hits = sorted(geo.project_point(ring, la, ln)[0] for la, ln, _pid in checkpoints)
    best = 0.0
    for i in range(len(hits)):
        gap = (hits[(i + 1) % len(hits)] - hits[i]) % max(1.0, total)
        best = max(best, gap)
    return total - best


def public_catalog():
    """给前端的精简目录：只带绘图必需字段。"""
    data = load()
    out = []
    for c in data["campuses"]:
        routes = []
        for r in c["routes"]:
            anchors = route_checkpoints(c["id"], r["id"])
            views = route_checkpoint_views(c["id"], r["id"])
            ring = route_ring(c["id"], r["id"])
            perimeter = geo.path_len_m(ring)
            cover = min_cover_m(ring, anchors)
            routes.append({
                "id": r["id"],
                "name": r["name"],
                "poi": r.get("poi", ""),
                "hint_km": round(perimeter / 1000.0, 2),
                "per_lap_m": r.get("per_lap_m"),
                "min_cover_km": round(cover / 1000.0, 2),
                "checkpoints": views,
            })
        out.append({
            "id": c["id"],
            "name": c["name"],
            "short": c.get("short", c["name"]),
            "center": c.get("center"),
            "boundary": c.get("boundary", []),
            "roads": c.get("roads", []),
            "routes": routes,
        })
    return out


def semester_target(gender):
    sem = policy().get("semester", {})
    return float(sem.get(str(gender or "other").lower(), sem.get("other", 90)))
