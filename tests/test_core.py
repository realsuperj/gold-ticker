"""核心模块全量单元测试 (tests/test_core.py)。"""
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 保证从任意工作目录执行时均能正确导入 core
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import (
    DEFAULT_CONFIG,
    load_config,
    sanitize_config,
    save_config,
)
from core.constants import (
    COOL_DOWN_SECONDS,
    DEFAULT_BANK_SPREADS,
    DISCLAIMER_CN,
    MIN_REFRESH_SECONDS,
    SUPPORTED_SYMBOLS,
    SYMBOL_AU9999,
    SYMBOL_ICBC_JCJ,
    SYMBOL_META,
    SYMBOL_XAU_USD,
    SYMBOL_ZS_JCJ,
)
from core.pricing import PricingEngine, QuoteData
from core.storage import (
    cleanup_old_history,
    clear_intraday_cache,
    load_today_points,
    record_price_point,
)


class TestCoreConstants(unittest.TestCase):
    def test_symbols_and_meta(self):
        self.assertIn(SYMBOL_AU9999, SUPPORTED_SYMBOLS)
        self.assertIn(SYMBOL_ZS_JCJ, SUPPORTED_SYMBOLS)
        self.assertIn(SYMBOL_ICBC_JCJ, SUPPORTED_SYMBOLS)
        self.assertIn(SYMBOL_XAU_USD, SUPPORTED_SYMBOLS)

        for sym in SUPPORTED_SYMBOLS:
            meta = SYMBOL_META[sym]
            self.assertEqual(meta["id"], sym)
            self.assertIn("name_cn", meta)
            self.assertIn("name_en", meta)
            self.assertIn(meta["prefix_cn"], ("金", "Au"))
            self.assertIn(meta["prefix_en"], ("金", "Au"))

    def test_compliance_and_limits(self):
        self.assertGreaterEqual(MIN_REFRESH_SECONDS, 10)
        self.assertGreaterEqual(COOL_DOWN_SECONDS, 60)
        self.assertIn("免责声明", DISCLAIMER_CN)


class TestCoreConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config_path = self.test_dir / "config.json"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sanitize_refresh_rate_compliance(self):
        # 强制防范低于 10 秒的暴力轮询
        bad_cfg = {"refreshSeconds": 3}
        clean = sanitize_config(bad_cfg)
        self.assertEqual(clean["refreshSeconds"], 10)

        good_cfg = {"refreshSeconds": 15}
        self.assertEqual(sanitize_config(good_cfg)["refreshSeconds"], 15)

    def test_lockout_guard_auto_healing(self):
        # 若双入口都被设为 False，自动自愈恢复桌面入口
        ghost_cfg = {"showOnDesktop": False, "showMenuBarIcon": False}
        clean = sanitize_config(ghost_cfg)
        self.assertTrue(clean["showOnDesktop"])

        single_desktop = {"showOnDesktop": True, "showMenuBarIcon": False}
        self.assertFalse(sanitize_config(single_desktop)["showMenuBarIcon"])

    def test_opacity_and_width_clamping(self):
        self.assertEqual(sanitize_config({"opacity": 0.1})["opacity"], 0.60)
        self.assertEqual(sanitize_config({"opacity": 1.5})["opacity"], 1.0)
        # Nearest legal width depends on platform (macWidths vs winWidths).
        from core.config import VALID_WIDTHS
        expected = min(VALID_WIDTHS, key=lambda w: abs(w - 210))
        self.assertEqual(sanitize_config({"width": 210})["width"], expected)

    def test_load_save_roundtrip(self):
        initial = load_config(self.config_path)
        self.assertTrue(initial["showOnDesktop"])

        initial["refreshSeconds"] = 30
        initial["symbol"] = SYMBOL_XAU_USD
        save_config(initial, self.config_path)

        reloaded = load_config(self.config_path)
        self.assertEqual(reloaded["refreshSeconds"], 30)
        self.assertEqual(reloaded["symbol"], SYMBOL_XAU_USD)


class TestCoreStorage(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_record_and_load_points(self):
        ok = record_price_point(871.20, SYMBOL_AU9999, "09:30", data_dir=self.test_dir)
        self.assertTrue(ok)

        pts = load_today_points(SYMBOL_AU9999, data_dir=self.test_dir)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["p"], 871.20)
        self.assertEqual(pts[0]["t"], "09:30")

        # 同分钟更新测试
        record_price_point(871.50, SYMBOL_AU9999, "09:30", data_dir=self.test_dir)
        pts = load_today_points(SYMBOL_AU9999, data_dir=self.test_dir)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["p"], 871.50)

    def test_cleanup_old_history(self):
        today = dt.date.today()
        d_recent = today - dt.timedelta(days=1)
        d_old = today - dt.timedelta(days=5)

        f_recent = self.test_dir / f"intraday-{d_recent.isoformat()}.json"
        f_old = self.test_dir / f"intraday-{d_old.isoformat()}.json"

        f_recent.write_text("[]", encoding="utf-8")
        f_old.write_text("[]", encoding="utf-8")

        del_cnt = cleanup_old_history(keep_days=3, data_dir=self.test_dir)
        self.assertEqual(del_cnt, 1)
        self.assertTrue(f_recent.exists())
        self.assertFalse(f_old.exists())

    def test_clear_cache(self):
        record_price_point(871.20, SYMBOL_AU9999, data_dir=self.test_dir)
        self.assertTrue(clear_intraday_cache(data_dir=self.test_dir))
        self.assertEqual(len(load_today_points(data_dir=self.test_dir)), 0)


