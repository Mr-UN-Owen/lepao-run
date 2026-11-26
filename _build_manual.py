# -*- coding: utf-8 -*-
"""生成《使用说明书》Word + 同内容 Markdown（单一内容源，避免两份漂移）。"""
import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

OUT_DIR = r"D:\YZX\校园跑\公大跑-虚拟定位跑步包\文档"
DOCX = os.path.join(OUT_DIR, "使用说明书.docx")
MD = os.path.join(OUT_DIR, "使用说明.md")

# ---------------------------------------------------------------- 内容定义
# 块类型：h1 h2 p b(要点) n(编号) table note key
BLOCKS = [
    ("title", "公大跑 · 虚拟定位跑步包  使用说明书"),
    ("subtitle", "网页控制台版 ｜ 站点 api3.lptiyu.com ｜ 中国人民公安大学 school_id = 816"),
    ("meta", [
        ("包名", "公大跑-虚拟定位跑步包"),
        ("适用系统", "Windows 10 / 11（64 位）"),
        ("运行依赖", "Python 3.8 及以上；电脑版微信；能打开「公大跑者」小程序"),
        ("主程序入口", "启动脚本\\1-启动网页控制台.bat → 浏览器 http://127.0.0.1:8780"),
        ("说明书版本", "v1.0（打包日 2026-11-25）"),
    ]),

    ("h1", "一、这个包是干什么的"),
    ("p", "一句话：不碰手机定位、不给微信装任何模块，直接在电脑上生成一条「真人形态」的跑步轨迹，"
          "通过平台自己的接口提交上去，成绩落在你的账号里。"),
    ("p", "为什么叫「虚拟定位」：位置数据确实是被「造」出来的，但造它的地方不是手机 GPS，而是电脑上的协议实现。"
          "小程序读定位走的是微信自己的定位通道，安卓上挂「模拟位置」应用基本无效，"
          "而 iOS 上改坐标又会因为缺少步频/速度曲线被判无效。本包绕开这一层，"
          "直接让服务端收到一条配速、步频、打卡点首通过都自洽的轨迹。"),
    ("h2", "包里有什么"),
    ("table", ["目录 / 文件", "作用", "你是否需要动它"], [
        ["程序\\webapp", "主程序：网页控制台（登录 / 看打卡点 / 生成轨迹 / 提交）", "不需要，双击 bat 即可"],
        ["程序\\lepao", "协议库：加密、指纹头、轨迹引擎、v3 接口封装", "不需要"],
        ["程序\\工具", "抓证工具：本机 MITM 代理、抓包启动器、域名嗅探", "不需要（网页按钮会调用）"],
        ["程序\\_private\\mitm_ca", "预置抓包根证书 + 44 个域名叶证书", "只在第 2 步安装一次"],
        ["程序\\selfcheck.py", "环境自检脚本", "由 5-环境自检.bat 调用"],
        ["程序\\app、程序\\cli.py", "进阶：旧版控制台（8770）与命令行流水线", "新手不用管，见第九章"],
        ["启动脚本\\", "7 个双击即用的 bat", "看下面第 3 章，按顺序点"],
        ["示例配置\\config-公大.json", "进阶用的 config.json 模板（已按公大改好 api3 / 3.02~3.20km）", "进阶才用"],
        ["文档\\", "本说明书、虚拟定位可行性评估", "随时可看"],
    ]),

    ("h1", "二、运行前检查（30 秒）"),
    ("table", ["项目", "要求", "怎么确认"], [
        ["操作系统", "Windows 10 / 11 64 位", "Win+R → 输入 winver → 回车"],
        ["Python", "3.8 或更高，且已加入 PATH", "Win+R → 输入 cmd → 回车 → 输入 python -V → 回车，能显示版本号即可"],
        ["微信", "电脑版已登录，能打开「公大跑者」小程序", "微信左侧小程序面板里能找到它"],
        ["网络", "能访问 api3.lptiyu.com", "浏览器打开 https://api3.lptiyu.com 有响应即可（报错页也算通）"],
        ["权限", "当前是普通用户即可，不需要管理员", "——"],
    ]),
    ("note", "不需要装：mitmproxy、pycryptodome、Fiddler、安卓 root、FakeLocation、爱思助手/AnyGo。"
             "这些要么用不上，要么本身就是本包要绕开的那条路。"),

    ("h1", "三、首次使用：按顺序做 6 步"),
    ("p", "下面每一步都写清了「双击哪个文件、点哪个按钮、按哪个键」。全部做完大约 5 分钟。"),

    ("h2", "第 1 步：解压（不要只解一半）"),
    ("n", "按 Win+E 打开「文件资源管理器」，找到收到的压缩包。"),
    ("n", "在压缩包上点鼠标右键 → 选「全部解压缩…」→ 点「提取」。"),
    ("n", "进入解压出来的文件夹，应当能看到 程序 / 启动脚本 / 文档 / 示例配置 这四个文件夹和 README.md。"),
    ("note", "不要放在 OneDrive、坚果云等同步目录里；也不要只把文件夹拖出来用（会丢 _private 里的证书）。"),

    ("h2", "第 2 步：安装抓包证书（只需一次）"),
    ("n", "进入「启动脚本」文件夹，双击 0-首次使用-安装证书.bat。"),
    ("n", "看到「安全警告」弹窗时，点弹窗里的【是】按钮（只点一次，装到当前用户，不需要管理员）。"),
    ("n", "黑窗口最后一行出现 [OK] 安装完成，即成功；按任意键关闭窗口。"),
    ("note", "如果提示「证书已经装过了」，说明之前装过，直接关掉窗口往下走。"),
    ("note", "为什么必须装：不装的话小程序不会把 HTTPS 交给本机代理解密，抓证会一直等到超时。"
             "装的是本包自带的 lepao-debug-ca，卸载方式见第六章最后一行。"),

    ("h2", "第 3 步：环境自检（确认这台电脑能跑）"),
    ("n", "双击 5-环境自检.bat。"),
    ("n", "看输出：每一行都应以 [OK] 开头；最后一行应是「结论：环境可用」。"),
    ("n", "如果有 [X] 行，按提示处理（最常见是没装 Python 或端口被占用），然后重新双击本文件。"),
    ("note", "自检会检查：Python 版本、核心库导入、加密后端、证书文件、证书是否已信任、openssl、"
             "8780 与 8086 端口、当前系统代理。"),

    ("h2", "第 4 步：启动网页控制台"),
    ("n", "双击 1-启动网页控制台.bat。"),
    ("n", "等 1~2 秒，默认浏览器会自动打开 http://127.0.0.1:8780，页面上是「乐跑控制台」登录框。"),
    ("n", "这个黑窗口就是服务本体：使用期间不要关；关掉它等于停止服务。"),
    ("note", "浏览器没自动打开：手动打开浏览器，在地址栏输入 127.0.0.1:8780 后按回车。"),

    ("h2", "第 5 步：一键抓凭证并登录（每天都要做）"),
    ("n", "在登录页点按钮「一键获取凭证（自动抓包）」。页面出现「抓包已就绪」字样。"),
    ("n", "按 Win+D 回到桌面，找到微信图标双击打开；如果微信已经开着，先在任务栏微信图标上点右键 → 选「退出」，再重新打开。"),
    ("n", "在微信左侧点小程序面板 → 打开「公大跑者」→ 进入跑步首页（能看到开始跑步/跑区那个页面）。"),
    ("n", "按 Alt+Tab 切回浏览器，等 3~15 秒：host / school_id / uid / token 四个框会自动填好，提示「凭证已填入上面的框」。"),
    ("n", "点按钮「登录」。页面切换到控制台，能看到学校、学期、本学期里程、跑区、打卡点坐标。"),
    ("note", "抓包期间不要在小程序里反复退出登录/重新进入，会把刚抓到的 token 顶掉。"),
    ("note", "页面 240 秒抓不到会自己停下并提示，此时系统代理已被自动还原，网络不会受影响。"),

    ("h2", "第 6 步：生成轨迹并提交"),
    ("n", "看右栏「生成与提交」：目标距离（公里）填 3.05 ；配速（秒/公里）填 310（= 5 分 10 秒/公里）。"),
    ("n", "点按钮「生成轨迹预览」。左侧地图出现蓝色轨迹线，地图上被经过的打卡点变绿并标出名字。"),
    ("n", "看按钮上方那行字，必须是「✓ 全部覆盖」。若是「✗ 有遗漏」，把距离改成 3.2 或把配速改成 300 再点一次「生成轨迹预览」。"),
    ("n", "点按钮「提交（实验性）」。弹出确认框，核对距离/用时/打卡点后点【确定】。"),
    ("n", "等右下角出现成功提示，下拉「跑步记录」面板，最新一条记录出现在列表里即完成。"),
    ("note", "提交前若页面提示「今天已经有 N 条【有效】记录」，说明今天已经打过卡，【提交】按钮会变灰——这是保护，不要去绕。"),

    ("h1", "四、每天重复使用的流程"),
    ("p", "首次装好之后，以后每天只有 3 步："),
    ("n", "双击 启动脚本\\1-启动网页控制台.bat（黑窗口别关）。"),
    ("n", "网页上点「一键获取凭证（自动抓包）」→ 打开微信「公大跑者」进跑步页 → 等自动填好 → 点「登录」。"),
    ("n", "点「生成轨迹预览」→ 确认「✓ 全部覆盖」→ 点「提交（实验性）」→ 弹窗点【确定】。"),
    ("key", "为什么每天都要重新抓：token 是「单会话消耗品」，提交完成即失效；小程序重新登录也会顶掉旧的。"
            "所以不要指望登录一次用一周。"),
    ("key", "每天只记 1 次有效成绩（服务端规则）：同一天重复提交不会多算，只多一条无效记录。"),

    ("h1", "五、参数怎么填（附服务端规则表）"),
    ("table", ["参数", "推荐值", "规则范围（服务端下发）", "说明"], [
        ["目标距离", "3.05 km", "3.00 ~ 20.00 km", "低于 3.00 直接判无效；取 3.0~3.2 最稳"],
        ["配速", "310 秒/公里", "3'00\" ~ 5'30\"（即 180~330 秒/公里）", "数字越小越快；310 属于中等偏慢，通过率高"],
        ["用时", "自动计算", "——", "= 距离 × 配速，页面预览里会显示"],
        ["打卡点", "自动选 2 个并覆盖", "每次随机 2 个，必须途经", "页面会标出「覆盖打卡点 12,18」这类编号"],
        ["时间窗", "自动", "06:00 ~ 22:00", "服务器按提交时刻判，夜里不要提交"],
        ["每日次数", "1 次", "min_num = 1", "提交成功即当日完成"],
    ]),
    ("note", "距离/配速都在页面上改：点输入框 → 按 Ctrl+A 全选 → 输入新数字 → 点「生成轨迹预览」重新生成即可。"),

    ("h1", "六、出错怎么办（照着查）"),
    ("table", ["现象", "原因", "按这个做"], [
        ["一直显示「抓取中」，240 秒后超时", "证书没装 / 装了但微信没重启", "双击 0-首次使用-安装证书.bat；微信任务栏右键「退出」后重开；再点一键获取"],
        ["提示「MITM 没起来，代理设置一个字都没动」", "8086 端口被占（上一个抓包窗口没关）", "关掉所有黑窗口；仍不行就重启电脑再试"],
        ["提示「自动改系统代理失败」", "权限不足或安全软件拦截注册表写入", "页面会给出「我已设好代理，开始抓包」按钮：先手动把 设置→网络和 Internet→代理 设为 127.0.0.1:8086，再点它"],
        ["登录报 [101]", "token 失效，或抓包时的出口与提交时不一致", "重新抓一次；抓包和提交期间不要开/关 VPN、Clash"],
        ["提交按钮是灰的、点不动", "轨迹没覆盖全部打卡点", "把距离改 3.2、配速改 300，重新点「生成轨迹预览」"],
        ["服务端判「速度过慢 / 跑步时间异常」", "配速或时间轴不在规则内", "配速填 300~320；距离 3.0~3.2；不要用 6 分以上的配速"],
        ["提交成功但记录里看不到 / 显示无效", "服务端异步复核", "等 5~10 分钟，按 F5 刷新记录列表再看"],
        ["浏览器、微信突然上不了网", "抓包窗口被强关，系统代理没还原", "双击 4-关闭系统代理-救急.bat"],
        ["网页打不开 / 一直转圈", "控制台黑窗口被关了", "重新双击 1-启动网页控制台.bat，再刷新页面（F5）"],
        ["双击 bat 黑窗口一闪就没了", "没装 Python，或装的时候没勾 Add to PATH", "装 Python 3.8+（勾选 Add python.exe to PATH），重开窗口，先跑 5-环境自检.bat"],
        ["想卸载证书", "——", "Win+R → 输入 certmgr.msc → 回车 → 受信任的根证书颁发机构 → 证书 → 找到 lepao-debug-ca → 右键删除"],
    ]),

    ("h1", "七、导入到其他电脑，功能还能生效吗"),
    ("p", "结论：能生效，但有 3 件事必须在新电脑上重做一次。代码、证书、参数都不含这台电脑的私有路径，"
          "换机器不用改任何文件。"),
    ("table", ["能力", "换电脑后", "为什么"], [
        ["网页控制台、轨迹生成、提交逻辑", "直接生效", "纯 Python 标准库实现，路径全相对，无盘符硬编码"],
        ["加密算法（AES-128-CBC / SignMD5）", "直接生效", "包内自带纯 Python AES，缺 pycryptodome 会自动回退"],
        ["抓证书（MITM 解密小程序 HTTPS）", "要重装一次证书", "证书按「当前用户」安装，存放在注册表/用户证书库，不随文件夹走"],
        ["抓 token", "要重新抓", "token 是与会话、出口绑定的消耗品，不能拷来用"],
        ["已预置的 44 个域名叶证书", "直接生效", "已随包带走，所以新电脑没装 openssl 也能抓"],
        ["config.json / 会话缓存", "不会带过去（也不该带）", "含真实 token，已列入 .gitignore"],
        ["bat 启动脚本", "直接生效", "已改为自动探测 py / python / python3，不再写死解释器路径"],
        ["手机端虚拟定位（安卓 Hook 等）", "不在本包内", "本包走协议路线，不依赖手机改定位"],
    ]),
    ("h2", "新电脑上的操作顺序（4 步）"),
    ("n", "装 Python 3.8+，安装界面勾选 Add python.exe to PATH。"),
    ("n", "把整个文件夹拷过去（U 盘 / 网盘都行），路径别太深、别含特殊符号。"),
    ("n", "双击 启动脚本\\5-环境自检.bat，确认全绿。"),
    ("n", "双击 0-首次使用-安装证书.bat 装证书 → 双击 1-启动网页控制台.bat → 重新抓一次凭证登录。"),
    ("h2", "什么情况下会失效"),
    ("b", "平台改了接口或换了域名：需要在 程序\\webapp\\lplib.py 里改 host/签名逻辑（一般用户不用管，先跑自检看域名是否还通）。"),
    ("b", "学校换了打卡规则（比如要求 3.5km 或加人脸）：页面参数跟着服务端下发变，按第五章的表调整即可。"),
    ("b", "电脑上没有 Python，或装的是 Microsoft Store 版 Python（会出现假 python.exe 别名）：改用官网安装包。"),
    ("b", "公司/学校网络强制走代理或做了 TLS 拦截：抓证会失败，换手机热点再试。"),

    ("h1", "八、包内目录说明"),
    ("table", ["路径", "说明"], [
        ["程序\\webapp\\server.py", "网页控制台后端（端口 8780）：登录、档案、预览、提交"],
        ["程序\\webapp\\lplib.py", "v3 协议客户端：加密请求、解密响应、轨迹组装"],
        ["程序\\webapp\\index.html", "单页前端：登录框、地图、记录列表、提交按钮"],
        ["程序\\lepao\\", "协议库：crypto / aes / transport / track / record / pipeline / v3api …"],
        ["程序\\工具\\mitm_debug_proxy.py", "零依赖 MITM 代理：本机解密小程序 HTTPS，落盘 capture_log.jsonl"],
        ["程序\\工具\\capture_launcher.py", "命令行抓包启动器：先起代理确认监听，再改系统代理，退出必还原"],
        ["程序\\_private\\", "运行时目录：会话缓存、抓包明文（含真实 token，勿外发）"],
        ["程序\\app\\、程序\\cli.py", "进阶：旧版控制台与命令行流水线（需自备 config.json）"],
        ["示例配置\\config-公大.json", "进阶用配置：api3.lptiyu.com、3.02~3.20km、配速 200~330"],
    ]),

    ("h1", "九、进阶用法（可选，新手跳过）"),
    ("p", "命令行流水线（需要先复制配置）：把 示例配置\\config-公大.json 复制到 程序\\config.json，然后："),
    ("code", "cd /d 程序\npython cli.py account add 张三 2023xxxxxx --alias 张三    注册成员（= 抓证白名单）\npython cli.py capture --member 张三                        抓 token\npython cli.py build  --member 张三                         干跑（零写入）\npython cli.py submit --member 张三                         真提交\npython cli.py watch  <record_id> --member 张三             复核"),
    ("p", "旧版控制台：双击 启动脚本\\9-进阶-启动旧控制台8770.bat，服务起来后浏览器打开 127.0.0.1:8770。"),
    ("p", "局域网模式：双击 启动脚本\\2-启动网页-局域网模式.bat，手机在同一 WiFi 下可用局域网地址打开（无密码，仅限自家网络）。"),

    ("h1", "十、安全、数据与声明"),
    ("b", "只给自己或已明确同意的同学打卡；不要把 token、capture_log.jsonl 发给任何人，等同交出账号。"),
    ("b", "程序只和 api3.lptiyu.com 通信，不上传任何第三方；数据只写在本机 程序\\_private\\。"),
    ("b", "抓包证书 lepao-debug-ca 只用于本机调试，含私钥，不要外传；不用了按第六章最后一行卸载。"),
    ("b", "本包跟随上游 LRL-1.0 许可：仅供学习研究、不可牟利、再发布须署名引用原始仓库 "
          "https://github.com/dan-cun/lepao3 并保留全部声明文件（程序\\LICENSE、NOTICE、DISCLAIMER.md 等）。"),
    ("b", "按「现状」提供，不保证打卡必然有效；账号限制、成绩作废等后果由使用者承担。服务端判定为准。"),

    ("h1", "附：一次提交在后台发生了什么（技术向）"),
    ("p", "1) beforeRunV260：拿学期、跑区、打卡点坐标、当日额度、参数规则表（时间窗/里程/配速/打卡点数）。"),
    ("p", "2) 本机生成轨迹：按跑区几何 + 随机 2 个打卡点合成环线，配速恒定，步频分桶，首点/末点时间轴包住起止时刻。"),
    ("p", "3) 上传轨迹文件到 OSS（STS 临时凭证），拿到文件地址。"),
    ("p", "4) Run/stopRunV278：提交跑区模式的记录（必须用跑区接口，自由跑接口不计成绩）。"),
    ("p", "5) 服务端复核：校验 里程 → 配速 → 时间轴 → 打卡点首通过 → 每日唯一；通过后记录 status = 有效。"),
    ("note", "校验顺序决定了报错顺序：配速不合格时只会报「速度过慢」，只有配速过了才会暴露时间轴问题。"
             "所以先修配速，再看时间。"),
]

