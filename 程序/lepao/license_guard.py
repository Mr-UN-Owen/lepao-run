# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.license_guard —— 声明完整性自检 / 署名输出（LRL-1.0 第三、十一条）

启动时打印署名与声明指纹; 声明文件缺失或版权头被移除时给出**显式警示**。
这里刻意不做"缺文件就拒绝运行"的硬锁: 硬锁会让人用改代码的方式绕过, 反而更容易丢声明。
"""
import hashlib
import os

NOTICE_MARKER = "# --- lepao-research-notice v1 (do not remove; see LICENSE) ---"
NOTICE_END = "# --- end lepao-research-notice ---"

REQUIRED_FILES = (
    "LICENSE", "LICENSE.md", "NOTICE", "DISCLAIMER.md", "SECURITY.md",
    "CONTRIBUTING.md", "README.md",
)

SIGNATURE_LINE = (
    "乐跑协议研究（Lepao Research） · Copyright (c) 2026 dan-cun\n"
    "源码 https://github.com/dan-cun/lepao3 · 许可证 LRL-1.0（仅供学习 · 不可牟利）\n"
    "再发布须保留全部声明文件与源文件版权头并署名引用原始仓库 · 技术讨论 QQ 1224145544"
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256_of(path, limit=1 << 20):
    try:
        with open(path, "rb") as f:
            h = hashlib.sha256()
            while True:
                b = f.read(65536)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return ""


def missing_declarations(root=None):
    root = root or repo_root()
    return [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(root, f))]


def files_without_header(root=None):
    """扫描 lepao/*.py 与 cli.py，返回缺版权块的文件（apply_headers --check 的轻量版）。"""
    root = root or repo_root()
    bad = []
    targets = [os.path.join(root, "cli.py")]
    pkg = os.path.join(root, "lepao")
    if os.path.isdir(pkg):
        targets += [os.path.join(pkg, n) for n in sorted(os.listdir(pkg))
                    if n.endswith(".py")]
    for p in targets:
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(2048)
        except OSError:
            continue
        if NOTICE_MARKER not in head or NOTICE_END not in head:
            bad.append(os.path.relpath(p, root))
    return bad


def check(root=None, verbose=True):
    root = root or repo_root()
    missing = missing_declarations(root)
    no_header = files_without_header(root)
    lic = os.path.join(root, "LICENSE")
    info = {
        "root": root,
        "missing_declarations": missing,
        "files_without_header": no_header,
        "license_sha256_16": sha256_of(lic)[:16] if os.path.isfile(lic) else "",
        "ok": not missing and not no_header,
    }
    if verbose:
        if info["ok"]:
            print("[license] 声明完整性: OK")
        else:
            print("[license] ⚠ 声明完整性异常（LRL-1.0 第三条: 删除或篡改声明 = 授权自动终止）")
            for f in missing:
                print(f"[license]   缺声明文件: {f}")
            for f in no_header:
                print(f"[license]   缺版权头: {f}")
    return info


def print_notice(verbose=True):
    """程序运行时可见输出中的署名（LRL-1.0 要求的"三处"之一）。"""
    if not verbose:
        return
    try:
        from ._buildstamp import BUILD_ID, BUILD_TIME, VERSION
        stamp = f"build {BUILD_ID} ({BUILD_TIME}) · v{VERSION}"
    except Exception:
        stamp = "build ?"
    print("=" * 68)
    print(SIGNATURE_LINE)
    print(stamp)
    print("=" * 68)


def assert_declarations():
    """启动时自检: 只告警 + 返回是否完整。"""
    info = check(verbose=False)
    if not info["ok"]:
        print("⚠ 声明文件/版权头不完整 —— LRL-1.0 第三条: 删除或篡改声明即自动终止授权。")
        for f in info["missing_declarations"]:
            print(f"   缺: {f}")
        for f in info["files_without_header"]:
            print(f"   版权头缺失: {f}")
        print("   修复: py -3 tools/apply_headers.py")
    return info["ok"]
