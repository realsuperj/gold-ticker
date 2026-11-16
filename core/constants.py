"""常量定义与金融合规文案 — 统一自 shared/spec.json 加载 (core/constants.py)。"""
from __future__ import annotations

from core.product import load_spec

_SPEC = load_spec()
_LIMITS = _SPEC["limits"]

# 标的代码常量
SYMBOL_AU9999 = "au9999"
SYMBOL_ZS_JCJ = "zs_jcj"
SYMBOL_ICBC_JCJ = "icbc_jcj"
SYMBOL_CCB_JCJ = "ccb_jcj"
SYMBOL_XAU_USD = "xau_usd"

SUPPORTED_SYMBOLS = tuple(item["id"] for item in _SPEC["symbols"])

SYMBOL_META = {
    item["id"]: dict(item)
    for item in _SPEC["symbols"]
}

DEFAULT_BANK_SPREADS = {
    item["id"]: float(item["spread"])
    for item in _SPEC["symbols"]
    if float(item.get("spread", 0.0)) > 0
}

TROY_OUNCE_TO_GRAM = float(_LIMITS["troyOunceToGram"])
MIN_REFRESH_SECONDS = int(_LIMITS["minRefreshSeconds"])
DEFAULT_REFRESH_SECONDS = int(_LIMITS["defaultRefreshSeconds"])
COOL_DOWN_SECONDS = int(_LIMITS["coolDownSeconds"])
MAX_FAILURES_BEFORE_COOLDOWN = int(_LIMITS["maxFailuresBeforeCooldown"])

DISCLAIMER_CN = _SPEC["disclaimers"]["zh"]
DISCLAIMER_EN = _SPEC["disclaimers"]["en"]
