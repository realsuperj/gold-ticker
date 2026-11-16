"""用户配置读写与跨端路径管理 (core/config.py)。"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict

from core.constants import (
    DEFAULT_REFRESH_SECONDS,
    MIN_REFRESH_SECONDS,
    SUPPORTED_SYMBOLS,
    SYMBOL_AU9999,
)
from core.product import load_spec

_SPEC = load_spec()
_DEFAULTS = _SPEC["defaults"]
_OPTIONS = _SPEC["options"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "symbol": _DEFAULTS["symbol"],
    "showOnDesktop": bool(_DEFAULTS["showOnDesktop"]),
    "showMenuBarIcon": bool(_DEFAULTS["showMenuBarIcon"]),
    "showChart": bool(_DEFAULTS["showChart"]),
    "showDetails": bool(_DEFAULTS["showDetails"]),
    "alwaysOnTop": bool(_DEFAULTS["alwaysOnTop"]),
    "width": int(_DEFAULTS["winWidth"] if sys.platform == "win32" else _DEFAULTS["macWidth"]),
    "opacity": float(_DEFAULTS["opacity"]),
    "refreshSeconds": int(_DEFAULTS["refreshSeconds"]),
    "colorMode": _DEFAULTS["colorMode"],
    "changeBasis": _DEFAULTS["changeBasis"],
    "language": _DEFAULTS["language"],
    "windowX": float(_DEFAULTS["windowX"]),
    "windowY": float(_DEFAULTS["windowY"]),
}

VALID_WIDTHS = tuple(int(x) for x in (_OPTIONS["winWidths"] if sys.platform == "win32" else _OPTIONS["macWidths"]))
VALID_REFRESH_INTERVALS = tuple(int(x) for x in _OPTIONS["refreshIntervals"])
VALID_OPACITIES = tuple(float(x) for x in _OPTIONS["opacities"])


def get_app_data_dir() -> Path:
    """获取跨平台标准应用数据存储路径。"""
    override = os.environ.get("GOLDTICKER_DATA_DIR")
    if override:
        base = Path(override).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "GoldTicker"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / "GoldTicker" if appdata else Path.home() / ".gold-ticker"
    else:
        # Linux / XDG
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) / "gold-ticker" if xdg_config else Path.home() / ".config" / "gold-ticker"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_default_config_path() -> Path:
    """获取配置文件默认绝对路径。"""
    return get_app_data_dir() / "config.json"


def sanitize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """校验并纠偏配置合法性，保证合规与数据类型安全。"""
    res = dict(DEFAULT_CONFIG)
    if not isinstance(cfg, dict):
        return res

    cfg = dict(cfg)
    for old, new in (
        ("refreshInterval", "refreshSeconds"),
        ("showMenuBar", "showMenuBarIcon"),
        ("dataSource", "symbol"),
    ):
        if new not in cfg and old in cfg:
            cfg[new] = cfg[old]
    cfg["colorMode"] = {"red-up": "cny", "green-up": "intl"}.get(cfg.get("colorMode"), cfg.get("colorMode", "cny"))
    cfg["changeBasis"] = {"prev_close": "prevClose", "open_price": "open"}.get(cfg.get("changeBasis"), cfg.get("changeBasis", "prevClose"))

    # 标的合法性
    sym = str(cfg.get("symbol", SYMBOL_AU9999)).strip()
    if sym in SUPPORTED_SYMBOLS:
        res["symbol"] = sym

    # 布尔项
    for bool_key in ("showOnDesktop", "showMenuBarIcon", "showChart", "showDetails", "alwaysOnTop"):
        if bool_key in cfg:
            res[bool_key] = bool(cfg[bool_key])

    # 互锁防幽灵自愈保障：若两个入口均被写成了 False，自动强制恢复桌面悬浮窗为 True
    if not res["showOnDesktop"] and not res["showMenuBarIcon"]:
        res["showOnDesktop"] = True

    # 宽度约束
    try:
        w = int(cfg.get("width", 216))
        res["width"] = w if w in VALID_WIDTHS else min(VALID_WIDTHS, key=lambda x: abs(x - w))
    except (ValueError, TypeError):
        res["width"] = 216

    # 透明度约束 (0.60 ~ 1.0)
    try:
        op = float(cfg.get("opacity", 0.88))
        res["opacity"] = max(0.60, min(1.0, op))
    except (ValueError, TypeError):
        res["opacity"] = 0.88

    # 轮询频率合规底线 (严格 >= 10 秒)
    try:
        ref = int(cfg.get("refreshSeconds", DEFAULT_REFRESH_SECONDS))
        res["refreshSeconds"] = max(MIN_REFRESH_SECONDS, ref)
    except (ValueError, TypeError):
        res["refreshSeconds"] = DEFAULT_REFRESH_SECONDS

    # 配色模式
    cm = str(cfg.get("colorMode", "cny")).lower()
    res["colorMode"] = "intl" if cm == "intl" else "cny"

    # 涨跌基准
    cb = str(cfg.get("changeBasis", "prevClose")).strip()
    res["changeBasis"] = "open" if cb == "open" else "prevClose"

    # 界面语言
    lang = str(cfg.get("language", "auto")).lower().strip()
    res["language"] = lang if lang in ("auto", "zh", "en") else "auto"

    # 窗口坐标
    for coord_key in ("windowX", "windowY"):
        try:
            val = float(cfg.get(coord_key, -1))
            res[coord_key] = val
        except (ValueError, TypeError):
            res[coord_key] = -1

    return res


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """读取并解析配置文件，带容错与自动初始化。"""
    path = config_path or get_default_config_path()
    if not path.exists():
        save_config(DEFAULT_CONFIG, path)
        return dict(DEFAULT_CONFIG)

    try:
        raw_text = path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)
        return sanitize_config(raw_data)
    except Exception:
        # 文件损坏或格式错误时退守默认配置，避免崩溃
        return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any], config_path: Path | None = None) -> None:
    """安全持久化配置至文件。"""
    path = config_path or get_default_config_path()
    cleaned = sanitize_config(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to save config to {path}: {e}\n")
