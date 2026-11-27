# 修改记录（MODIFICATIONS）

> 依据《乐跑研究协议 1.0（LRL-1.0）》第二条第 3 款：衍生作品必须显著标注修改者、修改日期与修改范围。

## 衍生版信息

| 项 | 内容 |
|---|---|
| 衍生版名称 | 校园跑协议研究 · 网页控制台（lepao-run） |
| 修改者 | `zixuanaYuan`（请替换为真实署名） |
| 修改日期 | 2026-11-26 |
| 上游项目 | 乐跑协议研究（Lepao Research）v2.2.0，build `2.2.0-01bd7da4db` |
| 上游作者 | dan-cun |
| 上游仓库 | <https://github.com/dan-cun/lepao3> |
| 许可证 | 乐跑研究协议 1.0（LRL-1.0），沿用上游，未改换 |
| 本版性质 | 源码公开、非商业；**不是 OSI 开源软件** |

## 修改范围

1. **移除预置抓包证书与全部私钥**（安全修复，最重要的一项）
   - 删除上游发行包里的 `程序/_private/mitm_ca/`：1 个根 CA 私钥 + 44 个域名叶证书私钥（合计 45 个私钥），
     其中包含 `weixin.qq.com`、`map.qq.com`、`login.live.com`、`graph.microsoft.com` 等与本项目无关域名的私钥。
   - 共用同一把根 CA 私钥意味着任何拿到仓库的人都能对这些域名做中间人，因此不再随包分发。
   - 改为首次运行在本机用 `openssl` 现场生成，只存在于使用者自己的电脑上。
2. **重写 `启动脚本/0-首次使用-安装证书.bat`**
   - 不再校验预置的 `ca.crt`，改为调用 `程序/工具/mitm_debug_proxy.py --init` 生成并安装本机证书；
   - 增加 Python 探测、openssl 缺失时的可读报错与失败退出码。
3. **`程序/工具/mitm_debug_proxy.py`**
   - 新增 `_find_openssl()`：PATH 里没有时自动找 Git for Windows / OpenSSL 安装目录；
   - `_run()` 捕获 `FileNotFoundError`，把“找不到 openssl”变成中文提示而不是 traceback；
   - `install_ca()` 生成失败时返回 `False` 并打印原因；
   - `--init` 按安装结果返回 0 / 1，`0-首次使用-安装证书.bat` 才能正确区分成功与失败。
4. **`程序/selfcheck.py`**
   - 证书缺失从“硬性失败”改为提示项（首次使用本就应该没有证书）；
   - openssl 检测改用 `shutil.which` + 常见安装路径；
   - 横幅文案改为衍生版名称。
5. **许可证文件**
   - `程序/LICENSE` 原为“条款摘要与指针”，按 LRL-1.0 第二条第 1 款“再发布须附全文”替换为上游 LICENSE 原文全文（14506 字节，逐字未改）；
   - 在仓库根目录新增 `LICENSE`（同一份全文），供 GitHub 识别与展示。
6. **名称与示例**
   - 项目名由“公大跑 · 虚拟定位跑步包”改为中性的“校园跑协议研究 · 网页控制台”；
   - `示例配置/config-公大.json` 改名为 `示例配置/config-案例816.json`，内容不变（`school_id = 816` 作为案例值保留）；
   - 同步更新 `启动脚本/9-进阶-启动旧控制台8770.bat` 与说明书的引用。
7. **文档**
   - 重写 `README.md`：保留上游署名与仓库地址、声明非商业与非 OSI 开源、补充本机证书说明与发布自检；
   - 重新生成 `文档/使用说明书.docx` 与 `文档/使用说明.md`（同一内容源）：证书章节改为“本机现场生成”，
     删除“已预置 44 个叶证书”等表述，补充 openssl 依赖与新电脑清单；
   - 依据 LRL-1.0 第二条第 4 款，在衍生版自有文档（README / 说明书）中不再把上游作者 QQ 作为技术支持渠道，
     改为本仓库 Issues；上游声明文件原文中的联系方式未改动，以保持声明完整性。
   - 新增 `程序/README.md`：让 `lepao/license_guard.py` 的声明完整性自检不再报 “缺 README.md”。
8. **`.gitignore` 收紧**
   - 忽略 `程序/_private/*`（仅保留 `.gitkeep`）、`*.key` / `*.pem` / `*.csr` / `*.srl`，
     防止证书、会话、抓包明文被误提交。
9. **`程序/webapp/server.py`**
   - `save_session()` 增加 `os.makedirs`，避免删掉 `_private/` 后首次登录保存会话失败。
