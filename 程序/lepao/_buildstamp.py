# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao._buildstamp —— 构建标识（LRL-1.0 第十一条）

刻意入库: 它是"这是哪次构建"的证据, 也是比对"去了声明的副本"的依据。
`py -3 tools/apply_headers.py --stamp` 会重写本文件; 请勿手工编辑 BUILD_ID。
"""

BUILD_ID = "2.2.0-01bd7da4db"
BUILD_TIME = "2026-11-24T06:48:09Z"
VERSION = "2.2.0"
SOURCE = "https://github.com/dan-cun/lepao3"
LICENSE_ID = "LRL-1.0"


def as_dict():
    return {
        "build_id": BUILD_ID,
        "build_time": BUILD_TIME,
        "version": VERSION,
        "source": SOURCE,
        "license": LICENSE_ID,
    }


def describe():
    return (f"乐跑协议研究 v{VERSION} · build {BUILD_ID} ({BUILD_TIME})\n"
            f"源码 {SOURCE} · 许可证 {LICENSE_ID}（仅供学习 · 不可牟利 · 再发布须署名引用）")
