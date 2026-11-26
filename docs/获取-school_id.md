# 取 school_id：反查为什么失败，以及 3 分钟抓包流程

> 结论：`school_id` 拿不到**不是学号的问题**，是几条反查通道本身没有数据。
> 唯一稳定的获取方式是抓一次小程序流量，然后本地解密看明文——工具已经备好。

---

## 一、反查通道实测矩阵（2026-11-24）

| # | 通道 | 请求 | 结果 | 判定 |
|---|---|---|---|---|
| 1 | lerun 学号反查 | `POST lerun.lptiyu.com/setting.php/index/getUserSchool` `username=<学号>` | `{"code":0,"msg":"no school"}` | **接口无效**：换北邮样例学号、随机学号同样返回 `no school`；参数名错误时才回 `username error` |
| 2 | H5 面学校接口 | `.../index/Login/getSchoolList` `/getUserSchool` `/getSchool` | HTTP 404 | 方法不存在（H5 面只开 getToken/verify/login） |
| 3 | v3 公开口 | `WpLogin/getSchoolInfo` 空参数 | `参数错误` | 参数校验在前 |
| 4 | v3 公开口 | 同上，带 `school_id` = 1 / 2 / 798 | 全部 `系统错误` | 接口已下线（任何 id 都报错） |
| 5 | v3 学校接口 | `School/nearbySchool`、`School/getSchoolList`、`Login/getSchoolList` | `101 登录信息失效` | 需要 token，登录前不可用 |
| 6 | 子域枚举 | `*.ppsuc.edu.cn`(29) + `*.lptiyu.com`(16) | 只解析出 `www`/`jwc`/`wp`/`api4` | 没有体育/白标站点暴露 |
| 7 | 备用节点 | `wp.lptiyu.com` / `api4.lptiyu.com` | 超时 / 404 | 不对外提供 v3 |

第 1 条是决定性的：接口活着（能区分 `username error` 与 `no school`），但**对所有学号都说没学校**，
说明这个站点的用户表没有数据（`lerun` 是「首次设置密码」用的新站，不是主库）。

---

## 二、3 分钟抓包流程（Windows，零代码）

小程序登录前一定会把 `school_id` 放进请求里，`beforeRunV260` / `loginByCode` 的密文解开就是明文。

### 步骤

1. 装 [Reqable](https://reqable.com/)（Windows 版，免费够用），启动后它会自动把系统代理指到 `127.0.0.1:9000`。
2. Reqable 里点「安装证书」→ 装到 **Windows 受信任根**（它有一键按钮）。
3. 打开 **电脑微信**，进入「公大跑者」小程序，走到跑步首页 / 点一次「开始跑步」。
4. 回到 Reqable，按 `Host` 过滤 `lptiyu` 或看 `POST` 请求；找到 body 形如
   `ostype=5&data=<一长串 base64>` 的那条。
5. 右键该请求 → **Copy as cURL** 或直接复制 body，粘到下面。

### 解密

```bash
# 方式 A：直接粘 body
python 工具/decrypt_v3_blob.py --data "ostype=5&data=xxxxxxxx"

# 方式 B：把 Reqable 导出的 .har / 复制的整段文本存成 capture.txt
python 工具/decrypt_v3_blob.py --file capture.txt

# 方式 C：管道
type capture.txt | python 工具/decrypt_v3_blob.py
```

输出会直接把 `school_id / uid / token / student_num` 单独列出来：

```
--- 关键字段 ---
  school_id    = 798
  uid          = 2000123
  token        = abcd1234…WXYZ（64 位）
  student_num  = STUDENT_NUM
```

> 工具不联网、不上传，纯本地 AES 解密（`lepao.crypto`，与小程序同算法）。

### 抓不到 HTTPS 的排查

| 现象 | 原因 |
|---|---|
| Reqable 里全是 `Tunnel` 看不到 body | 根证书没装进「受信任的根证书颁发机构」 |
| 小程序转圈打不开 | 微信对小程序的证书校验更严；先在微信设置里退出小程序再重进，或改用「手机 + Reqable」 |
| 只看到 `servicewechat.com` | 那是小程序框架包，业务请求在 `lptiyu.com` 或学校域名下，按 `POST` 过滤 |

手机抓包同理：Android 装 Reqable → 证书装到「用户证书」不够，需 Magisk 模块把用户证书转系统证书；
iOS 装描述文件 + 在「关于本机 → 证书信任设置」里打开完全信任。

---

## 三、拿到之后填哪里

```bash
# 1) 控制台里登录（左栏「网页账号登录」）
school_id = <刚拿到的>
账号       = <学号或邮箱>
密码       = <平台密码>
验证码     = <看图输入>

# 2) 或者命令行抓号（拿到 token 后连抓号都省了）
python cli.py set-token --member <名字> --token <解出来的 token>
```

拿到 `school_id` 后我这边能立刻做的事：

1. 用 H5 链跑一次真实登录（验证码人眼过），确认账号体系是学号还是邮箱；
2. 登录成功后探 `Offline/index`，把线下补录的字段摸出来；
3. 把「网页登录 → 补录一条记录」做成控制台上的按钮。
