"""GoldTicker Windows 托盘位图自绘引擎与双入口互锁判定 (windows/tray.py)。

突破 Windows 11 移除 DeskBand 的技术限制，基于 Pillow 动态自绘内存宽位图，
并结合 pystray 在 Windows 任务栏通知区域模拟出原生价格走势状态栏。
实现等宽排版（“金”与“Au”）、红涨绿跌自适应与双入口互锁防幽灵机制。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# 确保任意工作路径下均能正确定位并导入 core 包
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

from core.constants import (
    DEFAULT_BANK_SPREADS,
    DISCLAIMER_CN,
    SYMBOL_AU9999,
    SYMBOL_META,
    SYMBOL_XAU_USD,
    SYMBOL_ZS_JCJ,
)
from core.pricing import QuoteData

# 颜色常量
COLOR_RED = "#ff5751"       # 涨红
COLOR_GREEN = "#47de87"     # 跌绿
COLOR_MUTED = "#9da5b4"     # 灰色/持平
COLOR_WHITE = "#ffffff"     # 纯白
COLOR_BG_BADGE = "#2d333b"  # 徽标底色
COLOR_TRANSPARENT = (0, 0, 0, 0)


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """按平台优先级安全查找可用字体，失败回退到 PIL 内置字体。"""
    candidate_font_names = []
    if sys.platform.startswith("win"):
        if bold:
            candidate_font_names = ["msyhbd.ttc", "simsun.ttc", "arialbd.ttf", "segoeuib.ttf"]
        else:
            candidate_font_names = ["msyh.ttc", "simsun.ttc", "arial.ttf", "segoeui.ttf"]
        # Windows Fonts 目录
        windir = os.environ.get("WINDIR", "C:\\Windows")
        fonts_dir = Path(windir) / "Fonts"
        for name in candidate_font_names:
            font_path = fonts_dir / name
            if font_path.is_file():
                try:
                    return ImageFont.truetype(str(font_path), size)
                except Exception:
                    continue
    elif sys.platform == "darwin":
        # macOS 字体回退
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    else:
        # Linux 字体回退
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        for p in candidates:
            if os.path.isfile(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue

    # 尝试直接通过名字加载
    for name in ["msyh.ttc", "arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue

    return ImageFont.load_default()


def is_quote_valid(quote: Optional[QuoteData]) -> bool:
    """判定行情对象是否有效可用。"""
    return quote is not None and not quote.error and quote.price > 0


def calculate_quote_delta(
    quote: Optional[QuoteData],
    change_basis: str = "prev_close",
) -> Tuple[float, float]:
    """计算价格变动绝对值与变动比例 (%)。

    Returns:
        (diff, pct)
    """
    if not is_quote_valid(quote):
        return 0.0, 0.0

    base_price = quote.prev_close if change_basis == "prev_close" else quote.open_price
    if base_price <= 0:
        base_price = quote.prev_close if quote.prev_close > 0 else quote.open_price

    if base_price <= 0:
        return 0.0, 0.0

    diff = quote.price - base_price
    pct = (diff / base_price) * 100.0
    return diff, pct


def get_quote_color(
    diff: float,
    color_mode: str = "red-up",
) -> str:
    """根据红涨绿跌配置获取对应色彩代码。"""
    if abs(diff) < 1e-4:
        return COLOR_MUTED
    if diff > 0:
        return COLOR_RED if color_mode == "red-up" else COLOR_GREEN
    else:
        return COLOR_GREEN if color_mode == "red-up" else COLOR_RED


def can_toggle_entry(current_desktop: bool, current_tray: bool, toggling_target: str) -> bool:
    """双入口互锁防幽灵判定核心契约。

    规则：
    - 至少保留一个可见入口（悬浮窗或托盘图标）；
    - 若当前只有 desktop 开启（tray 已关闭），则 desktop 不可关闭（返回 False）；
    - 若当前只有 tray 开启（desktop 已关闭），则 tray 不可关闭（返回 False）；
    - 开启操作始终允许。

    Args:
        current_desktop: 当前是否显示桌面悬浮窗
        current_tray: 当前是否显示托盘
        toggling_target: "desktop" 或 "tray"

    Returns:
        bool: 是否允许执行该切换操作（若为 False 则在菜单中置灰/禁用）
    """
    if toggling_target == "desktop":
        # 如果当前是要关闭 desktop（从 True 变 False），且 tray 当前未开启，则禁止
        if current_desktop and not current_tray:
            return False
        return True
    elif toggling_target in ("tray", "menuBar", "showMenuBar"):
        # 如果当前是要关闭 tray（从 True 变 False），且 desktop 当前未开启，则禁止
        if current_tray and not current_desktop:
            return False
        return True
    return True


def create_tray_image(
    quote: Optional[QuoteData],
    config: Dict[str, Any],
    width: int = 96,
    height: int = 32,
) -> Image.Image:
    """动态在内存中渲染 Windows 托盘抗锯齿宽位图（默认 96x32 RGBA）。

    排版对齐规范：
    - 左侧：国内模式绘制“金”，国际模式绘制“Au”（等宽占据 28 像素宽度徽标）；
    - 右侧：
      - 上行：最新价格（加粗等宽排布，白色/主题色）；
      - 下行：涨跌幅百分比（红涨绿跌自适应色彩）。
    """
    img = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
    draw = ImageDraw.Draw(img)

    change_basis = config.get("changeBasis", "prev_close")
    color_mode = config.get("colorMode", "red-up")

    # 1. 判定前缀字符（等宽排版：国内模式“金”，国际模式“Au”）
    symbol = quote.symbol if quote else config.get("symbol", SYMBOL_ZS_JCJ)
    prefix = "Au" if symbol == SYMBOL_XAU_USD else "金"

    diff, pct = calculate_quote_delta(quote, change_basis)
    color = get_quote_color(diff, color_mode)

    # 2. 绘制左侧徽标区域（等宽 26x24 徽标底框）
    badge_x0, badge_y0 = 3, 4
    badge_w, badge_h = 26, height - 8
    badge_x1, badge_y1 = badge_x0 + badge_w, badge_y0 + badge_h

    # 徽标圆角背景
    draw.rounded_rectangle(
        [(badge_x0, badge_y0), (badge_x1, badge_y1)],
        radius=4,
        fill=COLOR_BG_BADGE,
    )

    prefix_font = _get_font(size=12, bold=True)
    # 计算文字居中坐标
    try:
        bbox = draw.textbbox((0, 0), prefix, font=prefix_font)
        pw = bbox[2] - bbox[0]
        ph = bbox[3] - bbox[1]
    except Exception:
        pw, ph = 12, 12
    px = badge_x0 + (badge_w - pw) / 2
    py = badge_y0 + (badge_h - ph) / 2 - 1
    draw.text((px, py), prefix, fill="#e6edf3", font=prefix_font)

    # 3. 绘制右侧价格与涨跌幅
    text_x = badge_x1 + 6
    if not is_quote_valid(quote):
        price_str = "--"
        pct_str = "未就绪"
        val_color = COLOR_MUTED
    else:
        price_str = f"{quote.price:.2f}"
        pct_str = f"{pct:+.2f}%"
        val_color = color

    if height >= 28:
        # 双行排版 (96x32)
        price_font = _get_font(size=11, bold=True)
        pct_font = _get_font(size=10, bold=False)

        draw.text((text_x, 3), price_str, fill=COLOR_WHITE, font=price_font)
        draw.text((text_x, 17), pct_str, fill=val_color, font=pct_font)
    else:
        # 单行紧凑排版 (48x16 等低分辨率)
        compact_font = _get_font(size=9, bold=False)
        compact_str = f"{price_str} {pct_str}"
        draw.text((text_x, (height - 10) / 2), compact_str, fill=val_color, font=compact_font)

    return img


def build_tray_tooltip(quote: Optional[QuoteData], config: Dict[str, Any]) -> str:
    """生成 Windows 托盘图标鼠标悬停 Tooltip 文本（全量行情数据与免责声明）。"""
    symbol = config.get("symbol", SYMBOL_ZS_JCJ)
    meta = SYMBOL_META.get(symbol, {})
    symbol_name = meta.get("name_cn", symbol)
    currency = meta.get("currency", "CNY")

    if not is_quote_valid(quote):
        return f"GoldTicker\n{symbol_name}: 获取中…\n{DISCLAIMER_CN}"

    change_basis = config.get("changeBasis", "prev_close")
    basis_name = "昨收" if change_basis == "prev_close" else "今开"
    diff, pct = calculate_quote_delta(quote, change_basis)
    sign = "+" if diff > 0 else ""

    lines = [
        f"GoldTicker · {symbol_name}",
        f"最新价: {quote.price:.2f} {currency} ({sign}{diff:.2f}, {pct:+.2f}%)",
        f"基准({basis_name}): {quote.prev_close:.2f} | 今开: {quote.open_price:.2f}",
        f"最高: {quote.high:.2f} | 最低: {quote.low:.2f}",
        f"更新: {quote.time_str} (源: {quote.source_name})",
    ]

    if symbol == SYMBOL_ZS_JCJ and "zs_jcj" in DEFAULT_BANK_SPREADS:
        spread = DEFAULT_BANK_SPREADS["zs_jcj"]
        buy_p = quote.price + spread["buy_fee"]
        sell_p = quote.price - spread["sell_fee"]
        lines.append(f"浙商银行参考: 买入 {buy_p:.2f} | 卖出 {sell_p:.2f}")

    if config.get("showDisclaimer", True):
        lines.append(f"\n{DISCLAIMER_CN}")

    return "\n".join(lines)
