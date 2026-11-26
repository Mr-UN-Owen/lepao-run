# 程序目录说明

这里是全部可执行代码（Python 标准库即可运行）。项目总说明、三步开始、许可与免责请见仓库根目录的
[`README.md`](../README.md)、[`LICENSE`](../LICENSE) 与 [`MODIFICATIONS.md`](../MODIFICATIONS.md)。

| 子目录 / 文件 | 作用 |
|---|---|
| `webapp/` | 主程序：网页控制台（登录 → 打卡点 → 预览 → 提交） |
| `lepao/` | 协议库：AES-128-CBC / SignMD5 / 轨迹引擎 / v3 客户端 |
| `工具/` | 抓证工具：本机 MITM 代理、抓包启动器、域名嗅探 |
| `app/` | 进阶：旧版控制台（8770，需自备 config.json） |
| `cli.py` | 进阶：命令行流水线（account / capture / build / submit） |
| `selfcheck.py` | 环境自检（由 `启动脚本/5-环境自检.bat` 调用） |
| `_private/` | 运行时目录：会话、抓包明文、本机抓包证书；全部 gitignore，不入库 |

> 本目录下的 `LICENSE`、`LICENSE.md`、`NOTICE`、`DISCLAIMER.md`、`SECURITY.md`、`CONTRIBUTING.md`
> 与每个源文件顶部的 `lepao-research-notice` 版权块均来自上游
> [lepao3](https://github.com/dan-cun/lepao3)（作者 dan-cun），依 LRL-1.0 保留，请勿删除或替换。
> 本衍生版的修改记录见根目录 [`MODIFICATIONS.md`](../MODIFICATIONS.md)。