# ---------------------------------------------------------------- 文档工具
CN_FONT = "微软雅黑"


def set_run_font(run, size=None, bold=None, color=None, font=CN_FONT):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    el = OxmlElement("w:shd")
    el.set(qn("w:val"), "clear")
    el.set(qn("w:fill"), hex_color)
    tc_pr.append(el)


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    tr_pr.append(el)


def add_table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    no_split(t.rows[0])
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        r = p.add_run(h)
        set_run_font(r, 9.5, True, "FFFFFF")
        shade(hdr[i], "2F5597")
    for row in rows:
        cells = t.add_row().cells
        no_split(t.rows[-1])
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            r = p.add_run(str(v))
            set_run_font(r, 9)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def build_docx():
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.2)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.4)

    style = doc.styles["Normal"]
    style.font.name = CN_FONT
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    style.paragraph_format.space_after = Pt(4)
    style.paragraph_format.line_spacing = 1.25

    step = 0
    for block in BLOCKS:
        kind = block[0]
        if kind in ("h1", "h2"):
            step = 0
        if kind == "title":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(24)
            p.paragraph_format.space_after = Pt(6)
            set_run_font(p.add_run(block[1]), 22, True, "1F3864")
        elif kind == "subtitle":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(18)
            set_run_font(p.add_run(block[1]), 10.5, False, "44546A")
        elif kind == "meta":
            add_table(doc, ["项目", "内容"], block[1], widths=[4.0, 12.0])
        elif kind == "h1":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(16)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(block[1]), 15, True, "1F3864")
            pPr = p._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "8")
            bottom.set(qn("w:color"), "B4C6E7")
            bdr.append(bottom)
            pPr.append(bdr)
        elif kind == "h2":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(block[1]), 12, True, "2F5597")
        elif kind == "p":
            p = doc.add_paragraph()
            p.paragraph_format.first_line_indent = Pt(21)
            set_run_font(p.add_run(block[1]), 10.5)
        elif kind == "n":
            step += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.0)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            p.paragraph_format.space_after = Pt(3)
            set_run_font(p.add_run(f"{step})  "), 10.5, True, "2F5597")
            set_run_font(p.add_run(block[1]), 10.5)
        elif kind == "b":
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(3)
            set_run_font(p.add_run(block[1]), 10.5)
        elif kind == "note":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            set_run_font(p.add_run("提示｜"), 9.5, True, "C55A11")
            set_run_font(p.add_run(block[1]), 9.5, False, "7F6000")
        elif kind == "key":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(6)
            set_run_font(p.add_run("要点｜"), 9.5, True, "C00000")
            set_run_font(p.add_run(block[1]), 9.5, False, "833C0B")
        elif kind == "table":
            _, headers, rows = block
            add_table(doc, headers, rows)
        elif kind == "code":
            for line in block[1].split("\n"):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.8)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                r = p.add_run(line)
                set_run_font(r, 9, False, "203864", font="Consolas")
            doc.add_paragraph()

    doc.save(DOCX)
    return DOCX


