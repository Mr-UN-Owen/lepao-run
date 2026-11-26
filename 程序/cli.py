# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""cli.py —— 命令行入口

退出码（与 README 一致）:
  0 过审/成功   2 token 失效或待抓号   3 当日额度已满   4 其他失败(含链不通)   5 受理但判无效

示例:
  py -3 cli.py account add 张三 XXXXXXXXX --alias 张三
  py -3 cli.py capture --member 张三          # 起 mitm, 人开小程序, token 归位
  py -3 cli.py build --member 张三            # 干跑(零写入)
  py -3 cli.py submit --member 张三           # 真正提交
  py -3 cli.py run                            # capture + submit 一键
  py -3 cli.py batch --submit                 # 全员错峰提交
  py -3 cli.py status --all
  py -3 cli.py watch 450655 --member 张三
  py -3 cli.py cert [--install] / license / wechat-status
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lepao import __version__  # noqa: E402
from lepao import license_guard  # noqa: E402
from lepao.accounts import AccountError, AccountRegistry  # noqa: E402
from lepao.state import StateStore  # noqa: E402

# 注意: auth/pipeline/capture/h5api 依赖 pycryptodome，按需在子命令内导入，
# 使 `license`/`account`/`cert` 等纯本地命令在没有装依赖时也能跑。
EXIT_OK, EXIT_TOKEN, EXIT_QUOTA, EXIT_FAIL, EXIT_INVALID = 0, 2, 3, 4, 5


# ================================================================ 上下文
class Ctx:
    def __init__(self, args, create=False):
        self.args = args
        self.quiet = bool(getattr(args, "quiet", False))
        cfg = getattr(args, "config", None) or os.environ.get("LEPAO_CONFIG") \
            or os.path.join(os.getcwd(), "config.json")
        self.reg = AccountRegistry(cfg, create=create, verbose=not self.quiet)
        self.data_dir = os.path.dirname(self.reg.config_path)
        self.state = StateStore(os.path.join(self.data_dir, "state.json"),
                                verbose=not self.quiet)

    def say(self, msg=""):
        if not self.quiet:
            print(msg)

    def member(self, sel=None):
        from lepao.auth import AuthState
        key = self.reg.resolve(sel if sel is not None else getattr(self.args, "member", None))
        return key, AuthState(self.reg, key)


# ================================================================ 子命令
def cmd_account(ctx):
    a = ctx.args
    act = a.action
    if act == "add":
        ctx.reg.add(a.name, a.student_num, alias=a.alias, school_id=a.school)
        return EXIT_OK
    if act == "list":
        keys = ctx.reg.keys()
        if not keys:
            ctx.say("成员表为空: `cli.py account add <名字> <学号>`")
            return EXIT_OK
        ctx.say(f"成员表 {ctx.reg.config_path}（active={ctx.reg.active or '-'}）")
        for k in keys:
            ctx.say("  " + ctx.reg.describe(k))
        return EXIT_OK
    if act == "remove":
        ctx.reg.remove(a.selector)
        return EXIT_OK
    if act == "set":
        key = ctx.reg.resolve(a.selector)
        prof = ctx.reg.acc(key)
        for f in ("uid", "school_id"):
            v = getattr(a, f)
            if v is not None:
                prof[f] = int(v)
        for f in ("name", "alias"):
            v = getattr(a, f)
            if v:
                prof[f] = v
        if a.active:
            ctx.reg.active = key
        ctx.reg.persist()
        ctx.say("[account] 已更新: " + ctx.reg.describe(key))
        return EXIT_OK
    raise AccountError(f"未知 account 动作: {act}")


def cmd_status(ctx):
    keys = ctx.reg.keys()
    if not keys:
        ctx.say("成员表为空")
        return EXIT_OK
    if not ctx.args.all:
        keys = [ctx.member()[0]]
    for k in keys:
        st = AuthState(ctx.reg, k)
        ctx.say(st.describe())
    return EXIT_OK


def cmd_set_token(ctx):
    key, st = ctx.member()
    st.set_token(ctx.args.token, source="manual")
    if ctx.args.no_probe:
        return EXIT_OK
    return EXIT_OK if st.probe() else EXIT_TOKEN


