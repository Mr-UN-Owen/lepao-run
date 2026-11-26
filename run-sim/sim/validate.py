# -*- coding: utf-8 -*-
"""run-sim.sim.validate —— 提交前预检（本地规则引擎，与"能不能真过"是两回事）。

每条规则独立：{id, level: pass|warn|fail, title, detail}。
新增规则 = 在 RULES 里追加一个函数，前端自动展示，无需改前端。
"""
import datetime as _dt

from . import catalog, geo

CHECK_RADIUS_DEFAULT = 40.0


def _fmt_pace(sec):
    sec = int(round(sec))
    return f"{sec // 60}'{sec % 60:02d}\""


def rule_distance(res, pol):
    km = res["metrics"]["distance_km"]
    lo, hi = float(pol["dist_lo_km"]), float(pol["dist_hi_km"])
    # 平台按 0.01 km 取整比较，留 0.02 km 容差，避免 1.988 vs 2.00 这种误杀
    if lo - 0.02 <= km <= hi + 0.02:
        return dict(level="pass", title="单次里程在有效区间",
                    detail=f"{km:.2f} km ∈ [{lo:g}, {hi:g}] km")
    return dict(level="fail", title="单次里程超出有效区间",
                detail=f"{km:.2f} km 不在 [{lo:g}, {hi:g}] km 内，调距离参数")


def rule_pace(res, pol):
    p = res["metrics"]["avg_pace"]
    lo, hi = int(pol["pace_lo"]), int(pol["pace_hi"])
    if lo <= p <= hi:
        return dict(level="pass", title="平均配速在合理区间",
                    detail=f"{_fmt_pace(p)}/km ∈ [{_fmt_pace(lo)}, {_fmt_pace(hi)}]")
    return dict(level="fail", title="平均配速超出合理区间",
                detail=f"{_fmt_pace(p)}/km 不在 [{_fmt_pace(lo)}, {_fmt_pace(hi)}] 内")


def rule_checkpoints(res, pol):
    radius = float(pol.get("checkin_radius_m") or CHECK_RADIUS_DEFAULT)
    cps = res["checkins"]
    miss = [c for c in cps if not c["hit"]]
    worst = max((c["closest_m"] for c in cps), default=0.0)
    if not miss:
        return dict(level="pass", title=f"{len(cps)} 个打卡点全部命中",
                    detail=f"最远首通过偏差 {worst:.1f} m ≤ {radius:g} m")
    return dict(level="fail", title=f"有 {len(miss)} 个打卡点未命中",
                detail="未命中: " + ", ".join(f"{c['point_id']}({c['closest_m']:.0f}m)" for c in miss))


def rule_time_window(res, pol):
    hours = pol.get("allowed_hours") or [6.0, 22.5]
    lo, hi = float(hours[0]), float(hours[1])
    st = _dt.datetime.fromtimestamp(res["metrics"]["start_ts"])
    et = _dt.datetime.fromtimestamp(res["metrics"]["end_ts"])
    h1 = st.hour + st.minute / 60.0
    h2 = et.hour + et.minute / 60.0
    if lo <= h1 and h2 <= hi:
        return dict(level="pass", title="起止时间在开放时段内",
                    detail=f"{st:%H:%M} → {et:%H:%M} ∈ [{lo:g}:00, {hi:g}]")
    return dict(level="fail", title="起止时间超出开放时段",
                detail=f"{st:%H:%M} → {et:%H:%M} 不在 [{lo:g}:00, {hi:g}] 内")


def rule_continuity(res, pol):
    track = res["track"]
    worst, idx = 0.0, 0
    for i in range(1, len(track)):
        d = geo.haversine_m(track[i - 1]["a"], track[i - 1]["o"],
                            track[i]["a"], track[i]["o"])
        if d > worst:
            worst, idx = d, i
    if len(track) < 40:
        return dict(level="warn", title="轨迹点偏少",
                    detail=f"仅 {len(track)} 点，建议 ≥ 40 点")
    if worst > 60.0:
        return dict(level="warn", title="存在异常跳点",
                    detail=f"第 {idx} 点相邻位移 {worst:.0f} m > 60 m")
    return dict(level="pass", title="轨迹连续、无跳点",
                detail=f"{len(track)} 点，最大相邻位移 {worst:.1f} m")


def rule_target_match(res, pol):
    want = res["metrics"]["target_km"]
    got = res["metrics"]["distance_km"]
    dev = abs(got - want) / max(0.001, want)
    if dev <= 0.03:
        return dict(level="pass", title="合成里程与目标一致",
                    detail=f"目标 {want:.2f} km / 实际 {got:.2f} km（偏差 {dev * 100:.1f}%）")
    return dict(level="warn", title="合成里程偏离目标",
                detail=f"目标 {want:.2f} km / 实际 {got:.2f} km（偏差 {dev * 100:.1f}%）")


def rule_daily(res, pol, records=None, exclude_id=""):
    limit = int(pol.get("max_per_day") or 1)
    day = _dt.datetime.fromtimestamp(res["metrics"]["start_ts"]).strftime("%Y-%m-%d")
    same = [r for r in (records or [])
            if str(r.get("day")) == day and r.get("id") != exclude_id]
    if len(same) < limit:
        return dict(level="pass", title="当日额度充足",
                    detail=f"{day} 已记 {len(same)} 条 / 上限 {limit} 条")
    return dict(level="fail", title="当日额度已满",
                detail=f"{day} 已记 {len(same)} 条，上限 {limit} 条（仅本地统计）")


RULES = [
    ("distance", rule_distance),
    ("pace", rule_pace),
    ("checkpoints", rule_checkpoints),
    ("time_window", rule_time_window),
    ("continuity", rule_continuity),
    ("target_match", rule_target_match),
]


def validate(res, records=None, exclude_id=""):
    pol = catalog.policy()
    items = []
    for rid, fn in RULES:
        try:
            item = fn(res, pol)
        except Exception as e:  # noqa: BLE001  规则自身异常不影响其他规则
            item = dict(level="warn", title=f"规则 {rid} 执行失败", detail=str(e))
        item["id"] = rid
        items.append(item)
    item = rule_daily(res, pol, records, exclude_id)
    item["id"] = "daily"
    items.append(item)

    levels = [i["level"] for i in items]
    verdict = "fail" if "fail" in levels else ("warn" if "warn" in levels else "pass")
    return {
        "verdict": verdict,
        "passed": sum(1 for lv in levels if lv == "pass"),
        "total": len(items),
        "items": items,
    }
