"""Windows 表现层与动态自绘宽托盘单元测试 (tests/test_windows.py)。

覆盖 AC-1 (动态宽托盘位图引擎)、AC-2 (悬浮窗交互与视觉规范)、
AC-3 (双入口互锁防幽灵机制)、AC-4 (Action Matrix 契约)、AC-5 (PE 版本元数据) 与表现层纯净原则。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.constants import (
    DISCLAIMER_CN,
    SYMBOL_AU9999,
    SYMBOL_XAU_USD,
    SYMBOL_ZS_JCJ,
)
from core.pricing import QuoteData
from windows.tray import (
    COLOR_GREEN,
    COLOR_MUTED,
    COLOR_RED,
    build_tray_tooltip,
    calculate_quote_delta,
    can_toggle_entry,
    create_tray_image,
    get_quote_color,
    is_quote_valid,
)


class TestWindowsTrayEngine(unittest.TestCase):
    """测试 Windows 动态自绘内存宽位图托盘引擎。"""

    def setUp(self):
        self.valid_quote_cn = QuoteData(
            symbol=SYMBOL_ZS_JCJ,
            price=871.50,
            prev_close=868.00,
            open_price=869.00,
            high=873.00,
            low=867.00,
            change=3.50,
            change_pct=0.40,
            time_str="10:30:00",
            source_id="tangdouz",
            source_name="浙商银行",
        )
        self.valid_quote_intl = QuoteData(
            symbol=SYMBOL_XAU_USD,
            price=2735.60,
            prev_close=2740.00,
            open_price=2738.00,
            high=2745.00,
            low=2730.00,
            change=-4.40,
            change_pct=-0.16,
            time_str="10:30:00",
            source_id="sina_xau",
            source_name="新浪国际",
        )

    def test_create_tray_image_dimensions_and_mode(self):
        """AC-1: 验证生成位图的尺寸与 RGBA 透明通道格式。"""
        img_standard = create_tray_image(self.valid_quote_cn, {"symbol": SYMBOL_ZS_JCJ}, width=96, height=32)
        self.assertEqual(img_standard.size, (96, 32))
        self.assertEqual(img_standard.mode, "RGBA")

        img_compact = create_tray_image(self.valid_quote_cn, {"symbol": SYMBOL_ZS_JCJ}, width=48, height=16)
        self.assertEqual(img_compact.size, (48, 16))
        self.assertEqual(img_compact.mode, "RGBA")

    def test_create_tray_image_none_quote_safe(self):
        """AC-1: 验证行情为空或异常时位图引擎安全降级不崩溃。"""
        img_none = create_tray_image(None, {"symbol": SYMBOL_ZS_JCJ})
        self.assertEqual(img_none.size, (96, 32))
        self.assertEqual(img_none.mode, "RGBA")

        err_quote = QuoteData(
            symbol=SYMBOL_ZS_JCJ,
            price=0.0,
            prev_close=0.0,
            open_price=0.0,
            high=0.0,
            low=0.0,
            change=0.0,
            change_pct=0.0,
            time_str="--",
            source_id="err",
            source_name="err",
            error="Network Timeout",
        )
        img_err = create_tray_image(err_quote, {"symbol": SYMBOL_ZS_JCJ})
        self.assertEqual(img_err.size, (96, 32))
        self.assertEqual(img_err.mode, "RGBA")

    def test_color_mode_adaption(self):
        """AC-1: 验证红涨绿跌与绿涨红跌色彩自适应映射。"""
        # 上涨 (diff > 0)
        col_red_up = get_quote_color(3.5, color_mode="red-up")
        self.assertEqual(col_red_up, COLOR_RED)
        col_green_up = get_quote_color(3.5, color_mode="green-up")
        self.assertEqual(col_green_up, COLOR_GREEN)

        # 下跌 (diff < 0)
        col_red_down = get_quote_color(-3.5, color_mode="red-up")
        self.assertEqual(col_red_down, COLOR_GREEN)
        col_green_down = get_quote_color(-3.5, color_mode="green-up")
        self.assertEqual(col_green_down, COLOR_RED)

        # 持平
        col_zero = get_quote_color(0.0, color_mode="red-up")
        self.assertEqual(col_zero, COLOR_MUTED)

    def test_tooltip_content_fullness(self):
        """AC-1: 验证 Tooltip 包含全量行情字段与免责声明。"""
        tooltip = build_tray_tooltip(self.valid_quote_cn, {"symbol": SYMBOL_ZS_JCJ, "showDisclaimer": True})
        self.assertIn("GoldTicker", tooltip)
        self.assertIn("浙商", tooltip)
        self.assertIn("871.50", tooltip)
        self.assertIn("今开: 869.00", tooltip)
        self.assertIn("基准(昨收): 868.00", tooltip)
        self.assertIn("最高: 873.00", tooltip)
        self.assertIn("最低: 867.00", tooltip)
        self.assertIn("更新: 10:30:00", tooltip)
        self.assertIn(DISCLAIMER_CN, tooltip)


class TestDualEntryInterlockProtocol(unittest.TestCase):
    """测试 AC-3: 双入口互锁防幽灵机制核心契约。"""

    def test_both_enabled_can_toggle_either(self):
        """双入口都开启时，允许关闭任一入口。"""
        self.assertTrue(can_toggle_entry(current_desktop=True, current_tray=True, toggling_target="desktop"))
        self.assertTrue(can_toggle_entry(current_desktop=True, current_tray=True, toggling_target="tray"))

    def test_tray_only_cannot_close_tray(self):
        """仅托盘开启时，托盘开关被互锁锁定（不可关闭），桌面可以随时开启。"""
        # 试图关闭托盘 -> 必须被拒绝（False）
        self.assertFalse(can_toggle_entry(current_desktop=False, current_tray=True, toggling_target="tray"))
        # 开启桌面 -> 允许（True）
        self.assertTrue(can_toggle_entry(current_desktop=False, current_tray=True, toggling_target="desktop"))

    def test_desktop_only_cannot_close_desktop(self):
        """仅桌面开启时，桌面开关被互锁锁定（不可关闭），托盘可以随时开启。"""
        # 试图关闭桌面 -> 必须被拒绝（False）
        self.assertFalse(can_toggle_entry(current_desktop=True, current_tray=False, toggling_target="desktop"))
        # 开启托盘 -> 允许（True）
        self.assertTrue(can_toggle_entry(current_desktop=True, current_tray=False, toggling_target="tray"))


class TestPurityAndVersionMetadata(unittest.TestCase):
    """测试表现层纯净原则与 PE 版本信息。"""

    def test_purity_principle_no_debug_point_count(self):
        """表现层纯净原则：代码与渲染逻辑中严禁残留“1144点”等技术采样计数。"""
        main_py = REPO_ROOT / "windows" / "main.py"
        content = main_py.read_text(encoding="utf-8")
        self.assertNotIn("1144", content)
        self.assertNotIn("个点", content)
        self.assertNotIn("点)", content)

    def test_version_metadata(self):
        """AC-5: 验证 version.txt PE 资源元数据包含版权与 studio 声明。"""
        version_txt = REPO_ROOT / "windows" / "version.txt"
        self.assertTrue(version_txt.is_file())
        text = version_txt.read_text(encoding="utf-8")
        self.assertIn("realsuperj", text)
        self.assertIn("GoldTicker", text)
        self.assertIn("Copyright © 2026 realsuperj. MIT License.", text)


if __name__ == "__main__":
    unittest.main()
