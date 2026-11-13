"""时区与当日冻结基准回归测试 (tests/test_timezone.py)。

覆盖 UTC 存储、同分钟合并、缺口断线阈值、当日冻结基准先到先得、
旧格式（无 ts 的点）按文件本地日迁移。
"""
from __future__ import annotations

import datetime as dt
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.constants import SYMBOL_AU9999, SYMBOL_ZS_JCJ
from core.pricing import QuoteData
from core.storage import (
    SAMPLE_GAP_BREAK_SECONDS,
    apply_frozen_basis,
    freeze_day_basis,
    get_day_basis,
    load_today_points,
    now_utc_ms,
    record_price_point,
)


def _ts(h: int, m: int, sec: int = 0) -> int:
    """今日指定本地时刻的 UTC 毫秒。"""
    base = dt.datetime.combine(dt.date.today(), dt.time(0, 0))
    return int(base.timestamp() * 1000) + ((h * 60 + m) * 60 + sec) * 1000


class TestUTCStorage(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_points_stored_with_utc_ts(self):
        ts = now_utc_ms()
        self.assertTrue(record_price_point(837.5, SYMBOL_ZS_JCJ, data_dir=self.dir, ts_ms=ts))
        pts = load_today_points(SYMBOL_ZS_JCJ, data_dir=self.dir)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["ts"], ts)

    def test_same_minute_merged_backwards_compat_string(self):
        # 旧签名传入显示字符串 "09:30"，但去重键是真实采样分钟
        record_price_point(871.20, SYMBOL_AU9999, "09:30", data_dir=self.dir, ts_ms=_ts(16, 28))
        record_price_point(871.50, SYMBOL_AU9999, "09:30", data_dir=self.dir, ts_ms=_ts(16, 28, 30))
        pts = load_today_points(SYMBOL_AU9999, data_dir=self.dir)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["p"], 871.50)

    def test_out_of_order_same_minute_merge(self):
        t = _ts(10, 0)
        record_price_point(100.0, SYMBOL_AU9999, data_dir=self.dir, ts_ms=t + 5 * 60 * 1000)
        record_price_point(200.0, SYMBOL_AU9999, data_dir=self.dir, ts_ms=t)
        record_price_point(300.0, SYMBOL_AU9999, data_dir=self.dir, ts_ms=t + 10 * 1000)
        pts = load_today_points(SYMBOL_AU9999, data_dir=self.dir)
        # 10:00 两次合并（后写覆盖），10:05 一次
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0]["p"], 300.0)
        self.assertEqual(pts[1]["p"], 100.0)

    def test_legacy_points_migrated_from_local_t(self):
        day_file = self.dir / f"intraday-{dt.date.today().isoformat()}.json"
        day_file.write_text(
            '[{"t": "09:30", "p": 800.0, "s": "sina_au9999"}]',
            encoding="utf-8",
        )
        pts = load_today_points(SYMBOL_AU9999, data_dir=self.dir)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["s"], SYMBOL_AU9999)
        self.assertEqual(pts[0]["p"], 800.0)
        expected = int(dt.datetime.combine(dt.date.today(), dt.time(9, 30)).timestamp() * 1000)
        self.assertEqual(pts[0]["ts"], expected)

    def test_record_preserves_migrated_legacy_points(self):
        day_file = self.dir / f"intraday-{dt.date.today().isoformat()}.json"
        day_file.write_text(
            '[{"t": "09:30", "p": 800.0, "s": "tangdouz"}]',
            encoding="utf-8",
        )
        record_price_point(801.0, SYMBOL_AU9999, data_dir=self.dir, ts_ms=_ts(10, 0))
        pts = load_today_points(SYMBOL_AU9999, data_dir=self.dir)
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0]["p"], 800.0)
        self.assertEqual(pts[1]["p"], 801.0)


class TestDayBasis(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _quote(self, prev: float, op: float, price: float) -> QuoteData:
        return QuoteData(
            symbol=SYMBOL_ZS_JCJ, price=price, prev_close=prev, open_price=op,
            high=price, low=price, change=price - prev,
            change_pct=(price - prev) / prev * 100 if prev else 0.0,
            time_str="10:00", source_id="t", source_name="t",
        )

    def test_first_freeze_wins(self):
        self.assertTrue(freeze_day_basis(SYMBOL_ZS_JCJ, 833.01, 832.99, data_dir=self.dir))
        # 第二次（如备用源切换后）不覆盖
        freeze_day_basis(SYMBOL_ZS_JCJ, 999.0, 999.0, data_dir=self.dir)
        basis = get_day_basis(SYMBOL_ZS_JCJ, data_dir=self.dir)
        self.assertIsNotNone(basis)
        assert basis is not None
        self.assertEqual(basis["prev_close"], 833.01)
        self.assertEqual(basis["open"], 832.99)

    def test_apply_frozen_basis_stabilizes_delta(self):
        freeze_day_basis(SYMBOL_ZS_JCJ, 833.01, 832.99, data_dir=self.dir)
        # 备用源返回不同基准
        q = self._quote(prev=850.0, op=849.0, price=837.82)
        apply_frozen_basis(q, data_dir=self.dir)
        self.assertEqual(q.prev_close, 833.01)
        self.assertEqual(q.open_price, 832.99)
        self.assertAlmostEqual(q.change, 837.82 - 833.01, places=2)

    def test_apply_without_frozen_keeps_original(self):
        q = self._quote(prev=850.0, op=849.0, price=837.82)
        apply_frozen_basis(q, data_dir=self.dir)
        self.assertEqual(q.prev_close, 850.0)

    def test_invalid_prev_close_not_frozen(self):
        self.assertFalse(freeze_day_basis(SYMBOL_ZS_JCJ, 0.0, 100.0, data_dir=self.dir))
        self.assertIsNone(get_day_basis(SYMBOL_ZS_JCJ, data_dir=self.dir))


class TestSegmentation(unittest.TestCase):
    def test_gap_constant_reasonable(self):
        # 保留常量：全日等距绘图不再按缺口断线，但存储侧仍可复用该阈值
        self.assertGreaterEqual(SAMPLE_GAP_BREAK_SECONDS, 30 * 60)


if __name__ == "__main__":
    unittest.main()
