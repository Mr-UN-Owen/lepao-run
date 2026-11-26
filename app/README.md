# app/ —— 本地 Web 控制台（成品应用形态）

> 许可证同主仓库 **LRL-1.0**：仅供学习 · 不可牟利 · 再发布须署名引用
> <https://github.com/dan-cun/lepao3> 并保留全部声明。本目录不含任何账号数据。

## 这是什么

把 `lepao` 协议栈包成「双击就能用」的应用。和 bupt-run 那类桌面 EXE 等价，但形态换成
**本机网页**：不打包、不写注册表、不需要 Tk，浏览器打开 `127.0.0.1:8770` 即可。

```
app/
├── server.py     零依赖 HTTP 服务（标准库 http.server），REST + 静态页
├── index.html    单页控制台（原生 JS，无框架、无外部请求）
└── README.md     本文件
启动控制台.bat     Windows 双击入口（起服务 + 开浏览器）
```

界面只调 `lepao` 既有分层（`AccountRegistry` / `AuthState` / `Pipeline` / `StateStore`），
不复制任何协议逻辑——协议改动仍然只发生在 `lepao/` 里。

## 用法

```bash
py -3 app/server.py --port 8770      # 或双击 启动控制台.bat
```

打开后三步：**登记录入学号 → 抓号（见下）→ 干跑 → 提交**。

| 按钮 | 行为 | 写服务端？ |
|---|---|---|
| 干跑（零写入） | 真门 → 跑区 → 额度 → 时间 → 轨迹 → 覆盖校验 | 否 |
| 提交打卡 | 加 OSS 上传 + `stopRunV278` + 复核 | 是，每日按 `policy.max_per_day` |
| 停止 | 置 `stop_event`，任务在下一个检查点抛 `V3Error(9)` | — |

> 抓号（`capture`）仍然走命令行：它要起 mitm、改系统代理、要人打开小程序，
> 做成按钮反而更容易出错。`py -3 cli.py capture --member <名字>` 跑完 token 会落到
> `config.json`，界面刷新即可看到「token 就绪」。

## 网页账号登录（H5 面）—— 不抓包、不 root、不需要虚拟定位

界面左栏第二张卡片是 H5 登录器。它走的是平台上那套独立的 ThinkPHP 应用
（`/bdlp_h5_fitness_test/public/index.php`），与微信小程序的 token 面是**两套鉴权**：

```
GET  index/Login/getToken                        → {"status":1,"code":"<v-token>"}
GET  index/Login/verify?token=<v-token>&random=.. → 4 位数字验证码 PNG + Set-Cookie PHPSESSID
POST index/Login/login {school_id, student_num, password, verify,
                        login_type:2, token:<v-token>}  → PHPSESSID 会话
```

本机实测（2026-11-24，api2.lptiyu.com）：

| 步骤 | 结果 |
|---|---|
| getToken | `status:1`，返回 v-token |
| verify | 200，返回 4 位验证码 PNG（约 1.5 KB） |
| login（假账号 + 正确验证码） | `status:0` / **"学号或密码输入有误，请重新输入"** |
| login（验证码读错） | `status:0` / "验证码错误" |

也就是说：**链路是活的，只差一个真实账号密码**。验证码是 4 位数字、无扭曲干扰，
人工目视或 ddddocr 都能过；实测 5 连错不锁（P15）。

### 需要填的三个东西

| 字段 | 说明 |
|---|---|
| `school_id` | 学校编号，平台的学校主键（北邮是 798/837 这类三位数）。公大的编号要靠抓包或"学号反查学校"接口取 |
| 账号 | `student_num` 字段，实测接受任意字符串；学号 / 邮箱 / 手机号取决于学校在平台里的账号体系 |
| 密码 | 平台密码，不是校内统一身份认证密码（后者要走 SSO，是另一条链） |

### 登录成功之后能干什么

控制台的「探测接口」按钮会拿 PHPSESSID 探三个 H5 接口，直接告诉你这个账号的权限边界：

| 接口 | 用途 |
|---|---|
| `Index/checkLogin` | 会话是否有效 |
| `Report/getStudentScore` | 成绩/跑量报表（只读） |
| `Offline/index` | **线下打卡**入口 —— 补录跑步记录，不带 GPS/传感器校验 |

> 注意术语：v3 主 API **没有"修改已有记录"的接口**，只有 `stopRunV278` 新增提交。
> 所谓"网页端改跑步数据"，实际是两条路：H5 的 `Offline` 线下补录，或 v3 的轨迹提交。
> 前者更轻，后者数据更完整（有轨迹/步频），按学校开关选。

## 零依赖改造（本轮新增）

| 文件 | 变化 |
|---|---|
| `lepao/aes.py` | 新增：纯 Python AES-128-CBC + PKCS7（FIPS-197 向量 + openssl 交叉验证通过） |
| `lepao/crypto.py` | 优先 pycryptodome，缺失自动回退纯 Python；`crypto.backend()` 可查当前后端 |
| `app/server.py` | 新增：控制台后端 |
| `app/index.html` | 新增：控制台前端 |

意义：整个工具现在只依赖 **Python 标准库**（brotli 可选），可以做绿色版 / PyInstaller 单文件，
不必再让使用者装 `pycryptodome`。

## 换学校 / 换站点要改哪里

控制台本身与站点无关，判定后按需改这几处：

| 位置 | 字段 | 说明 |
|---|---|---|
| `lepao/transport.py` | `APP_ID` / `REFERER` / `UA_ANDROID` | 小程序的 appid 与 page-frame 版本号 |
| `lepao/v3api.py` | 请求 BASE | `https://<api_host>` |
| `config.json` → `environment` | `api_host` / `app_key` / `oss_host` | 站点与 OSS 桶 |
| `config.json` → `policy` | `dist_lo/hi`、`pace_lo/hi`、`max_per_day` | 换学校必须重设（公大是 ≥2.5~3km、配速 3~7.5） |
| `lepao/track.py` | 跑区/打卡点来源 | 已从 `beforeRunV260` 动态读取，一般不用改 |

先用 `工具/proxy_sniff.py` 确认域名，再动这些常量——顺序反了会白改。

## 与 bupt-run 形态的差异

| 维度 | bupt-run 类桌面 EXE | 本控制台 |
|---|---|---|
| 分发 | PyInstaller 单文件，几十 MB | 源码 + 一个 bat，零打包 |
| 界面 | Tk / 原生窗口 | 浏览器（手机同局域网也能开） |
| 依赖 | pycryptodome + requests | 纯标准库 |
| 数据落盘 | 打进 EXE 容易带出个人信息 | 只写 `config.json` / `state.json`，已 gitignore |
| 扩展 | 改 EXE 要重新打包 | 改 html 刷新即可 |

## 注意

1. `Pipeline` 必须传 `log_fn`（本实现已传），否则 windowed 模式下日志进黑洞。
2. `state.json` 是证据链，干跑也会写本地（不写服务端）；介意的删掉即可。
3. 界面默认只听 `127.0.0.1`，不要改成 `0.0.0.0` 除非你明确知道后果（同网段任何人都能点提交）。
