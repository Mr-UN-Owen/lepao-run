# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
"""webapp.lplib —— 乐跑 v3 客户端（网页版用，只依赖 lepao.crypto）

与 lepao.v3api 的区别：这里不做 config/成员表那套，直接以「host + school_id + uid + token」
为会话参数，适合网页里一个用户一个会话的形态。
"""
import base64
import datetime
import hashlib
import hmac
import http.client
import json
import random
import socket
import ssl
import string
import threading
import time
import urllib.parse
import urllib.request

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lepao.crypto import encrypt_data, decrypt_data, sign_md5, random6  # noqa: E402

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

DNS_TIMEOUT = 8.0          # getaddrinfo 没有超时接口，超过这个秒数一律判失败
DNS_TTL = 300.0
_DNS_CACHE = {}
_DNS_LOCK = threading.Lock()


def resolve_host(host, timeout=DNS_TIMEOUT, cache=True):
    """带超时的 DNS 解析。

    为什么必须自己包一层：socket.getaddrinfo 不受任何 timeout 约束。
    校内 DNS 抽风时它会**永久阻塞**，urllib / http.client 的 timeout 完全不生效，
    表现就是网页上「一直提交中」，而且后端连异常都抛不出来。
    返回 (ip, None) 或 (None, 人话原因)。
    """
    now = time.time()
    if cache:
        with _DNS_LOCK:
            hit = _DNS_CACHE.get(host)
        if hit and now - hit[1] < DNS_TTL:
            return hit[0], None

    box = {}

    def work():
        try:
            info = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            box["ip"] = info[0][4][0]
        except Exception as e:  # noqa: BLE001
            box["err"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=work, daemon=True)
    t0 = time.time()
    t.start()
    t.join(timeout)
    if "ip" in box:
        if cache:
            with _DNS_LOCK:
                _DNS_CACHE[host] = (box["ip"], now)
        return box["ip"], None
    if "err" in box:
        return None, f"DNS 解析失败（{box['err']}）"
    return None, (f"DNS 解析 {host} 超过 {timeout:.0f}s 没返回"
                  f"（校内 DNS / 认证网关异常，实测 {time.time() - t0:.1f}s）")


def tcp_probe(host, port=443, timeout=6.0):
    """连通性探测：返回 (ok, dns_s, tcp_s, 说明)。"""
    ip, err = resolve_host(host)
    if err:
        return False, None, None, err
    t0 = time.time()
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close()
        return True, None, time.time() - t0, f"{ip}:{port} 可达"
    except Exception as e:  # noqa: BLE001
        return False, None, time.time() - t0, f"{ip}:{port} 连不上（{type(e).__name__}: {e}）"

UA = ("Mozilla/5.0 (Linux; Android 10; Redmi Note 7 Build/QKQ1.190910.002; wv) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 "
      "Mobile Safari/537.36 XWEB/1420283 MMWEBID/2837 MicroMessenger/8.0.77.3160 "
      "WeChat/arm64 MiniProgramEnv/android")
DEFAULT_APPID = "wxb2043232183dac7f"


class V3Error(Exception):
    def __init__(self, status, info=""):
        super().__init__(f"[{status}] {info}")
        self.status = status
        self.info = info


