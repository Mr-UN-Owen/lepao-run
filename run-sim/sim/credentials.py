# -*- coding: utf-8 -*-
"""run-sim.sim.credentials —— 本机账号档案（学号 / token / 出口）。

只写本机 `run-sim/data/credentials.json`（已 gitignore），不外发。
token 是平台侧的「单活动会话消耗品」：抓号一次只能用一轮，用完要重抓。
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
FILE = os.path.join(DATA, "credentials.json")

DEFAULT = {
    "student_num": "",
    "name": "",
    "uid": 0,
    "school_id": 0,
    "token": "",
    "token_issued_at": "",
    "api_host": "api2.lptiyu.com",
    "proxy": "127.0.0.1:8081",
}

SECRET_KEYS = ("token",)


def _mask(v):
    if not v:
        return ""
    s = str(v)
    return s[:4] + "*" * max(4, len(s) - 8) + s[-4:] if len(s) > 10 else s[:2] + "***"


def load():
    out = dict(DEFAULT)
    try:
        with open(FILE, encoding="utf-8") as f:
            out.update(json.load(f) or {})
    except (OSError, ValueError):
        pass
    return out


def public():
    """给前端的脱敏视图（token 只回显掩码 + 是否有值）。"""
    c = load()
    view = {k: v for k, v in c.items() if k not in SECRET_KEYS}
    view["token_set"] = bool(c.get("token"))
    view["token_mask"] = _mask(c.get("token"))
    view["has_uid"] = bool(c.get("uid"))
    return view


def save(patch):
    c = load()
    for k in ("student_num", "name", "token", "api_host", "proxy", "token_issued_at"):
        if k in patch and patch[k] is not None:
            c[k] = str(patch[k]).strip()
    for k in ("uid", "school_id"):
        if k in patch and patch[k] not in (None, ""):
            try:
                c[k] = int(patch[k])
            except (TypeError, ValueError):
                pass
    if patch.get("token"):
        c["token_issued_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # 别名：ver 字段与 store 的 profile 对齐
    if patch.get("name"):
        c["name"] = str(patch["name"]).strip()
    os.makedirs(DATA, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)
    return public()


def clear_token():
    c = load()
    c["token"] = ""
    c["token_issued_at"] = ""
    os.makedirs(DATA, exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
    return public()