class TestCorePricing(unittest.TestCase):
    def setUp(self):
        self.engine = PricingEngine()

    @patch("core.pricing.http_get")
    def test_fetch_tangdouz_parsing(self, mock_get):
        mock_get.return_value = (
            "最新价格: 871.50\n"
            "前收盘价: 868.00\n"
            "开盘价: 869.00\n"
            "最高价: 873.00\n"
            "最低价: 867.00\n"
            "更新时间: 2026-11-11 14:30:00\n"
        ).encode("utf-8")

        q = self.engine.get_quote(SYMBOL_ZS_JCJ)
        self.assertEqual(q.symbol, SYMBOL_ZS_JCJ)
        self.assertEqual(q.price, 871.50)
        self.assertEqual(q.prev_close, 868.00)
        self.assertEqual(q.change, 3.50)
        self.assertEqual(q.time_str, "14:30")
        self.assertFalse(q.is_estimated)

    def test_fetch_tangdouz_real_byte_regression(self):
        # 回归：真实接口返回 UTF-8，但其字节可被 gb18030 无异常误解为乱码。
        # 旧实现先按 gb18030 解码导致浙商源解析失败，必须先按 UTF-8 严格解码。
        from unittest.mock import patch
        import core.pricing as cp
        real = (
            "浙商银行积存金价格信息\n====================\n产品名称: 浙商银行积存金\n产品代码: JCJ\n"
            "最新价格: 837.82 元\n涨跌额: 4.81 元\n涨跌幅: 0.58%\n开盘价: 832.99 元\n最高价: 843.63 元\n"
            "最低价: 831.97 元\n前收盘价: 833.01 元\n成交量: 1\n更新时间: 2026-11-13 15:42:15\n"
        ).encode("utf-8")
        with patch.object(cp, "http_get", return_value=real):
            pack = cp.fetch_tangdouz_raw()
        self.assertEqual(pack[0], 837.82)
        self.assertEqual(pack[1], 833.01)
        self.assertEqual(pack[2], 832.99)
        self.assertEqual(pack[7], "15:42")

    @patch("core.pricing.http_get")
    def test_bank_spread_estimation(self, mock_get):
        # 模拟新浪 Au99.99
        # f[3]=870.00, f[5]=865.00, f[7]=872.00, f[8]=864.00, f[9]=866.00
        mock_get.return_value = (
            'var hq_str_SGE_AU9999="Au99.99,Au99.99,AU9999,870.00,0,865.00,0,872.00,864.00,866.00,0,0,0,0,0,0,2026-11-11 15:00:00";\n'
        ).encode("utf-8")

        q_icbc = self.engine.get_quote(SYMBOL_ICBC_JCJ)
        spread = DEFAULT_BANK_SPREADS[SYMBOL_ICBC_JCJ]
        expected_price = round(870.00 + spread, 2)
        self.assertEqual(q_icbc.price, expected_price)
        self.assertTrue(q_icbc.is_estimated)

    @patch("core.pricing.http_get")
    def test_international_xau_usd(self, mock_get):
        mock_get.return_value = (
            'var hq_str_hf_XAU="2650.50,0,0,0,2660.00,2640.00,15:30:00,2645.00,2648.00";\n'
            'var hq_str_fx_susdcny="15:30:00,7.2400,0";\n'
        ).encode("utf-8")

        q_intl = self.engine.get_quote(SYMBOL_XAU_USD)
        self.assertEqual(q_intl.price, 2650.50)
        self.assertEqual(q_intl.usd_price, 2650.50)
        self.assertEqual(q_intl.fx_rate, 7.24)
        self.assertEqual(q_intl.time_str, "15:30")

    @patch("core.pricing.http_get")
    def test_cooldown_and_fallback(self, mock_get):
        # 连续故障触发冷却测试
        mock_get.side_effect = Exception("网络连接超时")
        q1 = self.engine.get_quote(SYMBOL_ZS_JCJ)
        self.assertEqual(q1.price, 0.0)

        statuses = self.engine.get_source_statuses()
        tangdouz_st = [s for s in statuses if s["source_id"] == "tangdouz"][0]
        self.assertTrue(tangdouz_st["cooling"])

    @patch("core.pricing.fetch_sina_xau_raw")
    @patch("core.pricing.fetch_tangdouz_raw")
    @patch("core.pricing.fetch_sina_au9999_raw")
    def test_sample_all_quotes_covers_supported(self, mock_au, mock_zs, mock_xau):
        mock_au.return_value = (870.0, 865.0, 866.0, 872.0, 864.0, 5.0, 0.58, "15:00")
        mock_zs.return_value = (871.5, 868.0, 869.0, 873.0, 867.0, 3.5, 0.4, "15:01")
        mock_xau.return_value = (
            (2650.5, 2645.0, 2648.0, 2660.0, 2640.0, 5.5, 0.21, "15:30"),
            2650.5,
            7.24,
        )
        quotes = self.engine.sample_all_quotes()
        for sym in SUPPORTED_SYMBOLS:
            self.assertIn(sym, quotes)
            self.assertGreater(quotes[sym].price, 0)
        self.assertEqual(quotes[SYMBOL_ZS_JCJ].price, 871.5)
        self.assertEqual(quotes[SYMBOL_AU9999].price, 870.0)
        self.assertEqual(
            quotes[SYMBOL_ICBC_JCJ].price,
            round(870.0 + DEFAULT_BANK_SPREADS[SYMBOL_ICBC_JCJ], 2),
        )


if __name__ == "__main__":
    unittest.main()
