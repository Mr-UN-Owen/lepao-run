#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 iOS 备份中提取步道乐跑 App 的 SQLite 数据库，并导出指定表。

v2 变更:
  - Bundle ID 默认改为 iOS 真实值 com.lepao.lptiyu（安卓包名是 com.lptiyu.tanke，两者不同）
  - 支持 --bundle 覆盖
  - domain 找不到时，自动列出备份里所有 AppDomain-* 供挑选
  - --reuse 可直接复用已有备份（改 domain 重查，无需重新备份）

用法:
    python extract_lepao_db.py --out ./lepao_backup --reuse          # 复用已有备份，秒出
    python extract_lepao_db.py --out ./lepao_backup                  # 备份 + 提取
    python extract_lepao_db.py --out ./lepao_backup --reuse --bundle com.lepao.lptiyu
    python extract_lepao_db.py --out ./lepao_backup --reuse --table SCHOOL_MORE_INFO
    python extract_lepao_db.py --out ./lepao_backup --reuse --list-apps   # 只列出备份里的所有 App 域

依赖: pip install pymobiledevice3
"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

# iOS 真实 Bundle ID（安卓包名 com.lptiyu.tanke 在 iOS 备份里不存在）
DEFAULT_BUNDLE = "com.lepao.lptiyu"
# 兜底候选：自动探测时按这些关键字匹配
BUNDLE_HINTS = ("lepao", "lptiyu")


def log(msg):
    print(f"[*] {msg}", flush=True)


