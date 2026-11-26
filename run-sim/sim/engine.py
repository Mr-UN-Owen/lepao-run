# -*- coding: utf-8 -*-
"""run-sim.sim.engine —— 轨迹生成引擎（可注册 / 可替换）。

当前内置：
  math     —— 锚点环 + 速度模型 + 打卡减速（默认；纯合成，不依赖任何真实轨迹）
  template —— 相似变换引擎：需要 data/真实轨迹_XXX明文.json 模板，缺失时不可用

新增引擎的方式：
  1) 写一个 `def gen_xxx(ctx) -> dict`（返回结构见 `_result()`）
  2) `ENGINES["xxx"] = {...}` 注册进注册表
  3) 前端会自动从 /api/bootstrap 的 engines 字段看到它，无需改前端
"""
import datetime as _dt
import math
import os
import random

from . import catalog, geo

DT = 2.833          # 采样步长（秒），真机实测值 ±0.02 抖动
MAX_POINTS = 6000   # 单次生成上限，防止极端参数把浏览器拖死


# --------------------------------------------------------------- 引擎注册表
ENGINES = {}


def register(name, label, description, fn, requires=()):
    ENGINES[name] = {
        "name": name,
        "label": label,
        "description": description,
        "fn": fn,
        "requires": list(requires),
    }


def engine_list():
    out = []
    for e in ENGINES.values():
        reason = ""
        for req in e["requires"]:
            if not os.path.isfile(req):
                reason = f"缺少 {os.path.basename(req)}"
        out.append({"name": e["name"], "label": e["label"],
                    "description": e["description"],
                    "available": not reason, "reason": reason})
    return out


# --------------------------------------------------------------- 工具
def _seed_rng(seed):
    if seed in (None, ""):
        seed = random.SystemRandom().randrange(1 << 30)
    if isinstance(seed, str):
        try:
            seed = int(seed.strip())
        except ValueError:
            seed = abs(hash(seed)) % (1 << 30)
    return random.Random(int(seed)), int(seed)


def _parse_start(start_at):
    """'2026-11-24T19:30' / ISO / 空 → epoch 秒。空值取「今天最近的整点」。"""
    if not start_at:
        now = _dt.datetime.now()
        return int(now.replace(minute=0, second=0, microsecond=0).timestamp())
    txt = str(start_at).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(_dt.datetime.strptime(txt[:19], fmt).timestamp())
        except ValueError:
            continue
    return int(_dt.datetime.now().timestamp())


def _transform_ring(coords, rnd, center, rot_rad, scale, dx, dy):
    """整圈环做相似变换（旋转 / 缩放 / 平移），用于逐圈微抖动。"""
    lat0, lng0 = center
    out = []
    ca, sa = math.cos(rot_rad), math.sin(rot_rad)
    for la, ln in coords:
        x, y = geo.enu(la, ln, lat0, lng0)
        x, y = x * scale, y * scale
        x, y = x * ca - y * sa, x * sa + y * ca
        out.append(geo.from_enu(x + dx, y + dy, lat0, lng0))
    return out


def _rotate_ring(ring, idx):
    """把闭环旋转到指定起点（保持闭合）。"""
    body = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring)
    n = len(body)
    idx %= n
    out = body[idx:] + body[:idx]
    return out + [out[0]]


def _start_phase(ring, checkpoints):
    """选起点：落在"相邻打卡点之间最长的那段空隙"之后。

    这样一次跑动覆盖全部打卡点所需里程最小（= 周长 - 最大间隙），
    短距离目标也不会被首尾切掉一个点。投影用线段投影，不是顶点最近。
    """
    if len(checkpoints) < 2:
        return 0, 0.0
    cum = geo.cumulative_m(ring)
    total = cum[-1]
    hits = []
    for la, ln, pid in checkpoints:
        s, d, _i = geo.project_point(ring, la, ln)
        hits.append((s, pid))
    hits.sort()
    best_gap, best_i = -1.0, 0
    for i in range(len(hits)):
        nxt = hits[(i + 1) % len(hits)]
        gap = (nxt[0] - hits[i][0]) % max(1.0, total)
        if gap > best_gap:
            best_gap, best_i = gap, i
    start_s = hits[(best_i + 1) % len(hits)][0]
    return start_s, total - best_gap