def cmd_capture(ctx):
    from lepao import wechat_ctl
    from lepao.capture import CaptureSession
    a = ctx.args
    env = ctx.reg.environment
    if env.get("wechat_logout_before_capture") and not a.keep_wechat:
        wechat_ctl.logout(verbose=not ctx.quiet)
    sess = CaptureSession(ctx.reg, data_dir=ctx.data_dir, port=a.port,
                          timeout=a.timeout, verbose=not ctx.quiet)
    key, st = sess.capture(timeout=a.timeout, probe=not a.no_probe)
    if key is None:
        ctx.say("[capture] 未抓到 token（按 README「抓不到登录流量」四步排查）")
        return EXIT_TOKEN
    if a.member:
        want = ctx.reg.resolve(a.member)
        if want != key:
            ctx.say(f"[capture] ⚠ 捕获身份 {key} 与请求成员 {want} 不一致, 已按身份归位到 {key}")
    return EXIT_OK if (a.no_probe or not st.token or st.probe(verbose=False)) else EXIT_TOKEN


def _pipeline(ctx):
    from lepao.pipeline import Pipeline
    key, st = ctx.member()
    pol = ctx.reg.policy_of(key)
    style = getattr(ctx.args, "style", None)
    if style:
        pol["style"] = style
    return st, Pipeline(st, ctx.state, policy=pol, verbose=not ctx.quiet,
                        log_fn=(None if ctx.quiet else print))


def cmd_build(ctx):
    st, pipe = _pipeline(ctx)
    out, code = pipe.run(submit=False, zone_override=ctx.args.zone)
    if out:
        ctx.say(json.dumps({k: out[k] for k in
                            ("track_points", "oss_record_file") if k in out},
                           ensure_ascii=False))
    return code


def cmd_submit(ctx):
    st, pipe = _pipeline(ctx)
    summary, code = pipe.run(submit=True, zone_override=ctx.args.zone)
    if summary and not ctx.quiet:
        ctx.say("RUN_RESULT:" + json.dumps(summary, ensure_ascii=False))
    return code


def cmd_run(ctx):
    rc = cmd_capture(ctx)
    if rc != EXIT_OK:
        return rc
    return cmd_submit(ctx)


def cmd_batch(ctx):
    keys = ctx.reg.keys()
    if not keys:
        ctx.say("成员表为空")
        return EXIT_OK
    rt = ctx.reg.runtime
    lo = int(rt.get("spacing_min") or 5) * 60
    hi = int(rt.get("spacing_max") or 10) * 60
    worst = EXIT_OK
    for i, k in enumerate(keys):
        prof = ctx.reg.acc(k)
        if not prof.get("enabled", True):
            ctx.say(f"[batch] 跳过已停用成员 {k}")
            continue
        st = AuthState(ctx.reg, k)
        if not st.token or st.consumed_at:
            ctx.say(f"[batch] {st.label}: 无可用 token（先 capture --member {k}）, 跳过")
            worst = max(worst, EXIT_TOKEN) if worst != EXIT_INVALID else worst
            continue
        pipe = Pipeline(st, ctx.state, policy=ctx.reg.policy_of(k),
                        verbose=not ctx.quiet, log_fn=(None if ctx.quiet else print))
        if ctx.args.submit:
            summary, code = pipe.run(submit=True, zone_override=ctx.args.zone)
            ctx.say(f"[batch] {st.label} → exit {code}")
        else:
            out, code = pipe.run(submit=False, zone_override=ctx.args.zone)
            ctx.say(f"[batch] {st.label} → dry-run exit {code}")
        if code != EXIT_OK:
            worst = code
        if ctx.args.submit and i != len(keys) - 1:
            wait = random.randint(lo, hi)
            ctx.say(f"[batch] 错峰等待 {wait // 60} 分钟（禁止并发/同刻提交）")
            time.sleep(wait)
    return worst


