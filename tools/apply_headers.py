# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""tools/apply_headers.py —— 版权头/构建戳维护

用法:
  py -3 tools/apply_headers.py            # 补齐/规范所有源文件的版权块
  py -3 tools/apply_headers.py --check    # 只检查（CI / 发布前门禁）
  py -3 tools/apply_headers.py --stamp    # 重写 lepao/_buildstamp.py（构建标识）
  py -3 tools/apply_headers.py --url <新仓库地址>   # 更新 release.meta.json 与全部文件头

设计约束（LRL-1.0 第三条）: 本工具只能**补齐或更新地址**，不能移除版权块。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_PATH = os.path.join(ROOT, "release.meta.json")

MARKER = "# --- lepao-research-notice v1 (do not remove; see LICENSE) ---"
END = "# --- end lepao-research-notice ---"

SCAN_DIRS = ("lepao", "tools", "工具", "ui")
SCAN_FILES = ("cli.py",)
SKIP_NAMES = {"__init__.py"} if False else set()


def load_meta():
    with open(META_PATH, encoding="utf-8") as f:
        return json.load(f)


def notice_block(meta):
    repo = meta.get("repo_url", "https://github.com/dan-cun/lepao3")
    author = meta.get("author", "dan-cun")
    year = meta.get("copyright_year", "2026")
    qq = meta.get("contact_qq", "")
    lic = meta.get("license_name", "乐跑研究协议 1.0")
    contact = f" · 技术讨论 QQ {qq}（仅作技术讨论，不提供代打卡）" if qq else ""
    return "\n".join([
        MARKER,
        f"# 乐跑协议研究（Lepao Research） · {repo}",
        f"# Copyright (c) {year} {author}{contact}",
        f"# 许可证 LRL-1.0（{lic}）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除",
        "# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。",
        END,
        f"# Copyright (c) {year} {author} · 许可协议见项目根目录 LICENSE",
    ])


def iter_sources():
    out = []
    for f in SCAN_FILES:
        p = os.path.join(ROOT, f)
        if os.path.isfile(p):
            out.append(p)
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.endswith(".py") and name not in SKIP_NAMES:
                out.append(os.path.join(base, name))
    return out


def split_head(text):
    """拆出 coding 行之前的 shebang / coding 声明，返回 (前缀行, 余下内容)。"""
    lines = text.splitlines()
    head = []
    i = 0
    while i < len(lines) and i < 3:
        s = lines[i].strip()
        if s.startswith("#!") or re.match(r"#.*coding[:=]", s):
            head.append(lines[i])
            i += 1
        else:
            break
    return head, lines[i:]


def has_block(text):
    return MARKER in text and END in text


def block_matches(text, block):
    """块存在、MARKER..END 段与规范逐字一致、且块后恰好一条 Copyright 行（防重复插入）。"""
    if not has_block(text):
        return False
    i = text.find(MARKER)
    j = text.find(END, i)
    if i < 0 or j < 0:
        return False
    seg = text[i:j + len(END)].strip()
    core = block[:block.find(END) + len(END)].strip()
    if seg != core:
        return False
    after = text[j + len(END):].splitlines()
    k = 0
    while k < len(after) and not after[k].strip():
        k += 1
    if k >= len(after) or not after[k].startswith("# Copyright (c)"):
        return False
    k += 1
    while k < len(after) and not after[k].strip():
        k += 1
    # 再出现一条 Copyright = 之前被重复插入过
    return not (k < len(after) and after[k].startswith("# Copyright (c)"))


def apply_to_file(path, block, check=False):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if check:
        return block_matches(text, block), False
    head, rest = split_head(text)
    body = "\n".join(rest)
    if MARKER in body:
        pre, mid = body.split(MARKER, 1)
        post = mid.split(END, 1)[1] if END in mid else ""
        lines = post.splitlines()
        # 丢掉 END 之后残留的空行与旧 Copyright 行（可能有多条 → 清干净, 保证幂等）
        while lines and (not lines[0].strip() or lines[0].startswith("# Copyright")):
            lines.pop(0)
        pre_clean = pre.rstrip("\n").lstrip("\n")
        parts = list(head) + [block]
        if pre_clean.strip():
            parts.append(pre_clean)
        parts.extend(lines)
        new_text = "\n".join(parts)
    else:
        new_text = "\n".join(list(head) + [block] + [body.lstrip("\n")])
    if not new_text.endswith("\n"):
        new_text += "\n"
    changed = new_text != text
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
    return True, changed


def write_buildstamp(meta, verbose=True):
    """重写 lepao/_buildstamp.py。BUILD_ID = 版本 + 内容指纹前 10 位（可复现）。"""
    ver = str(meta.get("version") or "0.0.0")
    h = hashlib.sha256()
    for p in iter_sources():
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except OSError:
            continue
    digest = h.hexdigest()[:10]
    build_id = f"{ver}-{digest}"
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = os.path.join(ROOT, "lepao", "_buildstamp.py")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r'^BUILD_ID = ".*"$', f'BUILD_ID = "{build_id}"', text, flags=re.M)
    text = re.sub(r'^BUILD_TIME = ".*"$', f'BUILD_TIME = "{now}"', text, flags=re.M)
    text = re.sub(r'^VERSION = ".*"$', f'VERSION = "{ver}"', text, flags=re.M)
    text = re.sub(r'^SOURCE = ".*"$', f'SOURCE = "{meta.get("repo_url", "")}"', text, flags=re.M)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if verbose:
        print(f"[stamp] {os.path.relpath(path, ROOT)} → BUILD_ID={build_id} at {now}")
    return build_id


def update_url(new_url, verbose=True):
    with open(META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    old = meta.get("repo_url", "")
    meta["repo_url"] = new_url
    with open(META_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if verbose:
        print(f"[url] {old} → {new_url}")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="版权头/构建戳维护")
    ap.add_argument("--check", action="store_true", help="只检查, 不修改（非 0 退出=不合格）")
    ap.add_argument("--stamp", action="store_true", help="重写构建标识")
    ap.add_argument("--url", help="更新仓库地址（元数据 + 全部文件头）")
    args = ap.parse_args(argv)

    if args.url:
        update_url(args.url)
    meta = load_meta()
    block = notice_block(meta)
    sources = iter_sources()

    if args.check:
        bad = []
        for p in sources:
            ok, _ = apply_to_file(p, block, check=True)
            if not ok:
                bad.append(os.path.relpath(p, ROOT))
        if bad:
            print(f"[check] ✗ {len(bad)} 个文件版权头缺失/不完整:")
            for b in bad:
                print("   " + b)
            print("→ 修复: py -3 tools/apply_headers.py")
            return 1
        print(f"[check] ✓ {len(sources)} 个源文件版权头齐全一致")
        return 0

    changed = 0
    for p in sources:
        ok, ch = apply_to_file(p, block)
        if ch:
            changed += 1
            print(f"[header] 已更新 {os.path.relpath(p, ROOT)}")
    print(f"[header] 完成: 扫描 {len(sources)} 个, 更新 {changed} 个")

    if args.stamp:
        write_buildstamp(meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
