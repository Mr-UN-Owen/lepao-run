# -*- coding: utf-8 -*-
"""run-sim.sim.submit —— 提交适配器（v0.1 只有 dry-run 骨架，刻意不联网）。

设计意图：站点先做「生成 + 预检 + 导出」，真正对接平台是后续阶段的独立工作。
这里把接口钉死，后续加适配器不用动 server.py / 前端：

    register_adapter(name, label, description, fn)
    fn(record, opts) -> {"ok": bool, "steps": [{"name","ok","detail"}], ...}

内置：
    offline —— 干跑计划：只读展示「真机提交链」会经过哪些阶段，零网络请求。
    后续可加 lepao / 学校自定义适配器（需要自备合法账号与已授权身份）。
"""
import time

ADAPTERS = {}


def register_adapter(name, label, description, fn):
    ADAPTERS[name] = {"name": name, "label": label,
                      "description": description, "fn": fn}


def adapter_list():
    return [{"name": a["name"], "label": a["label"], "description": a["description"]}
            for a in ADAPTERS.values()]


def _offline(record, opts=None):
    m = record.get("metrics") or {}
    steps = [
        ("准备身份与鉴权", "占位：接入合法账号的会话/凭证", "skip"),
        ("获取跑区与打卡点", f"已本地持有 {len(record.get('checkins') or [])} 个打卡点", "pass"),
        ("校验当日额度", f"本地已记 {opts.get('day_count', '?') if opts else '?'} 条", "pass"),
        ("上传轨迹文件", "占位：OSS / 平台文件接口", "skip"),
        ("提交跑步记录", f"占位：{m.get('distance_km')} km / {m.get('duration_s')} s", "skip"),
        ("复核记录状态", "占位：轮询记录状态接口", "skip"),
    ]
    return {
        "ok": True,
        "adapter": "offline",
        "dry_run": True,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "steps": [{"name": n, "detail": d, "state": s} for n, d, s in steps],
        "note": "v0.1 只做本地预演，不产生任何网络请求；对接平台需另行实现适配器。",
    }


register_adapter("offline", "离线预演（默认）",
                 "只输出提交链阶段清单，零网络请求", _offline)


def submit(record, adapter="offline", opts=None):
    a = ADAPTERS.get(adapter)
    if not a:
        raise KeyError(f"未知提交适配器: {adapter}")
    return a["fn"](record, opts or {})