def cmd_quota(ctx):
    st, _ = ctx.member()
    client = st.make_client(pace=0.8)
    rule = client.before_run()
    if not isinstance(rule, dict) or not rule.get("run_line_info"):
        ctx.say(f"[quota] beforeRun 异常: {str(rule)[:200]}")
        return EXIT_FAIL
    pts = (rule["run_line_info"].get("point_list") or [])
    tr0 = (rule.get("time_rule_arr") or [{}])[0]
    ctx.say(f"[quota] 跑区={rule.get('run_zone_id')}({rule.get('run_zone_name')}) "
            f"打卡点={len(pts)} 学期={rule.get('term_id')} "
            f"距离={tr0.get('min_distance')}~{tr0.get('max_distance')}km")
    rec = client.get_term_run_record(rule.get("term_id") or 0, 1)
    n = len((rec or {}).get("list") or []) if isinstance(rec, dict) else 0
    ctx.say(f"[quota] 本学期最近记录 {n} 条（额度上限 {ctx.reg.policy_of(st.key)['max_per_day']}/日）")
    return EXIT_OK


def cmd_watch(ctx):
    st, _ = ctx.member()
    client = st.make_client(pace=0.8)
    detail = client.record_detail(ctx.record_id)
    if not isinstance(detail, dict):
        ctx.say(f"[watch] 响应异常: {str(detail)[:200]}")
        return EXIT_FAIL
    rsn = (detail.get("record_failed_reason") or "").strip()
    positive = (not rsn) or ("有效" in rsn and "无效" not in rsn
                             and "不" not in rsn and "异常" not in rsn)
    ctx.say(f"[watch] record={ctx.record_id} status={detail.get('record_status')} "
            f"reason={rsn!r} distance={detail.get('distance')}")
    if str(detail.get("record_status")) in ("0", "1") and positive:
        return EXIT_OK
    return EXIT_INVALID if rsn else EXIT_FAIL


def cmd_cert(ctx):
    from lepao import certctl
    if ctx.args.install:
        certctl.install()
    certctl.report()
    return EXIT_OK


def cmd_wechat(ctx):
    from lepao import wechat_ctl
    if ctx.args.action == "logout":
        return EXIT_OK if wechat_ctl.logout() else EXIT_FAIL
    wechat_ctl.status()
    return EXIT_OK


def cmd_h5(ctx):
    from lepao.h5api import H5Client
    a = ctx.args
    key, st = ctx.member()
    env = ctx.reg.environment
    cli = H5Client(host=env.get("api_host", "api2.lptiyu.com"),
                   base=env.get("h5_base"), school_id=st.school_id or 0)
    if a.action == "login":
        r = cli.login(a.student_num, a.password, school_id=st.school_id or None,
                      verbose=not ctx.quiet)
        if isinstance(r, dict) and r.get("status") == 1:
            ctx.say("[h5] 登录成功（session 通道可用; PHPSESSID 仅存进程内, 不落盘）")
            return EXIT_OK
        ctx.say(f"[h5] 登录失败: {r}")
        return EXIT_FAIL
    out = cli.session_check(uid=st.uid)
    ctx.say(json.dumps(out, ensure_ascii=False, indent=1))
    return EXIT_OK


def cmd_license(ctx):
    license_guard.check()
    ctx.say(f"lepao v{__version__} · 配置文件 {ctx.reg.config_path}")
    return EXIT_OK


