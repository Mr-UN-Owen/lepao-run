# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""mitm 抓号插件（白名单 = 已登记成员）

用法（由 lepao/capture.py 自动拉起）:
  mitmdump -q -s 工具/mitm_lptiyu_token.py -p 8081 --ssl-insecure

行为:
  - 只观测 lptiyu 域的登录响应（loginByCode / Login/login），其余流量一律放行不落盘。
  - 解密 v3 响应（AES-128-CBC + base64），取 uid/token/学号/卡号。
  - **白名单二次校验**：身份不在 config.json 成员表 → 不落盘（打印一行提示）。
  - 落 `凭证.json`（数据目录；0600；仅最新 20 条），供 capture 归位。
  - 不修改任何请求/响应（纯被动观测），不上传任何数据。

环境变量:
  LEPAO_CONFIG    成员表 config.json 路径（capture 自动注入）
  LEPAO_DATA_DIR  凭证落盘目录（缺省=config.json 所在目录）
"""
import json
import os
import sys
import tempfile
import time

from mitmproxy import http

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

try:
    from lepao.crypto import decrypt_data
except Exception:  # noqa: BLE001 - 无 pycryptodome 时降级为只抓明文
    decrypt_data = None

HOST_SUFFIXES = ("lptiyu.com",)
LOGIN_PATHS = ("loginByCode", "Login/login", "WpLogin/loginByCode")
CRED_FILE = "凭证.json"
MAX_RECORDS = 20


def _data_dir():
    d = os.environ.get("LEPAO_DATA_DIR", "").strip()
    if d:
        return os.path.abspath(d)
    cfg = os.environ.get("LEPAO_CONFIG", "").strip()
    if cfg:
        return os.path.dirname(os.path.abspath(cfg))
    return _REPO


def _cfg_path():
    cfg = os.environ.get("LEPAO_CONFIG", "").strip()
    if cfg:
        return os.path.abspath(cfg)
    return os.path.join(_REPO, "config.json")


def _whitelist():
    """读成员表 → (uid集合, 学号集合, 卡号集合)。读不到返回空集合（= 一律不落盘）。"""
    uid, num, card = set(), set(), set()
    path = _cfg_path()
    if not os.path.isfile(path):
        return uid, num, card
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return uid, num, card
    accs = cfg.get("accounts") or {}
    if not isinstance(accs, dict):
        return uid, num, card
    for k, prof in accs.items():
        if not isinstance(prof, dict) or not prof.get("enabled", True):
            continue
        if prof.get("uid"):
            uid.add(str(prof["uid"]))
        for f in ("student_num", "card_id"):
            v = str(prof.get(f) or "").strip()
            if v:
                (num if f == "student_num" else card).add(v)
        if k:
            num.add(str(k))
    return uid, num, card


def _atomic_json(path, data):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_cred_", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _load_records(path):
    if not os.path.isfile(path):
        return {"version": 1, "records": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "records": []}
    if isinstance(data, dict):
        data.setdefault("records", [])
        return data
    if isinstance(data, list):
        return {"version": 1, "records": data}
    return {"version": 1, "records": []}


def _parse_payload(raw):
    """响应体 → dict（v3 加密 data 自动解密；明文 JSON 直接返回）。"""
    try:
        j = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(j, dict):
        return None
    data = j.get("data")
    if isinstance(data, str) and len(data) > 32 and decrypt_data is not None:
        try:
            inner = json.loads(decrypt_data(data))
            if isinstance(inner, dict):
                return inner
        except Exception:  # noqa: BLE001
            pass
    return j


class LepaoTokenAddon:
    """被动抓号：登录响应里出现 token 就落盘（白名单校验后）。"""

    def __init__(self):
        self._dir = _data_dir()
        self._seen_tokens = set()

    def response(self, flow: http.HTTPFlow):
        req = flow.request
        if not any(req.pretty_host.endswith(s) for s in HOST_SUFFIXES):
            return
        path = req.path or ""
        if not any(p in path for p in LOGIN_PATHS):
            return
        body = flow.response.get_text(strict=False) if flow.response else ""
        if not body:
            return
        j = _parse_payload(body)
        if not isinstance(j, dict):
            return
        token = str(j.get("token") or j.get("access_token") or "").strip()
        if not token:
            return
        if token in self._seen_tokens:
            return
        rec = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "uid": j.get("uid") or j.get("user_id") or "",
            "student_num": str(j.get("student_num") or j.get("student_num_str") or ""),
            "card_id": str(j.get("card_id") or ""),
            "school_id": j.get("school_id") or 0,
            "name": j.get("name") or j.get("nickname") or "",
            "token": token,
            "refresh_token": str(j.get("refresh_token") or ""),
            "refresh_expire": int(j.get("refresh_expire") or 0),
            "source": "mitm-loginByCode",
            "host": req.pretty_host,
            "path": path.split("?")[0],
        }
        uid_wl, num_wl, card_wl = _whitelist()
        if not (str(rec["uid"]) in uid_wl
                or rec["student_num"] in num_wl
                or rec["card_id"] in card_wl):
            print(f"[addon] 丢弃未登记身份的凭证 uid={rec['uid']!r} "
                  f"学号={rec['student_num']!r}（先 account add 登记）", flush=True)
            return
        path_out = os.path.join(self._dir, CRED_FILE)
        data = _load_records(path_out)
        data["records"] = (data.get("records") or []) + [rec]
        del data["records"][:-MAX_RECORDS]
        data["updated_at"] = rec["at"]
        _atomic_json(path_out, data)
        self._seen_tokens.add(token)
        print(f"[addon] 已捕获登录凭证 uid={rec['uid']} 学号={rec['student_num'] or '-'} "
              f"→ {CRED_FILE}", flush=True)


addons = [LepaoTokenAddon()]
