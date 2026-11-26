# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""v3 抓包密文解密器 —— 从任何抓包工具里复制一段请求体，直接看明文。

为什么需要它：小程序 v3 的 body 是 `ostype=5&data=<AES>`，抓包工具（Reqable /
HttpCanary / Fiddler / Charles）只能看到密文。客户端手里有密钥（本就写在小程序里），
把密文丢进来就能还原出 school_id / uid / token / 业务参数。

用法：
  python 工具/decrypt_v3_blob.py --data "ostype=5&data=xxxxx"
  python 工具/decrypt_v3_blob.py --file capture.txt        # 自动从文本里提取 data= 段
  type capture.txt | python 工具/decrypt_v3_blob.py         # 管道

输出：格式化明文 JSON，并单独列出 school_id / uid / token / student_num（有则显示）。
"""
import argparse
import base64
import json
import re
import sys
import urllib.parse

import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lepao.crypto import decrypt_data, encrypt_data  # noqa: E402

KEYS = ("school_id", "uid", "token", "student_num", "card_id", "term_id",
        "course_id", "class_id", "timestamp", "nonce", "sign")


def extract_blobs(text: str):
    """从任意文本中提取 data= 的密文段（兼容 URL 编码与裸 base64）。"""
    out = []
    for m in re.finditer(r"data=([A-Za-z0-9+/=%]+)", text):
        raw = urllib.parse.unquote(m.group(1))
        raw = raw.replace(" ", "+")
        out.append(raw)
    if not out:
        # 裸 base64（>=32 字符，且能被 16 整除解码后）
        for m in re.finditer(r"[A-Za-z0-9+/]{32,}={0,2}", text):
            cand = m.group(0)
            try:
                if len(base64.b64decode(cand)) % 16 == 0:
                    out.append(cand)
            except Exception:
                continue
    return out


def try_decrypt(blob: str):
    try:
        plain = decrypt_data(blob)
        return json.loads(plain)
    except Exception:
        return None


def show(obj: dict, idx: int):
    print(f"===== 第 {idx} 段明文 =====")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print("--- 关键字段 ---")
    for k in KEYS:
        if k in obj:
            v = obj[k]
            if k == "token" and isinstance(v, str) and len(v) > 12:
                v = v[:8] + "…" + v[-4:] + f"（{len(v)} 位）"
            print(f"  {k:12s} = {v}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="完整请求体或仅 data= 后面的密文")
    ap.add_argument("--file", help="包含抓包文本的文件")
    ap.add_argument("--selftest", action="store_true", help="自检：加密再解密一条样本")
    a = ap.parse_args()

    if a.selftest:
        sample = {"uid": "UID_PLACEHOLDER", "token": "T" * 40, "school_id": 798,
                  "student_num": "STUDENT_NUM", "ostype": 5}
        body = "ostype=5&data=" + urllib.parse.quote(encrypt_data(json.dumps(sample)))
        blobs = extract_blobs(body)
        obj = try_decrypt(blobs[0]) if blobs else None
        ok = obj == sample
        print("自检:", "OK" if ok else f"FAIL {obj}")
        show(obj or {}, 1)
        return 0 if ok else 1

    text = a.data or ""
    if a.file:
        with open(a.file, encoding="utf-8", errors="replace") as f:
            text += "\n" + f.read()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text.strip():
        print("没有输入。用法见 --help")
        return 2

    # 先整体试一次（用户可能直接粘了裸密文）
    obj = try_decrypt(text.strip())
    if obj:
        show(obj, 1)
        return 0

    blobs = extract_blobs(text)
    if not blobs:
        print("没找到 data= 段，也没找到可解密的 base64。")
        return 2

    n = 0
    for b in blobs:
        obj = try_decrypt(b)
        if obj:
            n += 1
            show(obj, n)
    if not n:
        print(f"提取到 {len(blobs)} 段，但都解密失败（可能不是 v3 报文，或抓包被截断）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
