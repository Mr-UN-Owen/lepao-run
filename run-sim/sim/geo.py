# -*- coding: utf-8 -*-
"""run-sim.sim.geo —— 地理计算原语（零依赖）。

设计原则：只放纯函数，所有上层（engine / validate / exporters）都复用这里，
换椭球模型或换距离算法时只改一个文件。
"""
import math

EARTH_R = 6371000.0  # 米，球面近似（与真机 haversine 口径一致）
QUANT = 3600000.0    # 真机经纬度量化分母：1/3600000°


def haversine_m(lat1, lng1, lat2, lng2):
    """两点球面距离（米）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(min(1.0, a)))


def offset_m(lat, lng, north_m, east_m):
    """以米为单位的 NE 偏移 → 新坐标（小范围平面近似，校园尺度足够）。"""
    nlat = lat + north_m / 111320.0
    nlng = lng + east_m / (111320.0 * max(math.cos(math.radians(lat)), 1e-6))
    return nlat, nlng


def enu(lat, lng, lat0, lng0):
    """经纬度 → 以 (lat0,lng0) 为原点的东-北平面坐标（米）。"""
    return ((lng - lng0) * 111320.0 * math.cos(math.radians(lat0)),
            (lat - lat0) * 111320.0)


def from_enu(x, y, lat0, lng0):
    """东-北平面坐标（米）→ 经纬度。"""
    return (lat0 + y / 111320.0,
            lng0 + x / (111320.0 * max(math.cos(math.radians(lat0)), 1e-6)))


def quantize_geo(v):
    """真机坐标量化（1/3600000°）。"""
    return int(round(v * QUANT)) / QUANT


def path_len_m(coords):
    """折线长度（米）。coords: [(lat,lng), ...]"""
    return sum(haversine_m(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
               for i in range(1, len(coords)))


def cumulative_m(coords):
    """累计里程数组，与 coords 等长，首项 0.0。"""
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + haversine_m(coords[i - 1][0], coords[i - 1][1],
                                         coords[i][0], coords[i][1]))
    return cum


def position_at(coords, cum, s):
    """按里程 s 在折线上线性插值取点 → (lat, lng)。"""
    if not coords:
        raise ValueError("empty path")
    s = max(0.0, min(float(s), cum[-1]))
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < s:
            lo = mid + 1
        else:
            hi = mid
    i = max(lo - 1, 0)
    seg = cum[i + 1] - cum[i] if i + 1 < len(cum) else 0.0
    t = 0.0 if seg <= 0 else (s - cum[i]) / seg
    a, b = coords[i], coords[min(i + 1, len(coords) - 1)]
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def catmull_rom_closed(points, step_m=4.0):
    """闭合 Catmull-Rom 样条加密。points: [(lat,lng)] → 加密后的闭合折线。

    用平面 ENU 坐标做插值再转回经纬度，避免在高纬出现形状畸变。
    首尾点重合（闭合）。
    """
    if len(points) < 3:
        return list(points) + [points[0]]
    lat0 = sum(p[0] for p in points) / len(points)
    lng0 = sum(p[1] for p in points) / len(points)
    xy = [enu(p[0], p[1], lat0, lng0) for p in points]
    n = len(xy)
    out = []
    for i in range(n):
        p0 = xy[(i - 1) % n]
        p1 = xy[i]
        p2 = xy[(i + 1) % n]
        p3 = xy[(i + 2) % n]
        seg = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        steps = max(2, int(math.ceil(seg / max(0.5, step_m))))
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append(from_enu(x, y, lat0, lng0))
    out.append(out[0])
    return out


def oval_anchors(center, rx_m, ry_m, n=4, phase_deg=45.0):
    """椭圆（田径场）上均匀取 n 个锚点 → [(lat,lng)]。rx 为南北半轴。"""
    lat0, lng0 = center
    out = []
    for k in range(n):
        ang = math.radians(phase_deg) + 2 * math.pi * k / n
        x = ry_m * math.cos(ang)   # 东西
        y = rx_m * math.sin(ang)   # 南北
        out.append(offset_m(lat0, lng0, y, x))
    return out


def bearing_deg(lat1, lng1, lat2, lng2):
    """方位角（0=北，顺时针）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def bounds(coords, pad_ratio=0.08):
    """点集外包框 → {north, south, east, west}，带比例留白。"""
    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    la_min, la_max = min(lats), max(lats)
    ln_min, ln_max = min(lngs), max(lngs)
    dla = max(1e-5, la_max - la_min) * pad_ratio
    dln = max(1e-5, ln_max - ln_min) * pad_ratio
    return {"north": la_max + dla, "south": la_min - dla,
            "east": ln_max + dln, "west": ln_min - dln}


def ellipse_ring(center, rx_m, ry_m, n=48, phase_deg=0.0):
    """椭圆闭环（田径场形态）：按角度均匀取 n 点，闭合。"""
    lat0, lng0 = center
    out = []
    for k in range(n):
        ang = math.radians(phase_deg) + 2 * math.pi * k / n
        out.append(offset_m(lat0, lng0, rx_m * math.sin(ang), ry_m * math.cos(ang)))
    out.append(out[0])
    return out


def chaikin_closed(points, iterations=2, ratio=0.18):
    """Chaikin 角切平滑：把折线拐角磨圆，保留直边（比 Catmull-Rom 更"贴路"）。"""
    out = [(p[0], p[1]) for p in points]
    for _ in range(max(0, iterations)):
        new = []
        n = len(out)
        for i in range(n):
            a, b = out[i], out[(i + 1) % n]
            new.append((a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio))
            new.append((a[0] + (b[0] - a[0]) * (1 - ratio), a[1] + (b[1] - a[1]) * (1 - ratio)))
        out = new
    out.append(out[0])
    return out


def project_point(coords, lat, lng):
    """点投影到折线：返回 (沿里程 s, 最近距离 m, 段索引)。"""
    best_d, best_s, best_i = 1e18, 0.0, 0
    for i in range(len(coords) - 1):
        ax, ay = enu(coords[i][0], coords[i][1], lat, lng)
        bx, by = enu(coords[i + 1][0], coords[i + 1][1], lat, lng)
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 <= 1e-9 else max(0.0, min(1.0, -(ax * dx + ay * dy) / l2))
        px, py = ax + dx * t, ay + dy * t
        d = math.hypot(px, py)
        if d < best_d:
            best_d = d
            best_s = cum_s(coords, i) + math.hypot(dx, dy) * t
            best_i = i
    return best_s, best_d, best_i


def cum_s(coords, i):
    """第 i 段起点处的累计里程（内部用，带缓存）。"""
    key = id(coords)
    cache = _CUM_CACHE.get(key)
    if cache is None or cache[0] is not coords or cache[1] != len(coords):
        cache = (coords, len(coords), cumulative_m(coords))
        _CUM_CACHE[key] = cache
    return cache[2][i]


_CUM_CACHE = {}


def resample_closed(coords, step_m=5.0):
    """闭合折线按固定步长重采样（起点保持 coords[0]），返回闭合点列。"""
    if len(coords) < 2:
        return list(coords)
    body = coords[:-1] if coords[0] == coords[-1] else coords
    body = body + [body[0]]
    cum = cumulative_m(body)
    total = cum[-1]
    if total <= 0:
        return list(body)
    n = max(8, int(round(total / max(0.5, step_m))))
    out = []
    for k in range(n):
        out.append(position_at(body, cum, total * k / n))
    out.append(out[0])
    return out
