# 任务：从 iOS 设备备份中导出指定 App 的 SQLite 数据库

## 目标

在一台已连接 iPhone 的电脑上，导出 `com.lptiyu.tanke`（步道乐跑）App 的本地数据库，
并从中读取 `SCHOOL_LIST_INFO` 表的内容，输出为 JSON。

目标产物：一个 JSON 文件，包含该表全部行（学校 id + 名称 + 相关字段）。

## 背景

这是标准的 iOS 数据迁移 / App 数据取证流程：
iTunes 备份会把 App 的 `Documents/` 与 `Library/` 目录一并打包，其中包含 App 使用 greenDAO
生成的 SQLite 数据库。备份完成后通过 `Manifest.db` 的 `Files` 表即可按
`domain = 'AppDomain-com.lptiyu.tanke'` 与 `relativePath LIKE '%databases%'` 定位到具体文件。

不涉及越狱、不涉及解密用户数据（备份密码为空时备份不加密）、不涉及修改设备上的任何内容。
全程只读：备份是一份拷贝，手机上的 App 状态不会被改变。

## 前置条件

| 项目 | 要求 |
|---|---|
| 设备 | iPhone，已用数据线连接电脑，屏幕已解锁并点过「信任此电脑」 |
| 系统 | Windows / macOS / Linux 均可 |
| Windows 额外依赖 | 安装 Apple Mobile Device 驱动（装 iTunes 或「Apple 设备」应用即可获得） |
| Python | 3.9+ |
| 磁盘 | 至少 20 GB 空闲（全量备份体积取决于手机用量） |

设备是否连上，用这条命令确认：

```bash
python -m pymobiledevice3 usbmux list
```

能列出 UDID 即为连接成功。

## 执行步骤

### 1. 安装依赖

```bash
python -m pip install --upgrade pymobiledevice3
```

Windows 若报 `Could not find module '...Apple Mobile Device...'`，说明缺驱动，先装 iTunes。

### 2. 运行脚本

```bash
python extract_lepao_db.py --out ./lepao_backup --result ./school_list.json
```

脚本会完成：备份 → 定位 `Manifest.db` → 抽取目标 App 的数据库文件 → 读取表 → 写 JSON。

首次备份耗时较长（视手机数据量，10–40 分钟），后续可复用已有备份目录。

### 3. 交付产物

脚本结束后输出两个东西：

- `./school_list.json` —— `SCHOOL_LIST_INFO` 表的全部内容
- `./lepao_dbs/` —— 抽取出的原始 `.db` 文件（备查）

如果 `SCHOOL_LIST_INFO` 表为空，脚本会自动列出该 App 全部 `.db` 文件的表名清单，
换一张表即可。

## 预期输出格式

```json
{
  "db_file": "xxx.db",
  "table": "SCHOOL_LIST_INFO",
  "row_count": 512,
  "rows": [
    { "_id": 1, "SCHOOL_ID": 18, "SCHOOL_NAME": "...", "..." : "..." }
  ]
}
```

字段名以实际表结构为准，脚本会原样输出所有列。

## 故障排查

| 现象 | 处理 |
|---|---|
| `usbmux list` 为空 | 换数据线（要能传数据的，不是仅充电线）；重新点「信任此电脑」；Windows 检查设备管理器里是否有 Apple Mobile Device |
| 备份卡在 0% | 手机锁屏了，保持解锁；或换 USB 口（直连主板，别用 hub） |
| 备份提示需要密码 | 该设备此前设过加密备份。脚本不处理加密备份，需先在 iTunes/Finder 里取消「加密本地备份」并重新备份 |
| 找不到 `AppDomain-com.lptiyu.tanke` | App 未安装或从未启动过。先在手机上打开一次该 App |
| 找到 domain 但没有 databases 目录 | 该 App 把数据库放在了别的位置，脚本会回退到列出所有 `.sqlite` / `.db` / `.realm` 文件 |
| 表里没数据 | 先联网打开一次 App，让它在本地写入缓存，再重新备份 |

## 边界

- 只读取备份副本，不写入设备
- 不修改、不删除任何数据
- 备份文件仅用于本次提取，任务结束后可自行删除
