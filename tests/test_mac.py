"""macOS 表现层单测与冒烟验证 (tests/test_mac.py)。"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import DEFAULT_CONFIG
from core.constants import SYMBOL_AU9999, SYMBOL_XAU_USD
if sys.platform != "darwin":
    raise unittest.SkipTest("macOS AppKit tests require macOS")
from mac.main import I18N, calc_window_height, get_current_lang


class TestMacModule(unittest.TestCase):
    def test_window_height_calculation(self):
        # 基础高度
        cfg_compact = {"showChart": False, "showDetails": False}
        h1 = calc_window_height(cfg_compact)

        # 展开走势图
        cfg_chart = {"showChart": True, "showDetails": False}
        h2 = calc_window_height(cfg_chart)
        self.assertGreater(h2, h1)

        # 同时展开走势图与详细行
        cfg_full = {"showChart": True, "showDetails": True}
        h3 = calc_window_height(cfg_full)
        self.assertGreater(h3, h2)

    def test_i18n_dictionary(self):
        for lang in ("zh", "en"):
            self.assertIn(lang, I18N)
            self.assertIn("showOnDesktop", I18N[lang])
            self.assertIn("showMenuBar", I18N[lang])
            self.assertIn("showChart", I18N[lang])
            self.assertIn("alwaysOnTop", I18N[lang])

    def test_get_current_lang_override(self):
        self.assertEqual(get_current_lang({"language": "zh"}), "zh")
        self.assertEqual(get_current_lang({"language": "en"}), "en")

    def test_no_debug_point_residual(self):
        """严格验证表现层纯净原则：源码中不得残留类似 1144点 等采样调试信息。"""
        main_source = (REPO_ROOT / "mac" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("1144", main_source)
        self.assertNotIn("点数", main_source)
        self.assertNotIn("采样点", main_source)

    def test_lockout_guard_menu_state(self):
        """验证双入口互锁防幽灵置灰逻辑。"""
        from unittest.mock import MagicMock
        from mac.main import MenuController

        mock_app = MagicMock()
        # 1. 双开时，两个开关均可用 (Enabled = True)
        mock_app.config = {"showOnDesktop": True, "showMenuBarIcon": True, "language": "zh"}
        mock_app.current_quote = None
        ctrl = MenuController.alloc().initWithAppController_(mock_app)
        menu1 = ctrl.build_menu()
        items1 = {item.title(): item for item in menu1.itemArray()}
        self.assertTrue(items1["显示到桌面"].isEnabled())
        self.assertTrue(items1["显示到菜单栏/托盘"].isEnabled())

        # 2. 菜单栏已关闭，桌面入口置灰锁定 (Enabled = False)
        mock_app.config = {"showOnDesktop": True, "showMenuBarIcon": False, "language": "zh"}
        menu2 = ctrl.build_menu()
        items2 = {item.title(): item for item in menu2.itemArray()}
        self.assertFalse(items2["显示到桌面"].isEnabled())
        self.assertTrue(items2["显示到菜单栏/托盘"].isEnabled())

        # 3. 桌面已关闭，菜单栏入口置灰锁定 (Enabled = False)
        mock_app.config = {"showOnDesktop": False, "showMenuBarIcon": True, "language": "zh"}
        menu3 = ctrl.build_menu()
        items3 = {item.title(): item for item in menu3.itemArray()}
        self.assertTrue(items3["显示到桌面"].isEnabled())
        self.assertFalse(items3["显示到菜单栏/托盘"].isEnabled())


if __name__ == "__main__":
    unittest.main()