def _index_at(cum, s):
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < s:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _build_route(ring, target_m, rnd, step_m=4.0):
    """几何环 → 长度 ≥ target_m*1.15 的闭合折线（逐圈相似变换抖动）。"""
    if len(ring) < 12:
        ring = geo.catmull_rom_closed(ring, step_m)
    perimeter = geo.path_len_m(ring)
    lat0 = sum(p[0] for p in ring) / len(ring)
    lng0 = sum(p[1] for p in ring) / len(ring)
    need = max(1, int(math.ceil(target_m * 1.15 / max(1.0, perimeter))))
    coords = []
    for _ in range(need):
        coords.extend(_transform_ring(
            ring, rnd,
            center=(lat0, lng0),
            rot_rad=math.radians(rnd.uniform(-0.6, 0.6)),
            scale=1.0 + rnd.uniform(-0.004, 0.004),
            dx=rnd.uniform(-2.5, 2.5),
            dy=rnd.uniform(-2.5, 2.5),
        ))
    return coords, perimeter


def _walk_route(coords, cum, anchors, target_m, base_v, rnd, start_ts):
    """沿折线走：速度模型 = 起步渐入 × 疲劳掉速 × 打卡减速 × 终点收速 × OU 噪声。

    返回 (track, min_dist_per_cp)。track 点：{a,o,s,b,c,t}
    """
    lat, lng = coords[0]
    ou_lat = ou_lng = 0.0
    s = 0.0
    t = 0.0
    track = []
    min_d = [1e9] * len(anchors)
    guard = 0
    while s < target_m and guard < MAX_POINTS:
        guard += 1
        pos = geo.position_at(coords, cum, s)

        # 打卡点最近距离
        dmins = [geo.haversine_m(pos[0], pos[1], a[0], a[1]) for a in anchors]
        for i, d in enumerate(dmins):
            if d < min_d[i]:
                min_d[i] = d
        dmin = min(dmins) if dmins else 1e9

        warm = 0.58 + 0.42 * min(1.0, t / 45.0)        # 起步 45s 渐入
        fatigue = 1.0 - 0.05 * (s / max(1.0, target_m))  # 后段轻微掉速
        slow_cp = 1.0
        if dmin < 28.0:                                  # 过打卡点减速拍照/确认
            slow_cp = 0.72 + 0.28 * (dmin / 28.0)
        remaining = target_m - s
        tail = 1.0
        if remaining < 80.0:                             # 终点收速走停
            tail = max(0.16, remaining / 80.0)
        ou_lat = ou_lat * 0.86 + rnd.gauss(0, 0.05)      # 速度抖动（一阶自回归）
        v = base_v * warm * fatigue * slow_cp * tail * (1.0 + max(-0.18, min(0.18, ou_lat)))
        v = max(0.35, min(v, 6.2))

        # 位置抖动（GPS 噪声，OU 平滑 + 偶发跳点）
        jl = 0.0
        jn = 0.0
        if len(track) > 0:
            jl = (geo.quantize_geo(pos[0] + rnd.gauss(0, 1.4) / 111000.0) - pos[0])
            jn = (geo.quantize_geo(pos[1] + rnd.gauss(0, 1.7) / (111320.0 * math.cos(math.radians(pos[0]))))
                  - pos[1])
        pt = {
            "a": geo.quantize_geo(pos[0] + jl),
            "o": geo.quantize_geo(pos[1] + jn),
            "t": round(t, 2),
        }
        if track:
            pt["s"] = round(v, 2)
        b = None
        if dmin < 18.0:
            b = 2 if rnd.random() < 0.75 else 1
        elif rnd.random() < 0.30:
            b = 1
        if b is not None:
            pt["b"] = b
        c = abs(rnd.gauss(0.06, 0.05))
        pt["c"] = f"{min(c, 0.60):.2f}"
        track.append(pt)

        ds = v * (DT + rnd.uniform(-0.02, 0.02))
        s += ds
        t += DT

    # 终点补两点（真人形态：停下后低速度、状态位 2）
    for _ in range(2):
        last = track[-1]
        pt = {
            "a": geo.quantize_geo(last["a"] + rnd.gauss(0, 0.8) / 111000.0),
            "o": geo.quantize_geo(last["o"] + rnd.gauss(0, 0.9) / (111320.0 * math.cos(math.radians(last["a"])))),
            "t": round(t, 2),
            "s": round(rnd.uniform(0.01, 0.06), 2),
            "b": 2,
            "c": f"{abs(rnd.gauss(0.06, 0.04)):.2f}",
        }
        track.append(pt)
        t += DT
    return track, min_d


def _track_metrics(track, target_m, start_ts):
    dist = 0.0
    speeds = []
    for i in range(1, len(track)):
        dist += geo.haversine_m(track[i - 1]["a"], track[i - 1]["o"], track[i]["a"], track[i]["o"])
        if track[i].get("s"):
            speeds.append(float(track[i]["s"]))
    used = track[-1]["t"] if track else 0.0
    pace = used / (dist / 1000.0) if dist > 1 else 0.0
    return {
        "distance_km": round(dist / 1000.0, 3),
        "duration_s": int(round(used)),
        "avg_pace": int(round(pace)),
        "avg_speed": round(dist / used, 2) if used else 0.0,
        "max_speed": round(max(speeds), 2) if speeds else 0.0,
        "min_speed": round(min(speeds), 2) if speeds else 0.0,
        "points": len(track),
        "start_ts": start_ts,
        "end_ts": int(start_ts + used),
        "target_km": round(target_m / 1000.0, 3),
    }