class Session:
    """一个登录会话。host/school_id/uid/token 是全部状态。"""

    def __init__(self, host="api3.lptiyu.com", school_id=816, uid=0, token="",
                 student_num="", card_id="", appid=DEFAULT_APPID, proxy=""):
        self.host = host
        self.school_id = int(school_id or 0)
        self.uid = str(uid or "")
        self.token = token
        self.student_num = student_num or ""
        self.card_id = card_id or student_num or ""
        self.appid = appid
        self.proxy = proxy
        self.refresh_token = ""
        self.term_id = 0
        self.school_name = ""
        self.term_name = ""
        self.last_before_run = None

    # ---------------------------------------------------------------- 底层
    def call(self, path, biz=None, flag=False, timeout=20):
        ip, err = resolve_host(self.host)
        if err:
            raise V3Error(-3, err)
        p = {
            "uid": self.uid, "token": self.token, "school_id": self.school_id,
            "term_id": self.term_id, "course_id": 0, "class_id": 0,
            "student_num": self.student_num, "card_id": self.card_id,
        }
        if biz:
            p.update(biz)
        p.update({"timestamp": int(time.time()), "version": 1,
                  "nonce": random6(), "ostype": 5})
        p["sign"] = sign_md5(p)
        body = "ostype=5&data=" + urllib.parse.quote(encrypt_data(json.dumps(p, ensure_ascii=False)))
        url = f"https://{self.host}{path}"
        # 显式给 ProxyHandler：proxy 为空时就是"不走任何代理"。
        # 否则 build_opener 会读系统代理——抓包期间系统代理指着 MITM，验证请求会被带偏。
        if self.proxy:
            handlers = [urllib.request.ProxyHandler({"https": self.proxy, "http": self.proxy})]
        else:
            handlers = [urllib.request.ProxyHandler({})]
        opener = urllib.request.build_opener(*handlers, urllib.request.HTTPSHandler(context=CTX))
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "charset": "utf-8",
            "Referer": f"https://servicewechat.com/{self.appid}/13/page-frame.html",
            "User-Agent": UA,
        }
        if flag:
            headers["flag"] = "[object Boolean]"
        req = urllib.request.Request(url, data=body.encode(), headers=headers)
        try:
            with opener.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            raise V3Error(-1, f"{type(e).__name__}: {e}") from e
        try:
            j = json.loads(raw)
        except Exception:
            raise V3Error(-2, f"响应不是 JSON: {raw[:120]}")
        if j.get("status") == 1 and isinstance(j.get("data"), str) and len(j["data"]) > 8:
            try:
                j["data"] = json.loads(decrypt_data(j["data"]))
            except Exception:
                pass
        return j

    def ok(self, path, biz=None, flag=False):
        j = self.call(path, biz, flag)
        if j.get("status") != 1:
            raise V3Error(j.get("status"), j.get("info") or "")
        return j.get("data")

    # ---------------------------------------------------------------- 业务
    def get_terms(self):
        data = self.ok("/v3/api.php/WpRun/getTermList")
        terms = data if isinstance(data, list) else []
        for t in terms:
            if str(t.get("status")) == "1":
                self.term_id = int(t.get("term_id") or 0)
                self.term_name = t.get("term_name") or ""
                break
        if not self.term_id and terms:
            self.term_id = int(terms[0].get("term_id") or 0)
            self.term_name = terms[0].get("term_name") or ""
        return terms

    def before_run(self):
        data = self.ok("/v3/api.php/Run2/beforeRunV260")
        if isinstance(data, dict):
            self.last_before_run = data
            self.school_name = data.get("school_name") or self.school_name
            if data.get("term_id"):
                self.term_id = int(data.get("term_id"))
        return data

    def records(self, page=1, limit=20):
        return self.ok("/v3/api.php/WpRun/getTermRunRecord",
                       {"term_id": self.term_id, "page": page, "limit": limit})

    def server_ts(self):
        data = self.ok("/v3/api.php/Run/getTimestampV278")
        if isinstance(data, dict):
            for k in ("timestamp", "time", "now"):
                if k in data:
                    try:
                        return int(float(data[k]))
                    except (TypeError, ValueError):
                        pass
        return int(time.time())

    def stop_free_run(self, biz):
        j = self.call("/v3/api.php/Run/stopFreeRunV220", biz, flag=True)
        return j

    def stop_run_v278(self, biz):
        """跑区模式（计入成绩、关联跑区）。biz 里必须带 term_id。"""
        j = self.call("/v3/api.php/Run/stopRunV278", biz, flag=True)
        return j

    # ---------------------------------------------------------------- OSS
    def get_oss_sts(self):
        """取 STS：含 AccessKeyId/Secret/SecurityToken/bucket/callback。"""
        return self.ok("/v3/api.php/WpIndex/getOssSts")

    def upload_track(self, text, sts, record_file, now_ms=None, timeout=40, use_callback=True):
        """把轨迹文本上传到 OSS（= wx.uploadFile 的形态复刻）。

        text: base64(AES(json(track))) 字符串 —— 与真机一致，服务端解密后才是 JSON。
        返回 (http_status, body)
        """
        bucket = (sts or {}).get("bucket") or "lptiyu-data"
        host = f"{bucket}.oss-cn-hangzhou.aliyuncs.com"
        key = "Public/Upload/file/" + record_file
        now_ms = int(now_ms or time.time() * 1000)
        exp = datetime.datetime.fromtimestamp((now_ms + 3600000) / 1000.0,
                                              datetime.timezone.utc)
        exp_s = exp.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now_ms + 3600000) % 1000:03d}Z"
        policy_src = ('{"expiration":"%s","conditions":[["content-length-range",0,1073741824]]}'
                      % exp_s)
        policy = base64.b64encode(policy_src.encode()).decode()
        signature = base64.b64encode(
            hmac.new(str(sts["AccessKeySecret"]).encode(), policy.encode(),
                     hashlib.sha1).digest()).decode()
        boundary = "----MultipartBoundary--" + "".join(
            random.choices(string.ascii_letters + string.digits, k=27))

        def field(name, value):
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                    f"{value}\r\n").encode()

        parts = [
            field("OSSAccessKeyId", sts["AccessKeyId"]),
            field("key", key),
            field("policy", policy),
            field("signature", signature),
            field("x-oss-security-token", sts["SecurityToken"]),
        ]
        # STS 里的 callbackUrl 常写成 api2（平台默认域），但本校 API 在 self.host。
        # 原样传会让 OSS 回调到错误域 → CallbackFailed（203）。这里把域改过来再编码。
        cb = sts.get("callback")
        if cb and use_callback:
            try:
                raw_cb = base64.b64decode(cb).decode("utf-8")
                host_key = f'"callbackUrl":"https:\\/\\/{self.host}'
                if "api2.lptiyu.com" in raw_cb and self.host != "api2.lptiyu.com":
                    raw_cb = raw_cb.replace("api2.lptiyu.com", self.host)
                    cb = base64.b64encode(raw_cb.encode()).decode()
            except Exception:
                pass
            parts.append(field("callback", cb))
        local_fname = f"{now_ms - random.randint(20, 90)}.txt"
        parts.append(
            (f"--{boundary}\r\n"
             f"Content-Disposition: form-data; name=\"file\"; filename=\"{local_fname}\"\r\n"
             f"Content-Type: text/plain\r\n\r\n").encode()
            + str(text).encode() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        ip, err = resolve_host(host)
        if err:
            raise V3Error(-3, err)

        last = None
        for attempt in (1, 2):
            conn = http.client.HTTPSConnection(host, timeout=timeout)
            try:
                conn.default_headers.clear()
            except Exception:
                pass
            try:
                conn.putrequest("POST", "/", skip_accept_encoding=True)
                conn.putheader("Connection", "keep-alive")
                conn.putheader("Content-Length", str(len(body)))
                conn.putheader("charset", "utf-8")
                conn.putheader("content-type", f"multipart/form-data; boundary={boundary}")
                conn.putheader("Referer", f"https://servicewechat.com/{self.appid}/13/page-frame.html")
                conn.putheader("User-Agent", UA)
                conn.putheader("Accept-Encoding", "gzip, deflate, br")
                conn.endheaders(body)
                resp = conn.getresponse()
                status = resp.status
                try:
                    rbody = resp.read().decode("utf-8", "replace")
                except Exception:
                    rbody = ""
                conn.close()
                return status, rbody
            except Exception as e:  # noqa: BLE001
                last = e
                try:
                    conn.close()
                except Exception:
                    pass
                if attempt == 1:
                    # 校园网/宿舍网第一次上传经常被掐，隔 1 秒重来一次往往就过
                    time.sleep(1.0)
        raise V3Error(-1, f"OSS 上传失败（已重试 2 次）：{type(last).__name__}: {last}")

    def record_detail(self, record_id):
        return self.call("/v3/api.php/Run/recordDetailV270", {"record_id": record_id})

    # ---------------------------------------------------------------- 续期
    def refresh(self, refresh_token):
        """Login/RefreshToken 续期。成功 → (access_token, refresh_token, expire) 并就地换 token。

        抓一次 loginByCode 拿到的 refresh_token 最长可用 ~30 天，之后不必再开小程序。
        """
        if not refresh_token:
            raise V3Error(0, "无 refresh_token")
        j = self.call("/v3/api.php/Login/RefreshToken", {"refresh_token": refresh_token})
        pools = [j]
        for key in ("data", "token_data", "auth_data"):
            v = j.get(key)
            if isinstance(v, dict):
                pools.append(v)
                for k2 in ("token_data", "auth_data"):
                    if isinstance(v.get(k2), dict):
                        pools.append(v[k2])
        at = rt = ""
        exp = 0
        for p in pools:
            at = at or str(p.get("access_token") or p.get("token") or "")
            rt = rt or str(p.get("refresh_token") or "")
            try:
                exp = exp or int(p.get("refresh_expire") or 0)
            except (TypeError, ValueError):
                pass
        if not at:
            raise V3Error(j.get("status"), j.get("info") or "refresh 未返回 access_token")
        self.token = at
        return at, rt or refresh_token, exp

    # ---------------------------------------------------------------- 摘要
    def profile(self):
        br = self.last_before_run or self.before_run() or {}
        rr = br.get("run_line_info") or {}
        zones = []
        for z in br.get("run_zone_list") or []:
            zones.append({
                "id": str(z.get("id")),
                "name": z.get("name"),
                "is_default": bool(int(z.get("is_default") or 0)),
                "time": z.get("time") or [],
            })
        points = []
        for p in rr.get("point_list") or []:
            jw = str(p.get("jingwei") or "")
            lat = lng = None
            if "," in jw:
                try:
                    lat, lng = float(jw.split(",")[0]), float(jw.split(",")[1])
                except ValueError:
                    pass
            points.append({
                "id": str(p.get("id")), "name": p.get("address") or "",
                "lat": lat, "lng": lng,
            })
        return {
            "host": self.host,
            "school_id": self.school_id,
            "school_name": self.school_name or br.get("school_name") or "",
            "uid": self.uid,
            "student_num": self.student_num,
            "term_id": self.term_id,
            "term_name": self.term_name or "",
            "term_date": br.get("term_date") or "",
            "total_distance": br.get("total_distance"),
            "total_num": br.get("total_num"),
            "total_log_num": br.get("total_log_num"),
            "run_zone_id": br.get("run_zone_id"),
            "run_zone_name": br.get("run_zone_name"),
            "run_start_time": br.get("run_start_time"),
            "run_end_time": br.get("run_end_time"),
            "rule_url": br.get("ruleUrl") or "",
            "auth_status": br.get("authStatus"),
            "tips": br.get("tips") or "",
            # 服务端权威计数：run_num = 今日已跑【有效】次数
            "run_num": int(br.get("run_num") or 0),
            "checks": {
                "geetest": br.get("is_check_geetest"),
                "deepkonw": br.get("is_check_deepkonw"),
                "geedevice": br.get("is_check_geedevice"),
                "device": br.get("is_check_device"),
                "time": br.get("is_check_time"),
                "face": br.get("is_register_face"),
                "capture_zone": br.get("is_capture_zone"),
            },
            "point_rule": {
                "point_num": rr.get("point_num"),
                "min_distance": rr.get("point_min_distance"),
                "max_distance1": rr.get("point_max_distance1"),
                "max_distance2": rr.get("point_max_distance2"),
                "log_max_distance": rr.get("log_max_distance"),
                "random_distance": br.get("random_distance"),
            },
            "zones": zones,
            "points": points,
        }
