# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao —— 乐跑(lptiyu)小程序协议研究库

分层:
  crypto     算法层   AES-128-CBC + SignMD5 + random6
  transport  传输层   真机指纹头组 + 出口绑定链(CONNECT 隧道) + 响应解码
  v3api      主 API   加密 POST → 解密响应 + 端点封装
  accounts   成员表   config v2 注册表(白名单/身份归位/策略合并)
  auth       生命周期 成员级 token=单活动会话消耗品
  capture    抓号      ProxyGuard + mitm 起停 + 等新 token + 归位
  track      轨迹引擎  template(真人模板反指纹) + math(备用) + log/step
  record     文件/OSS 命名仿真 + STS multipart 上传
  pipeline   流水线   真门→跑区→额度→时间→轨迹→[dry]→OSS→stopRun→复核
  state      证据链   dry-run/提交/复核 落盘
  h5api      H5 面     token+session 双通道; 登录链(可选 ddddocr)
  certctl    证书       mitmproxy 根证书体检/安装
  wechat_ctl 微信       进程查找/退出（仅进程级, 不读写微信数据）
  license    LRL-1.0   声明完整性自检与署名输出

注意: 本库不含网络回传代码; 凭证与轨迹仅存本机。
"""
__version__ = "2.2.0"
__license__ = "LRL-1.0"
__author__ = "dan-cun"
__repo__ = "https://github.com/dan-cun/lepao3"

__all__ = [
    "crypto", "transport", "v3api", "accounts", "auth", "capture",
    "track", "record", "pipeline", "state", "h5api", "certctl",
    "wechat_ctl", "license_guard",
]