# ================================================================ 解析器
def build_parser():
    p = argparse.ArgumentParser(
        prog="cli.py", description="乐跑协议研究 CLI（LRL-1.0 · 仅供学习 · 不可牟利）")
    p.add_argument("--config", help="config.json 路径（默认 ./config.json）")
    p.add_argument("-q", "--quiet", action="store_true", help="静默")
    p.add_argument("--version", action="version", version=f"lepao {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("account", help="成员管理")
    pa_sub = pa.add_subparsers(dest="action", required=True)
    add = pa_sub.add_parser("add", help="登记成员（姓名 + 学号）")
    add.add_argument("name")
    add.add_argument("student_num")
    add.add_argument("--alias")
    add.add_argument("--school", type=int)
    pa_sub.add_parser("list", help="成员总览")
    rm = pa_sub.add_parser("remove", help="移除成员")
    rm.add_argument("selector")
    stp = pa_sub.add_parser("set", help="修改成员字段")
    stp.add_argument("selector")
    stp.add_argument("--uid", type=int)
    stp.add_argument("--school_id", type=int, dest="school_id")
    stp.add_argument("--name")
    stp.add_argument("--alias")
    stp.add_argument("--active", action="store_true", help="同时设为 active")

    ps = sub.add_parser("status", help="token 状态")
    ps.add_argument("--all", action="store_true")
    ps.add_argument("--member")

    pc = sub.add_parser("capture", help="抓号（起 mitm, 人开小程序）")
    pc.add_argument("--member")
    pc.add_argument("--timeout", type=int, default=240)
    pc.add_argument("--port", type=int)
    pc.add_argument("--no-probe", action="store_true", help="抓到后不做真门探测")
    pc.add_argument("--keep-wechat", action="store_true", help="不先退出微信")

    pb = sub.add_parser("build", help="干跑（零写入）")
    pb.add_argument("--member")
    pb.add_argument("--zone")
    pb.add_argument("--style", choices=("template", "math"))

    psub = sub.add_parser("submit", help="提交打卡")
    psub.add_argument("--member")
    psub.add_argument("--zone")

    pr = sub.add_parser("run", help="capture + submit 一键")
    pr.add_argument("--member")
    pr.add_argument("--zone")
    pr.add_argument("--timeout", type=int, default=240)
    pr.add_argument("--port", type=int)
    pr.add_argument("--no-probe", action="store_true")
    pr.add_argument("--keep-wechat", action="store_true")

    pbt = sub.add_parser("batch", help="批量（默认干跑, --submit 才真提交）")
    pbt.add_argument("--submit", action="store_true")
    pbt.add_argument("--zone")

    pq = sub.add_parser("quota", help="跑区/打卡点/额度（只读）")
    pq.add_argument("--member")

    pw = sub.add_parser("watch", help="复核某条记录")
    pw.add_argument("record_id")
    pw.add_argument("--member")

    ptk = sub.add_parser("set-token", help="人工装载 token")
    ptk.add_argument("token")
    ptk.add_argument("--member")
    ptk.add_argument("--no-probe", action="store_true")

    pce = sub.add_parser("cert", help="mitm 根证书体检/安装")
    pce.add_argument("--install", action="store_true")

    pwx = sub.add_parser("wechat", help="微信进程状态/退出")
    pwx.add_argument("action", choices=("status", "logout"))

    ph5 = sub.add_parser("h5", help="H5 面独立登录链")
    ph5.add_argument("action", choices=("login", "check"))
    ph5.add_argument("--member")
    ph5.add_argument("--student_num")
    ph5.add_argument("--password")

    sub.add_parser("license", help="许可证/署名/声明自检")
    return p


DISPATCH = {
    "account": cmd_account, "status": cmd_status, "capture": cmd_capture,
    "build": cmd_build, "submit": cmd_submit, "run": cmd_run, "batch": cmd_batch,
    "quota": cmd_quota, "watch": cmd_watch, "set-token": cmd_set_token,
    "cert": cmd_cert, "wechat": cmd_wechat, "h5": cmd_h5, "license": cmd_license,
}

# account add 需要在没有 config.json 时也能创建
CREATE_CMDS = {("account", "add")}


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.quiet:
        license_guard.print_notice()
        license_guard.assert_declarations()
    try:
        create = (args.cmd, getattr(args, "action", None)) in CREATE_CMDS
        ctx = Ctx(args, create=create)
        return DISPATCH[args.cmd](ctx) or EXIT_OK
    except ModuleNotFoundError as e:
        print(f"[error] 缺 Python 依赖: {e.name}")
        print("        py -3 -m pip install -r requirements.txt"
              "（抓号还需 mitmproxy; H5 登录需 ddddocr）")
        return EXIT_FAIL
    except AccountError as e:
        print(f"[error] {e}")
        return EXIT_TOKEN if "token" in str(e) else EXIT_FAIL
    except KeyboardInterrupt:
        print("\n[中断] 已退出（系统代理请用 `cli.py capture` 正常结束或手动复原）")
        return EXIT_FAIL
    except Exception as e:  # noqa: BLE001
        if os.environ.get("LEPAO_DEBUG"):
            raise
        code = getattr(e, "code", None)
        msg = getattr(e, "msg", "") or str(e)
        if isinstance(code, int):          # V3Error（延迟导入, 按 code 映射退出码）
            print(f"[error] V3Error({code}) {msg[:200]}")
            return {101: EXIT_TOKEN, 3: EXIT_QUOTA}.get(code, EXIT_FAIL)
        print(f"[error] {type(e).__name__}: {msg[:300]}")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
