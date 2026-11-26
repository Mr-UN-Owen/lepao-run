# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.state —— 运行证据链持久化（state.json）

只做一件事: 把 dry-run 参数、提交结果、复核结论按时间落盘，供事后对账与 `watch`。
- 文件权限 0600、原子写；仅存本机（.gitignore 已排除，永不入库）。
- 每条记录带 uid + 成员标识，便于多成员场景区分（LRL-1.0: 数据仅存本地）。
"""
import copy
import json
import os
import tempfile
import time

MAX_RECORDS = 50


def _now_iso():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class StateStore:
    """state.json 读写。路径默认 = 配置文件同目录。"""

    def __init__(self, path=None, verbose=True):
        self.path = os.path.abspath(path or os.path.join(os.getcwd(), "state.json"))
        self.verbose = verbose
        self.data = {"version": 1, "updated_at": "", "dryruns": [], "submissions": []}
        if os.path.isfile(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self.data.update(raw)
            except (json.JSONDecodeError, OSError):
                # 坏文件不阻塞打卡: 另存坏副本后从空证据链开始
                try:
                    os.replace(self.path, self.path + ".broken")
                except OSError:
                    pass
                if self.verbose:
                    print(f"[state] {self.path} 解析失败, 已重命名为 .broken 并重建")
        self.data.setdefault("dryruns", [])
        self.data.setdefault("submissions", [])

    # ------------------------------------------------------------ 底层
    def _flush(self):
        self.data["updated_at"] = _now_iso()
        d = os.path.dirname(self.path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp_state_", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return self.path

    def _append(self, bucket, item):
        lst = self.data.setdefault(bucket, [])
        lst.append(item)
        del lst[:-MAX_RECORDS]
        return self._flush()

    # ------------------------------------------------------------ 写入
    def save_dryrun(self, out, uid=None, member=None):
        """记录 dry-run 产出的完整 stopRun 业务参数（零写入证明）。"""
        rec = {
            "at": _now_iso(),
            "kind": "dryrun",
            "uid": uid,
            "member": member or "",
            "track_points": (out or {}).get("track_points"),
            "oss_record_file": (out or {}).get("oss_record_file"),
            "stopRun_biz": copy.deepcopy((out or {}).get("stopRun_biz") or {}),
            "log_data": copy.deepcopy((out or {}).get("log_data") or [])[:50],
            "meta": copy.deepcopy((out or {}).get("meta") or {}),
        }
        self._append("dryruns", rec)
        if self.verbose:
            print(f"[state] dry-run 已存证 ({rec['oss_record_file']}) → {self.path}")
        return rec

    def save_submission(self, summary):
        """记录 stopRun 响应 + 复核结论（positive 判定依据）。"""
        rec = {
            "at": _now_iso(),
            "kind": "submission",
            "record_id": (summary or {}).get("record_id"),
            "uid": (summary or {}).get("uid"),
            "member": (summary or {}).get("member") or "",
            "distance": (summary or {}).get("distance"),
            "used_time": (summary or {}).get("used_time"),
            "record_status": (summary or {}).get("record_status"),
            "record_failed_reason": (summary or {}).get("record_failed_reason") or "",
            "game_id": (summary or {}).get("game_id"),
            "style": (summary or {}).get("style"),
        }
        self._append("submissions", rec)
        if self.verbose:
            print(f"[state] 提交结论已存证 record_id={rec['record_id']} "
                  f"status={rec['record_status']}")
        return rec

    # ------------------------------------------------------------ 读取
    def load(self):
        return self.data

    def last_dryrun(self):
        return (self.data.get("dryruns") or [None])[-1]

    def last_submission(self):
        return (self.data.get("submissions") or [None])[-1]

    def submissions_since(self, ts):
        return [r for r in self.data.get("submissions") or []
                if float(r.get("at_ts") or 0) >= ts or r.get("at", "") >= str(ts)]

    def find_record(self, record_id):
        rid = str(record_id)
        for r in reversed(self.data.get("submissions") or []):
            if str(r.get("record_id")) == rid:
                return r
        return None

    def clear(self):
        self.data = {"version": 1, "updated_at": _now_iso(),
                     "dryruns": [], "submissions": []}
        return self._flush()

    def touch_ts(self):
        self.data["updated_at"] = _now_iso()
        return time.time()
