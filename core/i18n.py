# -*- coding: utf-8 -*-
"""
GoldTicker 国际化 (i18n) 字典与解析模块
支持简体中文 (zh) 与英文 (en)，支持跟随操作系统语言 (auto)。
"""
import locale
import os
import sys

DEFAULT_LANGUAGE = "auto"

TRANSLATIONS = {
    # 指标标签
    "prev_close": {"zh": "昨收", "en": "Prev"},
    "open_price": {"zh": "今开", "en": "Open"},
    "high": {"zh": "最高", "en": "High"},
    "low": {"zh": "最低", "en": "Low"},
    "time": {"zh": "时间", "en": "Time"},
    "chart_accumulating": {"zh": "今日走势累积中", "en": "Accumulating trend data..."},

    # 单位与点差标识
    "unit_cny_g": {"zh": "元/克", "en": "CNY/g"},
    "unit_usd_oz": {"zh": "美元/盎司", "en": "USD/oz"},
    "estimated_spread": {"zh": "点差估算", "en": "Estimated Spread"},

    # 标的名称
    "sym_au9999": {"zh": "上海黄金交易所 · Au99.99", "en": "SGE · Spot Au99.99"},
    "sym_xau_usd": {"zh": "国际现货黄金 · XAU/USD", "en": "Spot Gold · XAU/USD"},
    "sym_zs_jcj": {"zh": "浙商银行 · 积存金", "en": "CZBank · Gold Accumulation"},
    "sym_icbc_jcj": {"zh": "工商银行 · 积存金", "en": "ICBC · Gold Accumulation"},
    "sym_ccb_jcj": {"zh": "建设银行 · 积存金", "en": "CCB · Gold Accumulation"},

    # 菜单：标的
    "menu_targets": {"zh": "标的切换", "en": "Select Target"},

    # 菜单：视图入口与图表
    "menu_view_entry": {"zh": "视图入口", "en": "View Entry"},
    "menu_show_desktop": {"zh": "显示到桌面", "en": "Show on Desktop"},
    "menu_show_tray": {"zh": "显示到状态栏/托盘", "en": "Show on Menu Bar / Tray"},
    "menu_show_chart": {"zh": "显示走势图", "en": "Show Trend Chart"},
    "menu_show_details": {"zh": "显示高/低/基准价", "en": "Show High/Low/Base Details"},
    "menu_always_on_top": {"zh": "窗口置顶", "en": "Always on Top"},

    # 菜单：涨跌与配色
    "menu_basis": {"zh": "涨跌基准", "en": "Change Basis"},
    "menu_basis_prev": {"zh": "较昨收价 (Prev Close)", "en": "vs Prev Close"},
    "menu_basis_open": {"zh": "较今开盘 (Open Price)", "en": "vs Open Price"},
    "menu_color_mode": {"zh": "红绿配色习惯", "en": "Color Scheme"},
    "menu_color_cny": {"zh": "红涨绿跌 (国内习惯)", "en": "Red Up / Green Down (CN)"},
    "menu_color_intl": {"zh": "绿涨红跌 (国际习惯)", "en": "Green Up / Red Down (Intl)"},

    # 菜单：频率与尺寸
    "menu_refresh_rate": {"zh": "刷新频率", "en": "Refresh Interval"},
    "menu_opacity": {"zh": "卡片透明度", "en": "Card Opacity"},
    "menu_width": {"zh": "卡片宽度", "en": "Card Width"},

    # 菜单：语言
    "menu_language": {"zh": "语言 (Language)", "en": "Language (语言)"},
    "menu_lang_auto": {"zh": "跟随系统 (Auto)", "en": "Auto (System Default)"},
    "menu_lang_zh": {"zh": "简体中文", "en": "Simplified Chinese (简体中文)"},
    "menu_lang_en": {"zh": "English", "en": "English"},

    # 菜单：维护操作
    "menu_data_mgmt": {"zh": "数据与维护", "en": "Maintenance"},
    "menu_open_config": {"zh": "打开配置目录", "en": "Open Config Directory"},
    "menu_clear_cache": {"zh": "清除走势缓存", "en": "Clear Trend Cache"},
    "menu_reset_pos": {"zh": "重置窗口位置", "en": "Reset Window Position"},
    "menu_quit": {"zh": "退出 GoldTicker", "en": "Quit GoldTicker"},
}


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
