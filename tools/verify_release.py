# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""tools/verify_release.py —— 发行门禁（声明完整性 + 个人信息泄露 + 出网面）

用法:
  py -3 tools/verify_release.py               # 全量扫描（发布前必跑）
  py -3 tools/verify_release.py --staged      # 只扫 git 暂存区（提 PR 前）
  py -3 tools/verify_release.py --network     # 附加: 可疑出网调用扫描
  py -3 tools/verify_release.py --exe 某.exe   # 附加: 发行物存在性与构建戳
  py -3 tools/verify_release.py --fix-url <新地址>   # 更新仓库地址

判定为"泄露"的项一律阻断（退出码 1）:
  邮箱 / 手机号 / 学号 / 大数 uid / 长 token / 真实校名 / 坐标对 / 服务端记录号目录
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "release.meta.json")

REQUIRED = ("LICENSE", "LICENSE.md", "NOTICE", "DISCLAIMER.md",
            "SECURITY.md", "CONTRIBUTING.md", "README.md")

SCAN_EXT = (".py", ".md", ".json", ".ps1", ".txt", ".js", ".mjs", ".cjs", ".html", ".yml")
SKIP_DIRS = {".git", "__pycache__", "_private", "research", "node_modules",
             "logs", "runtime", "dist", "build", ".venv", "venv", "ui/runtime"}

# 允许出现的"看起来像 PII"的已知常量（协议常量 / 公开 ID / 占位）
ALLOW_MARKERS = (
    "Wet2C8d34f62ndi3", "K6iv85jBD8jgf32D", "rDJiNB9j7vD2",
    "wxb2043232183dac7f", "lptiyu", "servicewechat", "example.com",
    "XXXXXXXXX", "0000000", "STUDENT_NUM", "USER_ID", "REDACTED",
    "qq.com.cn", "@qq.", "1224145544",
)

PATTERNS = [
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("学号(10位)", re.compile(r"(?<!\d)(?:19|20)\d{8}(?!\d)")),
    ("大数uid", re.compile(r'["\']?uid["\']?\s*[:=]\s*["\']?(\d{5,})')),
    # 只匹配"上下文明确是凭据"的长串，避免把注释分隔线与字符集常量误判为 token
    ("长token", re.compile(
        r"(?i)\b(access_token|refresh_token|token|session|sessionid|cookie|authorization|bearer)"
        r"\b[^\n]{0,24}?[:=]\s*[\"']?([A-Za-z0-9_\-\.]{32,})")),
    ("坐标对", re.compile(r"\b(\d{2}\.\d{4,})\s*,\s*(\d{2,3}\.\d{4,})\b")),
    ("真实校名", re.compile(r"(北京邮电|清华|北京大学|浙江大学|复旦大学|上海交通)大学?")),
    ("记录号文件", re.compile(r"rec_\d{6}\.json|payload_clone\.json|records\.json")),
]

# 明显是排版分隔线/纯符号的行，直接跳过
DECOR_LINE = re.compile(r"^[\s#\-=*_~<>|+÷—-]*$")


NETWORK_HINTS = ("requests.post", "requests.get", "urllib.request", "socket.socket",
                 "http.client.HTTPSConnection", "fetch(", "axios")


def load_meta():
    with open(META, encoding="utf-8") as f:
        return json.load(f)


def iter_files(only=None):
    if only is not None:
        yield from only
        return
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and f"{rel_dir}/{d}".lstrip("./") not in SKIP_DIRS]
        for n in filenames:
            p = os.path.join(dirpath, n)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            if n.endswith(SCAN_EXT) or n in REQUIRED:
                yield p


def staged_files():
    try:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return [os.path.join(ROOT, x.strip()) for x in out.stdout.splitlines() if x.strip()]


def allowed(line):
    if DECOR_LINE.match(line.strip()):
        return True
    return any(m in line for m in ALLOW_MARKERS)


