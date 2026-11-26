# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.refresh —— token 续期（loginByCode 抓一次 → refresh 续命，不必反复开小程序）

背景（实证）:
  - v3 主 API 只有 `WpLogin/loginByCode` 一个匿名登录口（微信 code 换 token），
    `Login/*` 全部在 token 门后（无 token 恒 101）——没有学号/密码登录端点。
  - 但 loginByCode 的响应带 `token_data.refresh_token` + `refresh_expire`（≈30 天）,
    对应端点 `Login/RefreshToken`（APK 内 `com.lptiyu.tanke` 的 Login 模块实证）。
  - token 本身无统一 TTL，只在「再次 loginByCode」时被顶号；refresh 的价值是
    在服务端显式失效/轮换后还能自愈，并把「每天开小程序」降到「每 30 天开一次」。

用法:
  from lepao.refresh import try_refresh, probe_alive
  r = try_refresh(uid, token, refresh_token, school_id=798, host="api2.lptiyu.com")
  if r["ok"]: new_token = r["token"]

`Login/RefreshToken` 的入参形态在不同版本间有差异，这里按「由严到宽」逐个试，
任一形态返回 access_token 即判定成功；全部失败返回 ok=False 并给出每次的错误文案。
"""
import time

from .v3api import V3Client, V3Error

REFRESH_PATH = "/v3/api.php/Login/RefreshToken"

# (标签, 用作 token 字段的值, 业务参数)
VARIANTS = (
    ("at+rt(body)", "at", lambda at, rt, uid: {"refresh_token": rt}),
    ("at+rt(uid,body)", "at", lambda at, rt, uid: {"refresh_token": rt, "uid": uid}),
    ("at+both(body)", "at", lambda at, rt, uid: {"access_token": at, "refresh_token": rt}),
    ("rt-as-token", "rt", lambda at, rt, uid: {"refresh_token": rt}),
    ("at+rt(ty=2)", "at", lambda at, rt, uid: {"refresh_token": rt, "ty": "2"}),
)


def _extract(j):
    """从响应里挖出 (access_token, refresh_token, refresh_expire)。"""
    if not isinstance(j, dict):
        return "", "", 0
    pools = [j]
    for k in ("data", "token_data", "auth_data", "user"):
        v = j.get(k)
        if isinstance(v, dict):
            pools.append(v)
    at = rt = ""
    exp = 0
    for p in pools:
        at = at or str(p.get("access_token") or p.get("token") or "")
        rt = rt or str(p.get("refresh_token") or "")
        try:
            exp = exp or int(p.get("refresh_expire") or 0)
        except (TypeError, ValueError):
            pass
    return at, rt, exp


def probe_alive(uid, token, school_id, host="api2.lptiyu.com", proxy=None,
                student_num="", card_id="", timeout=15):
    """真门探测：getTermList 不回 101 即视为活着。返回 (alive, info)。"""
    if not token:
        return False, "无 token"
    c = V3Client(uid=str(uid or ""), token=token, school_id=school_id,
                 student_num=student_num, card_id=card_id, host=host,
                 proxy=proxy, timeout=timeout)
    try:
        r = c.get_term_list()
    except V3Error as e:
        return False, f"V3Error({e.code}) {e.msg[:80]}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    if isinstance(r, dict) and str(r.get("status")) == "101":
        return False, "101 登录信息失效"
    return True, "ok"


def try_refresh(uid, token, refresh_token, school_id, host="api2.lptiyu.com",
                proxy=None, student_num="", card_id="", timeout=15, verbose=True):
    """逐个变体尝试续期。返回 dict：
       {"ok": bool, "token": str, "refresh_token": str, "refresh_expire": int,
        "variant": str, "log": [{"variant","status","info"}...]}
    """
    out = {"ok": False, "token": "", "refresh_token": refresh_token or "",
           "refresh_expire": 0, "variant": "", "log": []}
    if not refresh_token:
        out["log"].append({"variant": "-", "status": 0, "info": "无 refresh_token"})
        return out
    for label, tok_kind, body_fn in VARIANTS:
        tok = token if tok_kind == "at" else refresh_token
        if tok_kind == "at" and not token:
            continue
        c = V3Client(uid=str(uid or ""), token=tok, school_id=school_id,
                     student_num=student_num, card_id=card_id, host=host,
                     proxy=proxy, timeout=timeout)
        try:
            j = c.post(REFRESH_PATH, body_fn(token or "", refresh_token, str(uid or "")))
        except V3Error as e:
            out["log"].append({"variant": label, "status": e.code, "info": e.msg[:120]})
            if verbose:
                print(f"[refresh] {label} → V3Error({e.code}) {e.msg[:100]}")
            continue
        except Exception as e:  # noqa: BLE001
            out["log"].append({"variant": label, "status": -1,
                               "info": f"{type(e).__name__}: {e}"})
            if verbose:
                print(f"[refresh] {label} → {type(e).__name__}: {e}")
            continue
        st = j.get("status") if isinstance(j, dict) else None
        at, rt, exp = _extract(j)
        out["log"].append({"variant": label, "status": st,
                           "info": (j.get("info") if isinstance(j, dict) else "") or ""})
        if at:
            out.update({"ok": True, "token": at,
                        "refresh_token": rt or refresh_token,
                        "refresh_expire": exp, "variant": label})
            if verbose:
                print(f"[refresh] {label} ✔ 新 token={at[:8]}… "
                      f"refresh={'轮换' if rt else '沿用'} expire={exp or '-'}")
            return out
        if verbose:
            info = j.get("info") if isinstance(j, dict) else ""
            print(f"[refresh] {label} → status={st} {str(info)[:100]}")
        time.sleep(0.6)
    return out
