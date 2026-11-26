# ui/ —— 桌面端（不在本源码仓库范围内）

> **授权**：本程序按「乐跑研究协议 1.0（LRL-1.0）」提供 —— 仅供学习 · 不可牟利 ·
> 再发布须署名引用原始仓库 <https://github.com/dan-cun/lepao3> 并保留全部声明。
> 技术讨论 QQ 1224145544。

本仓库是**协议库 + 命令行**的源码版，不含桌面 GUI/EXE 源码与打包脚本。

## 为什么没有 GUI 源码

- 桌面端是 PyInstaller 打包的 Tk 控制台，属于发行物形态，不是协议研究的一部分；
- 它会把 `lepao` 包、轨迹模板、抓号 addon 一起冻结进 EXE，容易把本机数据带进发行包，
  与 LRL-1.0 第七条（发行面零个人信息）相冲突；
- 协议层与 CLI 已覆盖全部能力（`capture`/`build`/`submit`/`batch`/`watch`），
  有 GUI 需求的维护者可在自己的衍生版里实现。

## 想自己做 GUI

按 `lepao` 的既有分层接即可，最小接入面：

```python
from lepao.accounts import AccountRegistry
from lepao.auth import AuthState
from lepao.capture import CaptureSession
from lepao.pipeline import Pipeline
from lepao.state import StateStore

reg = AccountRegistry("config.json")
key = reg.resolve("你的成员")
st = AuthState(reg, key)
pipe = Pipeline(st, StateStore("state.json"), policy=reg.policy_of(key),
                verbose=True, log_fn=my_ui_log, stop_event=my_stop_event)
summary, code = pipe.run(submit=False)      # 干跑
```

注意事项：

1. **必须传 `log_fn`**：windowed（无控制台）模式下 `print` 进黑洞，会出现
   "程序显示成功、小程序没记录、日志里查不到原因"。
2. `stop_event` 用于「停止」按钮：`Pipeline._sleep()` 会响应中断并抛 `V3Error(9)`。
3. 抓号用 `CaptureSession`，不要自己拼 mitm 命令行（代理备份/复原、白名单、归位都在里面）。
4. 打包时排除 `config.json` / `state.json` / `凭证.json` / `data/真实轨迹*`；
   发行前跑 `py -3 tools/verify_release.py`。
