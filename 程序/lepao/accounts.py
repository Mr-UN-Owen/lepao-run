# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.accounts —— 成员注册表（config v2）

单一职责: 成员表的读写、选择器解析、身份归位与策略合并。
- 键 = 学号（首次登记只需姓名+学号，uid 由抓号回填）。
- v1 平铺配置(account/auth)首次读取自动迁移为 v2 accounts 表。
- 白名单语义: 注册表里的 uid/学号/卡号即 mitm 抓号插件允许落盘的键。
"""
import copy
import json
import os
import sys
import tempfile

DEFAULT_ENVIRONMENT = {
    "api_host": "api2.lptiyu.com",
    "api_proxy": "127.0.0.1:8081",
    "h5_base": "/bdlp_h5_fitness_test/public/index.php",
    "oss_host": "lptiyu-data.oss-cn-hangzhou.aliyuncs.com",
    "app_key": "wxb2043232183dac7f",
}

DEFAULT_POLICY = {
    "max_per_day": 1,
    "style": "template",
    "dist_lo": 2.03,
    "dist_hi": 2.35,
    "pace_lo": 185,
    "pace_hi": 560,
}

DEFAULT_RUNTIME = {"spacing_min": 5, "spacing_max": 10}

DEFAULT_AUTH = {
    "token": "",
    "issued_at": "",
    "source": "",
    "consumed_at": "",
    "refresh_token": "",
    "refresh_expire": 0,
    "ttl_class": "single-active-session",
    "probe_evidence": [],
}


class AccountError(Exception):
    """成员表相关错误（未登记 / 选择器歧义 / 缺 uid 等）。"""


def _now_iso():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _atomic_write_json(path, data, mode=0o600):
    """原子写 JSON：同目录临时文件 + os.replace，避免中断留下半截配置。"""
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_cfg_", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class AccountRegistry:
    """config v2 成员注册表。所有写操作即时落盘（含 token 这类短命字段）。"""

    def __init__(self, config_path=None, create=False, verbose=True):
        self.config_path = os.path.abspath(
            config_path or os.path.join(os.getcwd(), "config.json"))
        self.verbose = verbose
        self.config = {}
        if os.path.isfile(self.config_path):
            self._load()
        elif create:
            self.config = self._blank()
            self.persist()
            if self.verbose:
                print(f"[accounts] 已创建空配置 {self.config_path}")
        else:
            raise AccountError(
                f"未找到配置文件 {self.config_path}\n"
                f"→ 复制 config.sample.json 为 config.json, 或 `cli.py account add <名字> <学号>` 自动创建")

    # ------------------------------------------------------------ 读写
    def _blank(self):
        return {
            "version": 2,
            "active": "",
            "accounts": {},
            "environment": copy.deepcopy(DEFAULT_ENVIRONMENT),
            "policy": copy.deepcopy(DEFAULT_POLICY),
            "runtime": copy.deepcopy(DEFAULT_RUNTIME),
        }

    def _load(self):
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise AccountError(f"配置不是合法 JSON: {self.config_path} ({e})")
        if not isinstance(data, dict):
            raise AccountError(f"配置结构异常(应为对象): {self.config_path}")
        self.config = data
        if self._migrate_v1():
            self.persist()

    def _migrate_v1(self):
        """v1 平铺 -> v2 accounts。返回是否发生迁移。"""
        if int(self.config.get("version") or 1) >= 2 and isinstance(
                self.config.get("accounts"), dict):
            self.config.setdefault("environment", copy.deepcopy(DEFAULT_ENVIRONMENT))
            self.config.setdefault("policy", copy.deepcopy(DEFAULT_POLICY))
            self.config.setdefault("runtime", copy.deepcopy(DEFAULT_RUNTIME))
            return False
        old_acc = self.config.get("account") or {}
        old_auth = self.config.get("auth") or {}
        num = str(old_acc.get("student_num") or old_acc.get("card_id") or "").strip()
        accounts = {}
        if num:
            prof = {
                "uid": old_acc.get("uid") or 0,
                "school_id": old_acc.get("school_id") or 0,
                "student_num": num,
                "card_id": str(old_acc.get("card_id") or num),
                "name": old_acc.get("name") or num,
                "alias": old_acc.get("alias") or "",
                "enabled": True,
                "remark": "由 v1 配置自动迁移",
                "policy": {},
                "auth": dict(DEFAULT_AUTH, **(old_auth or {})),
            }
            accounts[num] = prof
        self.config = {
            "version": 2,
            "active": num,
            "accounts": accounts,
            "environment": dict(copy.deepcopy(DEFAULT_ENVIRONMENT),
                                **(self.config.get("environment") or {})),
            "policy": dict(copy.deepcopy(DEFAULT_POLICY),
                           **(self.config.get("policy") or {})),
            "runtime": dict(copy.deepcopy(DEFAULT_RUNTIME),
                            **(self.config.get("runtime") or {})),
        }
        self.config.pop("account", None)
        self.config.pop("auth", None)
        if self.verbose:
            print("[accounts] 检测到 v1 配置 → 已自动迁移为 v2 accounts 表")
        return True

    def persist(self):
        _atomic_write_json(self.config_path, self.config)
        return self.config_path

    # ------------------------------------------------------------ 访问器
    @property
    def accounts(self):
        return self.config.setdefault("accounts", {})

    @property
    def environment(self):
        return self.config.setdefault("environment", copy.deepcopy(DEFAULT_ENVIRONMENT))

    @property
    def runtime(self):
        return self.config.setdefault("runtime", copy.deepcopy(DEFAULT_RUNTIME))

    @property
    def active(self):
        return str(self.config.get("active") or "")

    @active.setter
    def active(self, key):
        self.config["active"] = str(key or "")

    def keys(self):
        return [k for k, v in self.accounts.items() if isinstance(v, dict)]

    def __contains__(self, key):
        return str(key) in self.accounts

    def __len__(self):
        return len(self.keys())

    def acc(self, key):
        k = str(key)
        prof = self.accounts.get(k)
        if not isinstance(prof, dict):
            raise AccountError(f"成员未登记: {k}（先 `account add` 登记，登记=抓号白名单）")
        prof.setdefault("auth", dict(DEFAULT_AUTH))
        if not isinstance(prof["auth"], dict):
            prof["auth"] = dict(DEFAULT_AUTH)
        for f, dflt in DEFAULT_AUTH.items():
            prof["auth"].setdefault(f, copy.deepcopy(dflt))
        return prof

    def add(self, name, student_num, alias=None, school_id=None):
        """登记成员（姓名 + 学号）。学号为键；已存在则返回既有键。"""
        num = str(student_num).strip()
        if not num:
            raise AccountError("学号不能为空")
        if num in self.accounts:
            if self.verbose:
                print(f"[accounts] 成员已存在: {num}（未改动）")
            return num
        self.accounts[num] = {
            "uid": 0,
            "school_id": int(school_id or 0),
            "student_num": num,
            "card_id": num,
            "name": str(name or num),
            "alias": str(alias or name or num),
            "enabled": True,
            "remark": f"登记于 {_now_iso()}",
            "policy": {},
            "auth": copy.deepcopy(DEFAULT_AUTH),
        }
        if not self.active:
            self.active = num
        self.persist()
        if self.verbose:
            print(f"[accounts] 已登记成员 {self.accounts[num]['name']} / {num} "
                  f"(uid 待首次抓号回填)")
        return num

    def remove(self, sel):
        key = self.resolve(sel)
        self.accounts.pop(key, None)
        if self.active == key:
            self.active = self.keys()[0] if self.keys() else ""
        self.persist()
        if self.verbose:
            print(f"[accounts] 已移除成员 {key}")
        return key

    # ------------------------------------------------------------ 选择器
    def resolve(self, sel=None):
        """选择器: None/空=active；支持 学号 | 别名 | 姓名 | uid。"""
        if sel is None or str(sel).strip() == "":
            if self.active:
                if self.active not in self.accounts:
                    raise AccountError(f"active 指向未登记成员: {self.active}")
                return self.active
            ks = self.keys()
            if len(ks) == 1:
                return ks[0]
            if not ks:
                raise AccountError("成员表为空: 先 `account add <名字> <学号>`")
            raise AccountError(f"未指定成员且 active 为空（现有成员: {', '.join(ks)}）")
        s = str(sel).strip()
        if s in self.accounts:
            return s
        hits = []
        for k, prof in self.accounts.items():
            if not isinstance(prof, dict):
                continue
            for field in ("alias", "name"):
                if str(prof.get(field) or "").strip() == s:
                    hits.append(k)
                    break
            else:
                if str(prof.get("uid") or "") == s:
                    hits.append(k)
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise AccountError(f"选择器 {s!r} 命中多个成员: {', '.join(hits)}（请改用学号）")
        raise AccountError(f"找不到成员: {s!r}（可用: {', '.join(self.keys()) or '空'}）")

    # ------------------------------------------------------------ 身份归位
    def key_of_cred(self, cred):
        """按 uid / 学号 / 卡号 三键把一份凭证归位到成员键；未登记返回 None。

        mitm 抓号与 capture 同步都用它: 白名单之外的身份一律不落盘/不入槽。
        """
        if not isinstance(cred, dict):
            return None
        uid = str(cred.get("uid") or "").strip()
        num = str(cred.get("student_num") or "").strip()
        card = str(cred.get("card_id") or "").strip()
        if uid and uid != "0":
            for k, prof in self.accounts.items():
                if str(prof.get("uid") or "") == uid and uid:
                    return k
        for cand in (num, card):
            if cand and cand in self.accounts:
                return cand
        return None

    def fill_identity(self, key, uid=None, school_id=None, student_num=None,
                      card_id=None, name=None):
        """首次抓号后回填身份字段（只补空值，不覆盖已填）。"""
        prof = self.acc(key)
        changed = False
        if uid and not prof.get("uid"):
            prof["uid"] = int(uid)
            changed = True
        if school_id and not prof.get("school_id"):
            prof["school_id"] = int(school_id)
            changed = True
        if student_num and not str(prof.get("student_num") or ""):
            prof["student_num"] = str(student_num)
            changed = True
        if card_id and not str(prof.get("card_id") or ""):
            prof["card_id"] = str(card_id)
            changed = True
        if name and (not prof.get("name") or prof.get("name") == key):
            prof["name"] = str(name)
            changed = True
        if changed:
            self.persist()
            if self.verbose:
                print(f"[accounts] 身份已回填 [{prof.get('name')}] uid={prof.get('uid')} "
                      f"school={prof.get('school_id')}")
        return prof

    def whitelist(self):
        """抓号白名单: {'uid': {...}, 'student_num': {...}, 'card_id': {...}}"""
        wl = {"uid": set(), "student_num": set(), "card_id": set()}
        for k, prof in self.accounts.items():
            if not isinstance(prof, dict) or not prof.get("enabled", True):
                continue
            if prof.get("uid"):
                wl["uid"].add(str(prof["uid"]))
            for f in ("student_num", "card_id"):
                v = str(prof.get(f) or "").strip()
                if v:
                    wl[f].add(v)
        return wl

    # ------------------------------------------------------------ 策略
    def policy_of(self, key):
        """全局 policy + 成员级覆盖（成员 policy 优先）。"""
        p = dict(DEFAULT_POLICY)
        p.update({k: v for k, v in (self.config.get("policy") or {}).items()
                  if v is not None})
        prof = self.accounts.get(str(key)) or {}
        p.update({k: v for k, v in (prof.get("policy") or {}).items() if v is not None})
        return p

    # ------------------------------------------------------------ 展示
    def describe(self, key):
        prof = self.acc(key)
        a = prof.get("auth") or {}
        state = "已消耗" if a.get("consumed_at") else ("在使用" if a.get("token") else "无 token")
        return (f"[{prof.get('alias') or prof.get('name') or key}] 学号={key} "
                f"uid={prof.get('uid') or '-'} 学校={prof.get('school_id') or '-'} "
                f"token={state}" + (f" 签发={a.get('issued_at')}" if a.get("issued_at") else ""))