10. **网络健壮性（v2.3，本版重点）**
    - 抓包默认改为 **PAC 模式**：只把 `*.lptiyu.com` / `*.weixin.qq.com` / `*.servicewechat.com`
      导到 `127.0.0.1:8086`，其余域名 `DIRECT`。控制台新增 `GET /proxy.pac`，
      抓包启动器在 `127.0.0.1:8091` 自带一个 PAC 服务，不依赖控制台是否在线。
    - `webapp/server.py`：新增 `_capture_guard()` 看门狗（MITM 进程消失或端口连续 3 次不通即还原代理）；
      `capture_stop()` 改为四项全还原（`ProxyEnable/ProxyServer/ProxyOverride/AutoConfigURL`）并清理备份；
      `_read_proxy()` 支持 `AutoConfigURL`、改用 `split(None,2)` 解析、在 `reg.exe` 被拦时回退 `winreg`；
      `fix_stuck_proxy()` 改为「按备份还原 → 只清指向本机 8081/8086/8090 的残留 → 删本机 PAC」，
      不再无脑 `ProxyEnable=0`（老行为会把用户自己的 Clash / 公司代理一起关掉）。
    - `程序/工具/mitm_debug_proxy.py`：新增 `_find_openssl()`（PATH 里没有就找 Git / OpenSSL / msys2 常见路径）；
      `_restore_proxy_from_backup()` 同时还原 `ProxyOverride` 与 `AutoConfigURL` 并刷新 WinINET；
      `bind` 失败 / 证书生成失败给出可读中文错误与退出码 2；连接的客户端加 120 s 空闲超时，避免线程堆死端口。
    - `程序/工具/capture_launcher.py`：重写为「备份 → 起 MITM → 确认监听 → 才设代理」，默认 PAC，
      `--global` 走兼容的全局模式（写 `ProxyOverride` 排除本机/局域网），新增 MITM 存活看门狗。
    - 新增 `程序/工具/fix_network.py` 与 `启动脚本/6-一键修复网络.bat`：按备份还原原代理、
      关掉指向本机的代理、删残留 PAC、重置 WinHTTP、清 DNS，并把修复前后的注册表值都打印出来。
    - `启动脚本/1-启动网页控制台.bat`、`2-启动网页-局域网模式.bat`：删掉「启动即 `ProxyEnable=0`」那两行，
      改由 `server.py` 的 `fix_stuck_proxy()` 智能清理；`4-关闭系统代理-救急.bat` 改为调用 `fix_network.py`。
    - `程序/selfcheck.py`：代理检查读取四项（含 PAC）并区分「指向本机」与「用户自己的代理」，
      证书未受信从提示项改为硬性失败（否则 HTTPS 抓包必然失败）；
      修复 `PYTHONIOENCODING=gbk` 下打印 `✗` 触发的 `UnicodeEncodeError`。
    - 新增 `文档/网络故障排查.md`，README 增加「打开脚本后上不了网」排查表与 v2.3 机制说明。
11. **提交链健壮性（v2.4）**
    - `程序/webapp/index.html`：`api()` 统一加 `AbortController` 超时（提交 180 s，其它 30 s）与 `try/catch`，
      返回带 `timeout/net` 标记的失败对象；`doSubmit()` 期间禁用按钮、每秒显示已等待秒数、`finally` 复位，
      失败时展示 `stage` 与 `elapsed`，并提示「stop/review 阶段之前轨迹可能已上传成功，先去记录列表确认」。
    - 新增 `GET /api/netcheck` 与网页「网络自检」按钮：一次探测乐跑 API / 阿里云 OSS / 外网基线三路的
      DNS + TCP 可达性，并给出一句结论（换热点 / 避高峰 / 查 token）。
    - `程序/webapp/server.py`：`do_GET`/`do_POST` 外面包统一异常处理 `_fail()`，未捕获异常一律返回
      `{"ok":false,"error","stage","elapsed","hint"}` 的 JSON，不再出现「异常→直接断连接→前端永远显示提交中」；
      `/api/submit` 内加入 `_stage()` 阶段标记（precheck / before_run1 / before_run2 / timestamp / sts /
      upload / before_run3 / stop / review），控制台同步打印累计耗时。
    - `程序/webapp/lplib.py`：新增 `resolve_host()`（线程内跑 `getaddrinfo`，8 s 超时 + 300 s 缓存）与
      `tcp_probe()`；`call()` 与 `upload_track()` 先做带超时的预解析，把「DNS 卡死导致无限挂起」变成 8 秒内可读报错；
      `upload_track()` 网络异常自动重试 1 次（间隔 1 s）。
    - `文档/网络故障排查.md` 新增「提交一直卡在提交中」章节：成因、6~8 次串行请求与各自超时、校园网四种典型失败、提交前固定动作。

## 未修改 / 保留

- `程序/LICENSE.md`、`程序/NOTICE`、`程序/DISCLAIMER.md`、`程序/SECURITY.md`、`程序/CONTRIBUTING.md`
  以及每个源文件顶部的 `lepao-research-notice` 版权块均保留原文，未删除、未遮盖、未替换；
- `程序/lepao/_buildstamp.py` 构建标识保留，用于版本核对；
- 协议实现、轨迹引擎、抓证工具的逻辑未改动（仅上述 openssl 查找与错误提示）；
- 本仓库不包含：APK、录屏、真实 token / 学号 / 姓名 / 轨迹数据、任何代跑服务。
