# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""零依赖 MITM 调试代理 —— 抓小程序 v3 明文（school_id / uid / token）

不需要 mitmproxy、不需要 pycryptodome：CA 用 openssl CLI 现签，TLS 用标准库 ssl 做中间人，
body 里的 `data=<AES>` 用本仓库的算法现场解密并打印。

用法：
    python 工具/mitm_debug_proxy.py --init      # 首次：生成 CA 并装进「当前用户→受信任根」
    python 工具/mitm_debug_proxy.py             # 起代理（默认 127.0.0.1:8081）
    # 另开一个窗口：把系统代理指到 127.0.0.1:8081，然后打开小程序

抓到的东西：
    - 控制台实时打印 method / host / path / 解密后的关键字段
    - 同时追加写 _private/capture_log.jsonl（明文，自己看，别外传）

安全边界：只监听 127.0.0.1；只打印不修改请求；不转发到任何第三方。
"""
import argparse
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
from lepao.crypto import decrypt_data  # noqa: E402

CA_DIR = os.path.join(REPO, "_private", "mitm_ca")
LEAF_DIR = os.path.join(CA_DIR, "leaf")
CA_KEY = os.path.join(CA_DIR, "ca.key")
CA_CRT = os.path.join(CA_DIR, "ca.crt")
CA_PEM = os.path.join(CA_DIR, "ca.pem")
LOG = os.path.join(REPO, "_private", "capture_log.jsonl")
OPENSSL = "openssl"

KEYS = ("school_id", "uid", "token", "student_num", "card_id", "term_id",
        "course_id", "class_id", "nonce", "timestamp")


# ---------------------------------------------------------------- CA
def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}… 失败: {p.stderr[:200]}")
    return p.stdout


def ensure_ca():
    os.makedirs(CA_DIR, exist_ok=True)
    os.makedirs(LEAF_DIR, exist_ok=True)
    if not (os.path.isfile(CA_KEY) and os.path.isfile(CA_CRT)):
        print("[ca] 生成根证书 …")
        _run([OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
              "-keyout", CA_KEY, "-out", CA_CRT, "-days", "3650",
              "-subj", "/CN=lepao-debug-ca/O=local research"])
    if not os.path.isfile(CA_PEM):
        _run([OPENSSL, "x509", "-in", CA_CRT, "-out", CA_PEM])
    return CA_CRT


def install_ca():
    ensure_ca()
    cmd = ["certutil", "-addstore", "-user", "Root", CA_CRT]
    p = subprocess.run(cmd, capture_output=True, text=True)
    ok = p.returncode == 0
    print(f"[ca] 安装到当前用户受信任根: {'成功' if ok else '失败'}")
    if not ok:
        print(p.stdout[-400:], p.stderr[-400:])
    else:
        print("[ca] 用毕可删除：certmgr.msc → 受信任的根证书颁发机构 → lepao-debug-ca")
    return ok


_leaf_cache = {}


def leaf_cert(host):
    """按域名现签叶证书（缓存），SAN 必须包含域名，否则浏览器/微信会拒。"""
    if host in _leaf_cache:
        return _leaf_cache[host]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", host)
    key = os.path.join(LEAF_DIR, safe + ".key")
    crt = os.path.join(LEAF_DIR, safe + ".crt")
    csr = os.path.join(LEAF_DIR, safe + ".csr")
    ext = os.path.join(LEAF_DIR, safe + ".ext")
    if not (os.path.isfile(key) and os.path.isfile(crt)):
        with open(ext, "w") as f:
            f.write(f"subjectAltName=DNS:{host}\nbasicConstraints=CA:FALSE\n")
        _run([OPENSSL, "req", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
              "-out", csr, "-subj", f"/CN={host}"])
        _run([OPENSSL, "x509", "-req", "-in", csr, "-CA", CA_CRT, "-CAkey", CA_KEY,
              "-CAcreateserial", "-out", crt, "-days", "365", "-extfile", ext])
    _leaf_cache[host] = (crt, key)
    return crt, key


# ---------------------------------------------------------------- 工具
def parse_sni(data: bytes):
    try:
        if len(data) < 6 or data[0] != 0x16:
            return None
        p = 5 + 4 + 2 + 32
        p += 1 + data[p]
        p += 2 + struct.unpack("!H", data[p:p + 2])[0]
        p += 1 + data[p]
        total = struct.unpack("!H", data[p:p + 2])[0]
        p += 2
        end = p + total
        while p + 4 <= end:
            etype, elen = struct.unpack("!HH", data[p:p + 4])
            p += 4
            if etype == 0:
                q = p + 2
                nlen = struct.unpack("!H", data[q + 1:q + 3])[0]
                return data[q + 3:q + 3 + nlen].decode("idna", "replace")
            p += elen
    except Exception:
        return None
    return None


def recv_head(sock, limit=65536):
    """读到 \r\n\r\n 为止，返回 (头部, 多余字节)。多余字节必须保留给 TLS 层。"""
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    return head, rest


class TLSStream:
    """把 SSLObject(MemoryBIO) 包装成 socket 风格的 recv/sendall。

    必须用 MemoryBIO：CONNECT 之后我们已经从 socket 预读了 ClientHello，
    直接用 wrap_socket 会让已读字节丢失 → 双方互等 → 握手超时。
    """

    def __init__(self, sock, ctx, leftover=b""):
        self.sock = sock
        self.inc = ssl.MemoryBIO()
        self.out = ssl.MemoryBIO()
        self.obj = ctx.wrap_bio(self.inc, self.out, server_side=True)
        if leftover:
            self.inc.write(leftover)

    def _flush(self):
        data = self.out.read()
        if data:
            self.sock.sendall(data)

    def handshake(self):
        while True:
            try:
                self.obj.do_handshake()
                self._flush()
                return
            except ssl.SSLWantReadError:
                self._flush()
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionError("对端在握手期关闭")
                self.inc.write(data)
            except ssl.SSLWantWriteError:
                self._flush()

    def recv(self, n):
        while True:
            try:
                return self.obj.read(n)
            except ssl.SSLWantReadError:
                data = self.sock.recv(65536)
                if not data:
                    return b""
                self.inc.write(data)
            except ssl.SSLWantWriteError:
                self._flush()

    def sendall(self, data):
        view = memoryview(data)
        while view:
            try:
                n = self.obj.write(view)
                view = view[n:]
            except ssl.SSLWantWriteError:
                self._flush()
            self._flush()

    def close(self):
        try:
            self._flush()
            self.sock.close()
        except Exception:
            pass


def log_json(obj):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except OSError:
        pass


def save_upload(host, path, head_b, body):
    """把 multipart 上传（wx.uploadFile，轨迹文件）的原文存下来。"""
    low = head_b.lower()
    if b"multipart/form-data" not in low:
        return
    ts = time.strftime("%H%M%S")
    out = os.path.join(REPO, "_private", f"upload_{ts}.bin")
    try:
        with open(out, "wb") as f:
            f.write(body)
        print(f"  ★ 抓到文件上传 {host}{path}  {len(body)} B → {out}")
    except OSError as e:
        print(f"  !! 保存上传体失败: {e}")


def inspect_body(host, path, body_bytes):
    """解 v3 body 并打印关键字段；返回明文 dict 或 None。"""
    text = body_bytes.decode("utf-8", "replace")
    m = re.search(r"data=([A-Za-z0-9+/=%]+)", text)
    if not m:
        return None
    raw = m.group(1)
    import urllib.parse
    raw = urllib.parse.unquote(raw).replace(" ", "+")
    try:
        obj = json.loads(decrypt_data(raw))
    except Exception:
        return None
    brief = {k: obj.get(k) for k in KEYS if k in obj}
    print(f"\n  ★ v3 明文  {host}{path}")
    for k, v in brief.items():
        if k == "token" and isinstance(v, str) and len(v) > 12:
            v = v[:8] + "…" + v[-4:]
        print(f"      {k:12s} = {v}")
    others = [k for k in obj if k not in KEYS]
    if others:
        print(f"      其他字段: {', '.join(others[:10])}")
    log_json({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "host": host, "path": path, "plain": obj})
    return obj


# ---------------------------------------------------------------- MITM
def handle_http(client, head, leftover):
    """明文 HTTP（非 CONNECT）转发 —— 不做 MITM（本来就是明文），只旁路解析 v3 body。

    上一版这里直接回 400，导致只要系统代理开着，`http://` 站点全部打不开。
    """
    lines = head.split(b"\r\n")
    host_hdr = ""
    for ln in lines[1:]:
        if ln.lower().startswith(b"host:"):
            host_hdr = ln.split(b":", 1)[1].strip().decode("latin1")
            break
    if not host_hdr:
        client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        client.close()
        return
    host, _, port_s = host_hdr.partition(":")
    port = int(port_s or 80)
    try:
        up = socket.create_connection((host, port), timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"  !! HTTP 上游不通 {host}:{port}: {type(e).__name__}")
        client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        client.close()
        return

    # 把已读到的头部 + 多余字节原样送给上游
    up.sendall(head + b"\r\n\r\n" + leftover)

    def up_to_client():
        try:
            while True:
                d = up.recv(65536)
                if not d:
                    break
                client.sendall(d)
        except Exception:
            pass
        finally:
            try:
                up.close()
            except Exception:
                pass

    threading.Thread(target=up_to_client, daemon=True).start()

    buf = leftover
    try:
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                idx = buf.find(b"\r\n\r\n")
                if idx < 0:
                    break
                head_b = buf[:idx + 4]
                m = re.search(rb"content-length:\s*(\d+)", head_b, re.I)
                need = int(m.group(1)) if m else 0
                total = idx + 4 + need
                if len(buf) < total:
                    break
                req = buf[:total]
                buf = buf[total:]
                try:
                    path = req.split(b"\r\n", 1)[0].decode("latin1").split(" ")[1]
                except Exception:
                    path = "/"
                inspect_body(host, path, req[idx + 4:total])
                save_upload(host, path, head_b, req[idx + 4:total])
                up.sendall(req)
    except Exception:
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass


def handle(client, addr):
    try:
        head, leftover = recv_head(client, 16384)
        if not head:
            client.close()
            return
        first = head.split(b"\r\n", 1)[0].decode("latin1")
        parts = first.split()
        if len(parts) < 2:
            client.close()
            return
        method, target = parts[0].upper(), parts[1]
        if method != "CONNECT":
            # 明文 HTTP：直接转发 + 旁路解析（不再返回 400）
            handle_http(client, head, leftover)
            return

        host, _, port_s = target.partition(":")
        port = int(port_s or 443)
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")

        # 预读的 leftover 里可能已有 ClientHello；没有就再读一点拿 SNI
        peek = leftover
        if not parse_sni(peek):
            try:
                peek += client.recv(16384)
            except Exception:
                pass
        sni = parse_sni(peek) or host
        crt, key = leaf_cert(sni)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        try:
            tls = TLSStream(client, ctx, peek)
            tls.handshake()
        except Exception as e:  # 客户端不信任我们的 CA
            print(f"  !! {sni} 握手失败（CA 未受信？）: {type(e).__name__}: {e}")
            client.close()
            return
        print(f"[TLS] {sni}:{port} 证书 CN={sni}")

        try:
            up_raw = socket.create_connection((host, port), timeout=20)
            up_ctx = ssl.create_default_context()
            up = up_ctx.wrap_socket(up_raw, server_hostname=sni)
        except Exception as e:  # noqa: BLE001
            print(f"  !! 连不上上游 {host}:{port}: {type(e).__name__}: {e}")
            tls.close()
            return

        def up_to_client():
            try:
                while True:
                    d = up.recv(65536)
                    if not d:
                        break
                    tls.sendall(d)
            except Exception:
                pass

        threading.Thread(target=up_to_client, daemon=True).start()

        buf = b""
        while True:
            try:
                chunk = tls.recv(65536)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while True:
                idx = buf.find(b"\r\n\r\n")
                if idx < 0:
                    break
                head_b = buf[:idx + 4]
                m = re.search(rb"content-length:\s*(\d+)", head_b, re.I)
                need = int(m.group(1)) if m else 0
                total = idx + 4 + need
                if len(buf) < total:
                    break
                req = buf[:total]
                buf = buf[total:]
                body = req[idx + 4:total]
                try:
                    path = req.split(b"\r\n", 1)[0].decode("latin1").split(" ")[1]
                except Exception:
                    path = "/"
                inspect_body(sni, path, body)
                save_upload(sni, path, head_b, body)
                try:
                    up.sendall(req)
                except Exception:
                    break
    except Exception as e:  # noqa: BLE001
        print(f"  !! 处理连接异常: {type(e).__name__}: {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass


def serve(host="127.0.0.1", port=8081):
    ensure_ca()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(128)
    print(f"[mitm] 监听 {host}:{port}  CA={CA_CRT}")
    print("[mitm] 把系统代理指到这个地址，然后打开小程序（建议先开 TUN/强制代理，防止微信绕过）")
    print("[mitm] Ctrl+C 退出；还记得把系统代理关掉")
    while True:
        try:
            c, a = srv.accept()
        except KeyboardInterrupt:
            break
        threading.Thread(target=handle, args=(c, a), daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="生成并安装 CA")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    if a.init:
        install_ca()
        return
    serve(a.host, a.port)


if __name__ == "__main__":
    main()
