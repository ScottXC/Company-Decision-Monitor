from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventDefinition:
    event_type: str
    display_name_zh: str
    materiality_weight: int
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]


EVENT_DEFINITIONS: dict[str, EventDefinition] = {
    "merger_acquisition": EventDefinition("merger_acquisition", "并购收购", 92, ("收购", "并购", "合并", "重大资产重组", "购买资产"), ("acquisition", "merger", "business combination", "acquire")),
    "asset_sale": EventDefinition("asset_sale", "资产出售", 78, ("出售资产", "资产出售", "转让资产", "剥离资产"), ("asset sale", "divestiture", "sell assets", "disposed of")),
    "control_change": EventDefinition("control_change", "控制权变更", 94, ("控股股东变更", "实际控制人变更", "控制权变更", "易主"), ("change of control", "controlling shareholder changed")),
    "equity_change": EventDefinition("equity_change", "权益变动", 72, ("权益变动", "持股比例变动", "增持", "减持"), ("equity interest change", "shareholding change", "stake increased", "stake reduced")),
    "financing": EventDefinition("financing", "融资", 76, ("定向增发", "发行股份", "可转债", "融资", "配股"), ("private placement", "convertible bond", "financing", "rights issue")),
    "buyback": EventDefinition("buyback", "股份回购", 70, ("回购", "股份回购", "股票回购"), ("buyback", "share repurchase", "repurchase program")),
    "dividend": EventDefinition("dividend", "分红派息", 65, ("分红", "派息", "利润分配", "现金红利"), ("dividend", "cash distribution")),
    "executive_change": EventDefinition("executive_change", "高管变动", 88, ("董事长辞职", "总经理辞职", "高管辞职", "聘任总经理", "首席执行官变更"), ("ceo resigned", "cfo resigned", "management change", "chief executive officer resigned")),
    "board_change": EventDefinition("board_change", "董事会变动", 74, ("董事辞职", "董事会换届", "董事任命", "独立董事辞职"), ("board appointment", "director resigned", "board change")),
    "strategic_partnership": EventDefinition("strategic_partnership", "战略合作", 68, ("战略合作", "战略协议", "合作框架协议"), ("strategic partnership", "strategic agreement", "collaboration agreement")),
    "major_contract": EventDefinition("major_contract", "重大合同", 72, ("重大合同", "签署合同", "中标", "重大订单"), ("major contract", "material contract", "won a contract", "purchase order")),
    "business_exit": EventDefinition("business_exit", "业务退出", 66, ("退出业务", "终止经营", "关闭工厂", "停止生产"), ("business exit", "cease operations", "shut down", "exit the business")),
    "new_business": EventDefinition("new_business", "新业务", 55, ("新业务", "进入新领域", "新产品线", "开展业务"), ("new business", "new product line", "entered a new market")),
    "capex_project": EventDefinition("capex_project", "资本开支项目", 62, ("投资建设", "扩产项目", "产能建设", "资本开支"), ("capex project", "capacity expansion", "new facility")),
    "earnings_warning": EventDefinition("earnings_warning", "业绩预警", 86, ("业绩预告", "盈利警告", "业绩修正", "亏损预告"), ("earnings warning", "profit warning", "guidance update")),
    "accounting_restatement": EventDefinition("accounting_restatement", "会计重述", 90, ("会计差错", "财务重述", "前期差错更正", "会计估计变更"), ("restatement", "accounting error", "financial statements should no longer be relied upon")),
    "regulatory_investigation": EventDefinition("regulatory_investigation", "监管调查", 90, ("立案调查", "监管调查", "调查通知书", "涉嫌违法违规"), ("regulatory investigation", "under investigation", "investigation notice")),
    "regulatory_penalty": EventDefinition("regulatory_penalty", "监管处罚", 88, ("行政处罚", "监管函", "问询函", "处罚决定书"), ("penalty", "sanction", "enforcement action", "regulatory letter")),
    "litigation": EventDefinition("litigation", "重大诉讼", 78, ("重大诉讼", "仲裁", "起诉", "诉讼事项"), ("litigation", "lawsuit", "arbitration", "legal proceeding")),
    "bankruptcy": EventDefinition("bankruptcy", "破产重整", 96, ("破产", "重整", "清算", "破产申请"), ("bankruptcy", "chapter 11", "restructuring proceeding", "insolvency")),
    "debt_default": EventDefinition("debt_default", "债务违约", 94, ("债务违约", "未能兑付", "逾期债务", "债券违约"), ("debt default", "defaulted", "failed to pay", "missed payment")),
    "product_approval": EventDefinition("product_approval", "产品获批", 70, ("产品获批", "注册批准", "取得批件", "上市许可"), ("product approval", "approved by", "marketing authorization")),
    "product_recall": EventDefinition("product_recall", "产品召回", 76, ("产品召回", "召回产品", "质量缺陷"), ("product recall", "recall of", "safety recall")),
    "cybersecurity_incident": EventDefinition("cybersecurity_incident", "网络安全事件", 86, ("网络安全事件", "数据泄露", "信息泄露", "系统被攻击"), ("cybersecurity incident", "data breach", "ransomware", "security incident")),
    "supply_chain_disruption": EventDefinition("supply_chain_disruption", "供应链中断", 58, ("供应链中断", "停供", "供应短缺", "物流受阻"), ("supply chain disruption", "supplier disruption", "shortage")),
}

EVENT_TYPES = tuple(EVENT_DEFINITIONS.keys())

STATUS_DISPLAY_ZH = {
    "rumored": "传闻",
    "proposed": "拟议",
    "board_approved": "董事会通过",
    "shareholder_approved": "股东大会通过",
    "announced": "已公告",
    "completed": "已完成",
    "terminated": "已终止",
    "denied": "已否认",
    "unknown": "未知",
}

STATUS_PATTERNS: dict[str, tuple[str, ...]] = {
    "denied": ("否认", "denied", "refuted"),
    "terminated": ("终止", "取消", "terminated", "cancelled", "canceled"),
    "completed": ("完成", "completed", "closed the transaction"),
    "shareholder_approved": ("股东大会审议通过", "shareholders approved"),
    "board_approved": ("董事会审议通过", "board approved"),
    "proposed": ("拟", "计划", "proposes", "intends to", "proposal"),
    "rumored": ("传闻", "据报道", "reportedly", "sources said"),
    "announced": ("公告", "announced", "disclosed"),
}