def scan_pii(files):
    """返回 (findings, scanned_count)。findings = [(rel, lineno, kind, snippet)]"""
    findings = []
    scanned = 0
    for p in files:
        if not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if rel.split("/")[0] in SKIP_DIRS:
            continue
        if rel in ("tools/verify_release.py",):
            continue  # 本文件自身含检测用正则，豁免
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        scanned += 1
        for i, line in enumerate(lines, 1):
            if allowed(line):
                continue
            for kind, pat in PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                snippet = line.strip()[:110]
                findings.append((rel, i, kind, snippet))
                break
    return findings, scanned


def check_declarations():
    missing = [f for f in REQUIRED if not os.path.isfile(os.path.join(ROOT, f))]
    sys.path.insert(0, ROOT)
    try:
        from lepao import license_guard
        no_header = license_guard.files_without_header()
    except Exception:
        no_header = []
    return missing, no_header


def check_network(files):
    """静态找可疑出网点：所有出网调用都应在 lptiyu / 本地，其余需人工确认。"""
    hits = []
    for p in files:
        if not p.endswith(".py") or not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if any(h in line for h in NETWORK_HINTS):
                hits.append((rel, i, line.strip()[:100]))
    return hits


def check_exe(path):
    import hashlib
    if not os.path.isfile(path):
        print(f"[exe] ✗ 不存在: {path}")
        return False
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    meta = load_meta()
    print(f"[exe] {os.path.basename(path)}  {size/1048576:.1f} MB  "
          f"sha256={h.hexdigest()[:16]}…  期望版本={meta.get('version')}")
    return True


def fix_url(new_url):
    path = META
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["repo_url"] = new_url
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[url] repo_url → {new_url}（记得再跑 apply_headers.py 同步文件头）")


def main(argv=None):
    ap = argparse.ArgumentParser(description="发行门禁: 声明完整性 + 个人信息泄露扫描")
    ap.add_argument("--staged", action="store_true", help="只扫 git 暂存文件")
    ap.add_argument("--network", action="store_true", help="附加出网调用扫描")
    ap.add_argument("--exe", help="检查发行物（EXE/安装包）")
    ap.add_argument("--fix-url", help="更新 release.meta.json 的仓库地址")
    args = ap.parse_args(argv)

    if args.fix_url:
        fix_url(args.fix_url)
        return 0

    only = staged_files() if args.staged else None
    if args.staged and only is None:
        print("[gate] 非 git 仓库或 git 不可用 → 退化为全量扫描")
        only = None
    files = list(iter_files(only))

    print("=" * 62)
    print("乐跑协议研究 · 发行门禁")
    print("=" * 62)

    ok = True
    missing, no_header = check_declarations()
    if missing:
        ok = False
        print(f"[声明] ✗ 缺文件: {', '.join(missing)}")
    else:
        print(f"[声明] ✓ {len(REQUIRED)} 个声明文件齐全")
    if no_header:
        ok = False
        print(f"[声明] ✗ 版权头缺失: {', '.join(no_header)}")
    else:
        print("[声明] ✓ 全部源文件含版权块")

    findings, scanned = scan_pii(files)
    if findings:
        ok = False
        print(f"[PII ] ✗ {len(findings)} 处疑似个人信息（扫描 {scanned} 个文件）:")
        for rel, ln, kind, snippet in findings[:60]:
            print(f"   {rel}:{ln}  [{kind}]  {snippet}")
        if len(findings) > 60:
            print(f"   … 其余 {len(findings)-60} 处省略")
    else:
        print(f"[PII ] ✓ 未发现个人信息（扫描 {scanned} 个文件）")

    if args.network:
        hits = check_network(files)
        hosts = sorted({h[2] for h in hits})
        print(f"[NET ] 出网调用 {len(hits)} 处（应仅指向 lptiyu 域名; 人工确认其余）")
        for rel, ln, line in hits[:20]:
            print(f"   {rel}:{ln}  {line}")

    if args.exe:
        ok = check_exe(args.exe) and ok

    print("-" * 62)
    print("结果:", "PASS（可发布）" if ok else "FAIL（阻断发布，按上面条目修复）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