def build_md():
    out = []
    for block in BLOCKS:
        kind = block[0]
        if kind == "title":
            out.append(f"# {block[1]}\n")
        elif kind == "subtitle":
            out.append(f"*{block[1]}*\n")
        elif kind == "meta":
            out.append("| 项目 | 内容 |")
            out.append("|---|---|")
            for k, v in block[1]:
                out.append(f"| {k} | {v} |")
            out.append("")
        elif kind == "h1":
            out.append(f"\n## {block[1]}\n")
        elif kind == "h2":
            out.append(f"\n### {block[1]}\n")
        elif kind == "p":
            out.append(f"{block[1]}\n")
        elif kind == "n":
            out.append(f"1. {block[1]}")
        elif kind == "b":
            out.append(f"- {block[1]}")
        elif kind == "note":
            out.append(f"> **提示**：{block[1]}\n")
        elif kind == "key":
            out.append(f"> **要点**：{block[1]}\n")
        elif kind == "table":
            _, headers, rows = block
            out.append("| " + " | ".join(headers) + " |")
            out.append("|" + "---|" * len(headers))
            for row in rows:
                out.append("| " + " | ".join(str(c) for c in row) + " |")
            out.append("")
        elif kind == "code":
            out.append("```bat")
            out.append(block[1])
            out.append("```\n")
    with open(MD, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return MD


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    print("DOCX:", build_docx())
    print("MD  :", build_md())
