# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""零依赖小程序平台嗅探代理（只看域名 / SNI / 明文 Host，不解密流量）

用途：判断“公大跑者”这类微信小程序到底连的是哪家后端（乐跑 lptiyu？体适能？自建？），
      以及有没有走腾讯的反作弊/风控域名。只记录元数据，不落任何 body、不装根证书。

用法：
  1) python 工具/proxy_sniff.py            # 默认监听 127.0.0.1:18081
  2) Windows 设置 → 网络和 Internet → 代理 → 手动设置代理 127.0.0.1:18081
     （或命令行: netsh winhttp set proxy 127.0.0.1:18081，仅对部分程序生效）
  3) 打开电脑微信 → 进入「公大跑者」小程序 → 点开跑步页 / 开始一次跑步
  4) 回到控制台看输出；日志同时写 _private/sniff.log
  5) 结束后务必关闭系统代理（脚本退出会提示）

注意：本脚本对 TLS 只做透传，小程序功能正常；HTTPS 内容不可见属预期。
"""
import argparse
import asyncio
import datetime as dt
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# 平台指纹：域名片段 -> 平台猜测
PLATFORM_HINTS = [
    ("lptiyu.com", "乐跑 / 数体智慧体育 (lptiyu) —— 与 lepao 协议栈同一后端"),
    ("lerun.", "乐跑 H5 端 (lerun.lptiyu.com)"),
    ("bupt.edu.cn", "高校自建 v3 站点（乐跑白标部署）"),
    ("tiyu.", "体育平台白标域名"),
    ("servicewechat.com", "微信小程序框架（可从中提取 appid）"),
    ("qcloud.com", "腾讯云 COS/OSS 对象存储"),
    ("aliyuncs.com", "阿里云 OSS 对象存储"),
    ("amap.com", "高德地图/定位"),
    ("qq.com/map", "腾讯地图/定位"),
    ("geetest", "极验验证码（风控）"),
    ("captcha", "验证码/风控"),
]


def classify(host: str) -> str:
    h = host.lower()
    for frag, label in PLATFORM_HINTS:
        if frag in h:
            return label
    return ""


def log(line: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    out = f"[{ts}] {line}"
    print(out, flush=True)
    try:
        with open(os.path.join(REPO, "_private", "sniff.log"), "a", encoding="utf-8") as f:
            f.write(out + "\n")
    except OSError:
        pass


def parse_sni(data: bytes):
    """从 TLS ClientHello 里取 SNI。失败返回 None。"""
    try:
        if len(data) < 6 or data[0] != 0x16:
            return None
        # record header 5B; handshake header 4B
        p = 5 + 4
        p += 2 + 32  # version + random
        sid_len = data[p]
        p += 1 + sid_len
        cs_len = struct.unpack("!H", data[p:p + 2])[0]
        p += 2 + cs_len
        cm_len = data[p]
        p += 1 + cm_len
        ext_total = struct.unpack("!H", data[p:p + 2])[0]
        p += 2
        end = p + ext_total
        while p + 4 <= end:
            etype, elen = struct.unpack("!HH", data[p:p + 4])
            p += 4
            if etype == 0x0000:
                # server_name list
                q = p + 2
                ntype = data[q]
                nlen = struct.unpack("!H", data[q + 1:q + 3])[0]
                if ntype == 0:
                    return data[q + 3:q + 3 + nlen].decode("idna", "replace")
            p += elen
    except Exception:
        return None
    return None


async def pipe(reader, writer):
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(client_r, client_w):
    peer = client_w.get_extra_info("peername")
    try:
        head = await asyncio.wait_for(client_r.readuntil(b"\r\n\r\n"), timeout=15)
    except Exception:
        client_w.close()
        return

    lines = head.decode("latin1").split("\r\n")
    first = lines[0]
    parts = first.split()
    if len(parts) < 2:
        client_w.close()
        return
    method, target = parts[0], parts[1]

    if method.upper() != "CONNECT":
        # 明文 HTTP 代理请求：看 Host 头
        host = ""
        for ln in lines[1:]:
            if ln.lower().startswith("host:"):
                host = ln.split(":", 1)[1].strip()
        tag = classify(host)
        if host:
            log(f"HTTP  {host:40s} {target[:80]}  {('<= ' + tag) if tag else ''}")
        else:
            client_w.close()
            return
        try:
            uh, up = host.split(":")[0], int(host.split(":")[1]) if ":" in host else 80
        except ValueError:
            client_w.close()
            return
        try:
            up_r, up_w = await asyncio.open_connection(uh, up)
        except Exception as e:
            client_w.close()
            return
        up_w.write(head)
        await up_w.drain()
        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
        return

    # CONNECT: 先回 200，再从客户端读 ClientHello 拿 SNI
    host, _, port = target.partition(":")
    port = int(port or 443)
    log(f"CONNECT {host}:{port}")
    client_w.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
    await client_w.drain()

    try:
        hello = await asyncio.wait_for(client_r.read(8192), timeout=12)
        # ClientHello 可能跨 record 或一次没到齐，补读一次
        if hello and not parse_sni(hello):
            try:
                more = await asyncio.wait_for(client_r.read(8192), timeout=2)
                hello += more
            except Exception:
                pass
        if not hello:
            raise ValueError("empty")
    except Exception as e:
        log(f"  !! 读 ClientHello 失败({host}): {type(e).__name__}: {e}")
        client_w.close()
        return
    sni = parse_sni(hello) or host
    tag = classify(sni)
    extra = ""
    if "servicewechat.com" in sni:
        # 形如 <appid>.servicewechat.com 或 servicewechat.com/<appid>/...
        extra = " (小程序包/框架)"
    log(f"TLS   {sni:40s} :{port:<5} {('<= ' + tag) if tag else ''}{extra}")

    try:
        up_r, up_w = await asyncio.open_connection(host, port)
    except Exception as e:
        log(f"  !! 连接 {host}:{port} 失败: {e}")
        client_w.close()
        return
    up_w.write(hello)  # 把已读的 ClientHello 转给上游
    await up_w.drain()
    await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))


async def main(host, port):
    log(f"嗅探代理已启动 http://{host}:{port}  — 请把系统代理指到这里，然后打开「公大跑者」小程序")
    log("只记录域名/SNI，不解密、不落 body。结束后记得关闭系统代理。")
    server = await asyncio.start_server(handle, host, port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18081)
    a = ap.parse_args()
    try:
        asyncio.run(main(a.host, a.port))
    except KeyboardInterrupt:
        print("\n已停止。别忘了关闭系统代理。")
