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

## 未修改 / 保留

- `程序/LICENSE.md`、`程序/NOTICE`、`程序/DISCLAIMER.md`、`程序/SECURITY.md`、`程序/CONTRIBUTING.md`
  以及每个源文件顶部的 `lepao-research-notice` 版权块均保留原文，未删除、未遮盖、未替换；
- `程序/lepao/_buildstamp.py` 构建标识保留，用于版本核对；
- 协议实现、轨迹引擎、抓证工具的逻辑未改动（仅上述 openssl 查找与错误提示）；
- 本仓库不包含：APK、录屏、真实 token / 学号 / 姓名 / 轨迹数据、任何代跑服务。