def _checkins(track, anchors, start_ts, radius):
    """打卡点首通过记录（与真机 log_data 字段语义一致）。"""
    cum = [0.0]
    for i in range(1, len(track)):
        cum.append(cum[-1] + geo.haversine_m(track[i - 1]["a"], track[i - 1]["o"],
                                             track[i]["a"], track[i]["o"]))
    rows = []
    for la, ln, pid in anchors:
        idx = None
        best = (1e9, 0)
        for k, p in enumerate(track):
            d = geo.haversine_m(p["a"], p["o"], la, ln)
            if d < best[0]:
                best = (d, k)
            if idx is None and d <= radius:
                idx = k
        hit = idx is not None
        k = idx if idx is not None else best[1]
        rows.append({
            "point_id": str(pid),
            "lat": track[k]["a"],
            "lng": track[k]["o"],
            "time": int(start_ts + track[k]["t"]),
            "offset_s": round(track[k]["t"], 1),
            "distance_km": round(cum[k] / 1000.0, 2),
            "closest_m": round(best[0], 1),
            "hit": hit,
        })
    return rows


def _steps(duration_s, rnd):
    """计步桶（60s 一格）—— 真机形态：稀疏、不规则。"""
    n = max(2, int(duration_s) // 60 + 1)
    lst = []
    for _ in range(n):
        r = rnd.random()
        if r < 0.12:
            lst.append(rnd.randint(0, 6))
        elif r < 0.25:
            lst.append(rnd.randint(70, 92))
        else:
            lst.append(rnd.randint(8, 42))
    total = sum(lst)
    if total < 180:
        lst[rnd.randrange(n)] += 180 - total + rnd.randint(0, 40)
    elif total > 380:
        k = rnd.randrange(n)
        lst[k] = max(0, lst[k] - (total - rnd.randint(310, 360)))
    return {"interval": 60, "list": lst, "total": sum(lst)}


# --------------------------------------------------------------- math 引擎
def gen_math(ctx):
    rnd, seed = _seed_rng(ctx["seed"])
    pol = catalog.policy()
    anchors = catalog.route_checkpoints(ctx["campus_id"], ctx["route_id"])
    target_m = float(ctx["distance_km"]) * 1000.0
    pace = max(120, min(700, int(ctx["pace_sec"] or 330)))
    start_ts = _parse_start(ctx.get("start_at"))

    # 几何环与打卡点解耦：环决定走的形状，打卡点用原始坐标判定首通过
    ring = geo.resample_closed(catalog.route_ring(ctx["campus_id"], ctx["route_id"]), 5.0)
    start_s, cover_m = _start_phase(ring, anchors)
    ring_cum = geo.cumulative_m(ring)
    ring = _rotate_ring(ring, _index_at(ring_cum, start_s))
    coords, perimeter = _build_route(ring, target_m, rnd)
    cum = geo.cumulative_m(coords)

    # 两次校准：先把平均配速压到目标，再把合成里程压到目标
    # （速度模型有起步渐入/打卡减速/终点收速，系统性偏慢；GPS 抖动会让里程偏大）
    base_v = 1000.0 / pace
    walk_m = target_m
    best = None
    for _ in range(5):
        sub_rnd = random.Random(seed ^ 0x5F3A)
        track, min_d = _walk_route(coords, cum, anchors, walk_m, base_v, sub_rnd, start_ts)
        met = _track_metrics(track, walk_m, start_ts)
        best = (track, met, min_d)
        dist_err = met["distance_km"] * 1000.0 - target_m
        pace_err = met["avg_pace"] - pace
        if abs(dist_err) <= max(6.0, target_m * 0.002) and abs(pace_err) <= 2:
            break
        if met["avg_pace"] > 0:
            base_v *= met["avg_pace"] / pace          # 太慢 → 提速
        got = max(1.0, met["distance_km"] * 1000.0)
        walk_m = min(walk_m * (target_m / got), target_m * 3.0)
    track, met, min_d = best
    met["target_km"] = round(target_m / 1000.0, 3)

    checkins = _checkins(track, anchors, start_ts, pol["checkin_radius_m"])
    steps = _steps(met["duration_s"], random.Random(seed ^ 0xA17))
    return _result(track, met, checkins, steps, {
        "engine": "math",
        "seed": seed,
        "perimeter_m": round(perimeter, 1),
        "min_cover_km": round(cover_m / 1000.0, 2),
        "laps": round(met["distance_km"] * 1000.0 / max(1.0, perimeter), 2),
        "checkpoint_min_dist_m": [round(d, 1) for d in min_d],
        "route_points": len(coords),
    })


# --------------------------------------------------------------- template 引擎
TEMPLATE_CANDIDATES = [
    os.path.join(catalog.ROOT, "..", "data", "真实轨迹_035明文.json"),
    os.path.join(catalog.ROOT, "data", "template.json"),
]


def _template_file():
    for p in TEMPLATE_CANDIDATES:
        p = os.path.normpath(p)
        if os.path.isfile(p):
            return p
    return ""


def gen_template(ctx):
    """真人模板相似变换（需自备模板文件；缺模板时抛错，前端会提示）。"""
    tpl_path = _template_file()
    if not tpl_path:
        raise FileNotFoundError("未找到真人轨迹模板，请在 run-sim/data/template.json 放入净化模板")
    import json
    with open(tpl_path, encoding="utf-8") as f:
        tpl = json.load(f)
    pts = tpl if isinstance(tpl, list) else tpl.get("track") or tpl.get("points") or []
    if len(pts) < 30:
        raise ValueError("模板点数不足（<30），换一份净化模板")
    rnd, seed = _seed_rng(ctx["seed"])
    anchors = catalog.route_checkpoints(ctx["campus_id"], ctx["route_id"])
    target_m = float(ctx["distance_km"]) * 1000.0
    start_ts = _parse_start(ctx.get("start_at"))

    # 模板 → 目标中心 / 尺度 / 旋转，使首末点与锚点环贴合
    src = [(float(p["a"]), float(p["o"])) for p in pts]
    lat0 = sum(p[0] for p in ring) / len(ring)
    lng0 = sum(p[1] for p in ring) / len(ring)
    src_lat = sum(p[0] for p in src) / len(src)
    src_lng = sum(p[1] for p in src) / len(src)
    src_len = max(1.0, geo.path_len_m(src))
    scale = target_m / src_len
    rot = math.radians(rnd.uniform(0, 360))
    coords = []
    for la, ln in src:
        x, y = geo.enu(la, ln, src_lat, src_lng)
        x, y = x * scale, y * scale
        x, y = x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
        coords.append(geo.from_enu(x, y, lat0, lng0))
    cum = geo.cumulative_m(coords)
    track = []
    for i, (la, ln) in enumerate(coords):
        p = pts[min(i, len(pts) - 1)]
        track.append({"a": geo.quantize_geo(la), "o": geo.quantize_geo(ln),
                      "t": round(i * DT, 2),
                      "s": p.get("s"), "b": p.get("b"), "c": p.get("c")})
    for p in track:
        if p.get("s") is None:
            p.pop("s", None)
        if p.get("b") is None:
            p.pop("b", None)
        if p.get("c") is None:
            p.pop("c", None)
    met = _track_metrics(track, target_m, start_ts)
    checkins = _checkins(track, anchors, start_ts, catalog.policy()["checkin_radius_m"])
    steps = _steps(met["duration_s"], random.Random(seed ^ 0xA17))
    return _result(track, met, checkins, steps, {
        "engine": "template",
        "seed": seed,
        "template": os.path.basename(tpl_path),
        "template_points": len(pts),
    })


def _result(track, metrics, checkins, steps, meta):
    return {
        "track": track,
        "metrics": metrics,
        "checkins": checkins,
        "steps": steps,
        "meta": meta,
    }


register("math", "数学环（默认）",
         "锚点环 + 速度模型 + 打卡点减速，纯合成，无需任何真实数据", gen_math)
register("template", "真人模板",
         "相似变换真人轨迹模板，最接近真机形态；需要自备净化模板",
         gen_template, requires=[TEMPLATE_CANDIDATES[1]])


# --------------------------------------------------------------- 对外入口
def generate(campus_id, route_id, distance_km, pace_sec, start_at=None,
             seed=None, engine="math"):
    eng = ENGINES.get(engine)
    if not eng:
        raise ValueError(f"未知引擎: {engine}")
    for req in eng["requires"]:
        if not os.path.isfile(req):
            raise FileNotFoundError(f"引擎 {engine} 缺少依赖文件: {os.path.basename(req)}")
    ctx = {
        "campus_id": campus_id,
        "route_id": route_id,
        "distance_km": distance_km,
        "pace_sec": pace_sec,
        "start_at": start_at,
        "seed": seed,
        "engine": engine,
    }
    out = eng["fn"](ctx)
    out["params"] = {
        "campus_id": campus_id,
        "route_id": route_id,
        "distance_km": round(float(distance_km), 3),
        "pace_sec": int(pace_sec),
        "start_at": start_at or "",
        "seed": out["meta"].get("seed"),
        "engine": engine,
    }
    return out
