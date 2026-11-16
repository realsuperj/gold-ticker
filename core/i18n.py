# -*- coding: utf-8 -*-
"""GoldTicker 国际化 (i18n) 模块 — 词条统一自 shared/spec.json 加载。"""
from __future__ import annotations

import locale
import os

from core.product import load_spec

DEFAULT_LANGUAGE = "auto"
TRANSLATIONS = load_spec()["i18n"]


def ticker_prefix(config) -> str:
    return "金" if resolve_language(config.get("language", "auto")) == "zh" else "Au"


def detect_system_language() -> str:
    """检测当前操作系统语言，返回 'zh' 或 'en'"""
    try:
        lang = os.environ.get("LANG") or os.environ.get("LC_ALL") or ""
        if not lang:
            loc, _ = locale.getdefaultlocale()
            lang = loc or ""
        lang = lang.lower()
        if "zh" in lang or "chinese" in lang:
            return "zh"
    except Exception:
        pass
    return "en"


def resolve_language(lang_setting: str) -> str:
    """将配置项解析为具体的语言代码 ('zh' 或 'en')"""
    s = str(lang_setting or "auto").lower()
    if s in ("zh", "cn", "zh_cn", "zh-cn", "chinese"):
        return "zh"
    if s in ("en", "english", "us", "uk"):
        return "en"
    return detect_system_language()


def t(key: str, lang: str = "auto", **kwargs) -> str:
    """获取指定 key 的多语言文本"""
    resolved_lang = resolve_language(lang)
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    text = entry.get(resolved_lang) or entry.get("zh") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            pass
    return text