def die(msg):
    print(f"[!] {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- 备份
def device_list():
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pymobiledevice3", "usbmux", "list"],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout.strip()
    except Exception as e:
        die(f"pymobiledevice3 调用失败: {e}（先 pip install pymobiledevice3）")


def run_backup(out_dir):
    log(f"开始全量备份到 {out_dir}（增量续传；保持手机解锁、别锁屏）")
    cmd = [sys.executable, "-m", "pymobiledevice3", "backup2", "backup", "--full", str(out_dir)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            print("   ", line[-160:], flush=True)
    proc.wait()
    if proc.returncode != 0:
        die(f"备份失败，退出码 {proc.returncode}（常见原因：手机锁屏了）")


def find_manifest(out_dir):
    root = Path(out_dir).resolve()
    for cand in root.rglob("Manifest.db"):
        return cand.parent
    return None


# ---------------------------------------------------------------- 域枚举
def list_domains(backup_root):
    con = sqlite3.connect(f"file:{backup_root / 'Manifest.db'}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT DISTINCT domain FROM Files WHERE domain LIKE 'AppDomain-%' ORDER BY domain")
    doms = [r[0] for r in cur.fetchall()]
    con.close()
    return doms


def guess_bundle(backup_root):
    doms = list_domains(backup_root)
    for d in doms:
        low = d.lower()
        if any(h in low for h in BUNDLE_HINTS):
            return d.replace("AppDomain-", "", 1)
    return None


# ---------------------------------------------------------------- 定位文件
def locate_db_files(backup_root, domain):
    con = sqlite3.connect(f"file:{backup_root / 'Manifest.db'}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT fileID, relativePath, flags FROM Files WHERE domain = ? "
        "AND (relativePath LIKE '%databases%' OR relativePath LIKE '%.db' "
        "     OR relativePath LIKE '%.sqlite' OR relativePath LIKE '%.realm')",
        (domain,),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def extract_files(backup_root, rows, dest_dir):
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    got = []
    for file_id, rel_path, flags in rows:
        if flags == 2 and "." not in Path(rel_path).name:
            continue
        src = backup_root / file_id[:2] / file_id
        if not src.exists():
            continue
        name = rel_path.replace("/", "_").lstrip("_")
        target = dest / name
        try:
            shutil.copy2(src, target)
            got.append((target, rel_path))
        except Exception as e:
            log(f"复制失败 {rel_path}: {e}")
    return got


# ---------------------------------------------------------------- 读表
def list_tables(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    info = []
    for t in tables:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            info.append((t, cur.fetchone()[0]))
        except Exception:
            info.append((t, -1))
    con.close()
    return info


def dump_table(db_path, table):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(f'SELECT * FROM "{table}"')
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="./lepao_backup")
    ap.add_argument("--result", default="./school_list.json")
    ap.add_argument("--dbs", default="./lepao_dbs")
    ap.add_argument("--table", default="SCHOOL_LIST_INFO")
    ap.add_argument("--bundle", default=DEFAULT_BUNDLE, help="iOS Bundle ID")
    ap.add_argument("--reuse", action="store_true", help="跳过备份，复用已有目录")
    ap.add_argument("--list-apps", action="store_true", help="只列出备份里所有 App 域，不提取")
    args = ap.parse_args()

    if not args.reuse:
        log("检测设备…")
        devs = device_list()
        print(devs if devs else "   (未发现设备)")
        if not devs:
            die("没有检测到设备。检查数据线、解锁屏幕、点「信任此电脑」。")
        run_backup(args.out)

    log("定位 Manifest.db …")
    backup_root = find_manifest(args.out)
    if not backup_root:
        die(f"在 {args.out} 里找不到 Manifest.db，备份可能没完成")
    log(f"备份根目录: {backup_root}")

    domains = list_domains(backup_root)
    log(f"备份里共有 {len(domains)} 个 App 域")

    if args.list_apps:
        for d in domains:
            print("   ", d)
        return

    # 确定 domain
    domain = f"AppDomain-{args.bundle}"
    if domain not in domains:
        log(f"{domain} 不在备份里，尝试自动探测…")
        guessed = guess_bundle(backup_root)
        if guessed:
            log(f"自动匹配到: com.{guessed} 之外的 {guessed}")
            args.bundle = guessed
            domain = f"AppDomain-{guessed}"
        else:
            print("\n=== 备份里所有 App 域（前 60 个）===")
            for d in domains[:60]:
                print("   ", d)
            die(f"找不到 {domain}，也不含 lepao/lptiyu 关键字。用 --bundle 指定上面列表里的某个。")

    log(f"使用 domain: {domain}")
    rows = locate_db_files(backup_root, domain)
    if not rows:
        die(f"{domain} 里没有 .db/.sqlite/.realm 文件。")
    for fid, rp, _ in rows:
        log(f"   {rp}")

    log("抽取文件…")
    got = extract_files(backup_root, rows, args.dbs)
    if not got:
        die("文件抽取全部失败，检查备份是否完整")

    log("扫描各数据库的表…")
    best = None
    for path, rel in got:
        try:
            tables = list_tables(path)
        except Exception as e:
            log(f"   {path.name}: 打不开 ({e})")
            continue
        log(f"   {path.name}: " + ", ".join(f"{t}({n})" for t, n in tables[:12]) + (" …" if len(tables) > 12 else ""))
        names = [t for t, _ in tables]
        if args.table in names:
            n = dict(tables)[args.table]
            if n > 0:
                best = (path, args.table)
                break
            if best is None:
                best = (path, args.table)

    if not best:
        die(f"没有任何数据库包含表 {args.table}。上面已列出所有表，用 --table 指定。")

    path, table = best
    log(f"导出 {path.name} :: {table}")
    rows_out = dump_table(path, table)

    result = {
        "bundle_id": args.bundle,
        "db_file": path.name,
        "db_source_path": next(r for p, r in got if p == path),
        "table": table,
        "row_count": len(rows_out),
        "rows": rows_out,
    }
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"完成 → {args.result}（{len(rows_out)} 行）")

    if rows_out:
        log("列: " + ", ".join(rows_out[0].keys()))
        for r in rows_out[:5]:
            log("   示例: " + json.dumps(r, ensure_ascii=False)[:220])


if __name__ == "__main__":
    main()
