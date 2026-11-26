# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.realism —— 真人跑步行为模型（轨迹"逼真化"参数与生成器）

对照参考：LePaoRunner（github.com/zgbjhk/LePaoRunner）的 run 参数组。
它是"模拟器注入"路线，我们是"协议直连"路线，但**要骗过的是同一套行为判定**，
所以它那组参数是可直接借用的行业经验值：

    speed_jitter_pct  6.0    配速随机波动
    update_hz         1.0    采样频率（按时间采，不是按距离）
    gps_noise_m       1.8    定位漂移
    warmup_s          45.0   起步渐变
    cooldown_s        20.0   收尾渐变
    lap_line_drift_m  1.6    每圈起跑线横向漂移
    traffic_events    true   偶发停顿
    cadence           0      步频自动（按速度推算）

本模块把这些落成可复用的函数：
    speed_curve()    → 逐秒速度序列（含热身/冷却/抖动/停顿）
    step_info_of()   → 由速度序列反推每分钟步数（与速度自洽）
    cadence_of()     → 速度 → 步频
"""

import math
import random

# ---- 默认参数（可在调用处覆盖）----
REALISM = {
    "speed_jitter_pct": 6.0,      # 配速波动 ±6%
    "sample_hz": 1.0,             # 1 秒一个点
    "gps_noise_m": 1.2,           # GPS 漂移（米），不能与点间距同量级
    "warmup_s": 45.0,             # 起步渐变
    "cooldown_s": 20.0,           # 收尾渐变
    "pause_probability": 0.65,    # 中途出现停顿的概率
    "pause_seconds": (2, 7),      # 单次停顿时长范围
    "lap_drift_m": 1.6,           # 每圈横向漂移
    "stride_m": 1.15,             # 步幅（米/步），用于把速度换成步频
    "cadence_min": 150,           # 步频下限（步/分）
    "cadence_max": 190,           # 步频上限
}


def _warmup_factor(t, warmup_s):
    """起步：从 55% 速度线性爬到 100%。"""
    if warmup_s <= 0 or t >= warmup_s:
        return 1.0
    return 0.55 + 0.45 * (t / float(warmup_s))


def _cooldown_factor(remain_s, cooldown_s):
    """收尾：最后 cooldown_s 秒从 100% 线性降到 45%。"""
    if cooldown_s <= 0 or remain_s >= cooldown_s:
        return 1.0
    return 0.45 + 0.55 * max(remain_s, 0.0) / float(cooldown_s)


def speed_curve(base_speed, total_s, rnd=None, **kw):
    """逐秒速度序列（m/s）。

    base_speed: 目标巡航速度（m/s）
    total_s:    预计总时长（秒）
    返回 list[float]，长度 = total_s
    """
    p = dict(REALISM)
    p.update({k: v for k, v in kw.items() if v is not None})
    rnd = rnd or random.Random()
    jit = float(p["speed_jitter_pct"]) / 100.0
    warm, cool = float(p["warmup_s"]), float(p["cooldown_s"])

    # 停顿窗口：在"热身之后、冷却之前"的区间里随机撒 0~2 次
    pauses = []
    if rnd.random() < float(p["pause_probability"]):
        n = 1 if rnd.random() < 0.75 else 2
        lo = int(warm + 10)
        hi = max(lo + 1, int(total_s - cool - 10))
        for _ in range(n):
            start = rnd.randint(lo, hi)
            dur = rnd.randint(*p["pause_seconds"])
            pauses.append((start, start + dur))

    speeds = []
    v_smooth = base_speed
    for t in range(int(total_s)):
        v = base_speed * (1.0 + rnd.uniform(-jit, jit))
        # 一阶低通：真人不会每秒独立跳变
        v_smooth = 0.6 * v_smooth + 0.4 * v
        v = v_smooth
        v *= _warmup_factor(t, warm)
        v *= _cooldown_factor(total_s - t, cool)
        for a, b in pauses:
            if a <= t < b:
                v = 0.0
                break
        speeds.append(max(0.0, v))
    return speeds


def cadence_of(v_mps, stride_m=1.15, lo=150, hi=190):
    """速度(m/s) → 步频(步/分)。stride 默认 1.15 米/步。"""
    if v_mps <= 0.2:
        return 0
    c = v_mps * 60.0 / float(stride_m)
    return int(max(lo, min(hi, round(c))))


def step_info_of(speeds, interval=60, **kw):
    """由逐秒速度反推 step_info（每分钟步数），保证与距离/配速自洽。"""
    p = dict(REALISM)
    p.update({k: v for k, v in kw.items() if v is not None})
    stride = float(p["stride_m"])
    lst = []
    for i in range(0, len(speeds), interval):
        chunk = speeds[i:i + interval]
        if not chunk:
            break
        avg = sum(chunk) / len(chunk)
        lst.append(cadence_of(avg, stride, p["cadence_min"], p["cadence_max"]))
    if not lst:
        lst = [0]
    return {"interval": interval, "list": lst}


def total_steps(step_info):
    return int(sum(step_info.get("list") or []))


def summarize(speeds):
    """给日志/界面用的摘要。"""
    if not speeds:
        return {}
    nz = [v for v in speeds if v > 0]
    avg = sum(speeds) / len(speeds)
    var = sum((v - avg) ** 2 for v in speeds) / len(speeds)
    return {
        "samples": len(speeds),
        "avg_mps": round(avg, 3),
        "max_mps": round(max(speeds), 3),
        "min_mps_nonzero": round(min(nz), 3) if nz else 0.0,
        "std_mps": round(math.sqrt(var), 3),
        "zero_samples": sum(1 for v in speeds if v == 0),
    }
