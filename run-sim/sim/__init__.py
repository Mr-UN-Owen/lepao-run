# -*- coding: utf-8 -*-
"""run-sim.sim —— 北邮校园跑模拟台的服务端内核。

分层（自下而上，只允许上层调下层）：
    geo        地理原语
    catalog    站点数据（校区/跑区/打卡点/策略）
    engine     轨迹生成引擎（可注册）
    validate   预检规则（可注册）
    exporters  导出器（可注册）
    submit     提交适配器（可注册，v0.1 仅 dry-run）
    store      本地记录库
"""
__version__ = "0.2.0"
