"""常量定义与金融合规文案 (core/constants.py)。"""
from __future__ import annotations

# 标的代码常量
SYMBOL_AU9999 = "au9999"      # 上海黄金交易所 Au99.99 现货基准
SYMBOL_ZS_JCJ = "zs_jcj"      # 浙商银行积存金 (官方直连接口)
SYMBOL_ICBC_JCJ = "icbc_jcj"  # 工商银行积存金 (基准点差估算)
SYMBOL_CCB_JCJ = "ccb_jcj"    # 建设银行积存金 (基准点差估算)
SYMBOL_XAU_USD = "xau_usd"    # 伦敦金现货 (国际标的)

SUPPORTED_SYMBOLS = (
    SYMBOL_AU9999,
    SYMBOL_ZS_JCJ,
    SYMBOL_ICBC_JCJ,
    SYMBOL_CCB_JCJ,
    SYMBOL_XAU_USD,
)

# 标的元数据定义
SYMBOL_META = {
    SYMBOL_AU9999: {
        "id": SYMBOL_AU9999,
        "name_cn": "上金所 Au99.99",
        "name_en": "SGE Au99.99",
        "market": "cn",
        "unit_cn": "元/克",
        "unit_en": "CNY/g",
        "prefix_cn": "金",
        "prefix_en": "Au",
        "is_estimated": False,
    },
    SYMBOL_ZS_JCJ: {
        "id": SYMBOL_ZS_JCJ,
        "name_cn": "浙商银行积存金",
        "name_en": "Zheshang Gold",
        "market": "cn",
        "unit_cn": "元/克",
        "unit_en": "CNY/g",
        "prefix_cn": "金",
        "prefix_en": "Au",
        "is_estimated": False,
    },
    SYMBOL_ICBC_JCJ: {
        "id": SYMBOL_ICBC_JCJ,
        "name_cn": "工商银行积存金",
        "name_en": "ICBC Gold",
        "market": "cn",
        "unit_cn": "元/克",
        "unit_en": "CNY/g",
        "prefix_cn": "金",
        "prefix_en": "Au",
        "is_estimated": True,
    },
    SYMBOL_CCB_JCJ: {
        "id": SYMBOL_CCB_JCJ,
        "name_cn": "建设银行积存金",
        "name_en": "CCB Gold",
        "market": "cn",
        "unit_cn": "元/克",
        "unit_en": "CNY/g",
        "prefix_cn": "金",
        "prefix_en": "Au",
        "is_estimated": True,
    },
    SYMBOL_XAU_USD: {
        "id": SYMBOL_XAU_USD,
        "name_cn": "伦敦金现货 (XAU)",
        "name_en": "XAU/USD Spot",
        "market": "intl",
        "unit_cn": "美元/盎司",
        "unit_en": "USD/oz",
        "prefix_cn": "金",
        "prefix_en": "Au",
        "is_estimated": False,
    },
}

# 商业银行积存金常规估算点差 (元/克，基于上金所 Au99.99 基准价浮动)
DEFAULT_BANK_SPREADS = {
    SYMBOL_ICBC_JCJ: 0.80,   # 工商银行积存金常规点差预设
    SYMBOL_CCB_JCJ: 0.75,    # 建设银行积存金常规点差预设
}

# 黄金计量衡制换算常量 (1 金衡盎司 troy ounce = 31.1034768 克)
TROY_OUNCE_TO_GRAM = 31.1034768

# 轮询与容灾约束 (秒)
MIN_REFRESH_SECONDS = 10     # 严守合规底线，最小轮询间隔必须 >= 10 秒
DEFAULT_REFRESH_SECONDS = 10
COOL_DOWN_SECONDS = 180      # 单数据源连续故障时的冷却时间窗口 (秒)
MAX_FAILURES_BEFORE_COOLDOWN = 2

# 金融合规免责声明
DISCLAIMER_CN = (
    "【免责声明】本软件仅供个人行情参考与学习交流，不构成任何投资建议或交易依据。"
    "积存金价格基于基准行情或常规点差估算，遇极端行情或非交易时段，银行可能调整点差，实际成交以各银行客户端为准。"
    "数据来源于公开公共网络接口，存在网络传输延迟，据此操作风险自担。"
)

DISCLAIMER_EN = (
    "[Disclaimer] This software is for personal market tracking and educational purposes only, "
    "and does not constitute investment advice or trading recommendation. "
    "Data is fetched from public endpoints with potential latency. Use at your own risk."
)
