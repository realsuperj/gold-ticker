# -*- coding: utf-8 -*-
import unittest
from core.i18n import detect_system_language, resolve_language, t


class TestI18n(unittest.TestCase):
    def test_resolve_language(self):
        self.assertEqual(resolve_language("zh"), "zh")
        self.assertEqual(resolve_language("zh_CN"), "zh")
        self.assertEqual(resolve_language("en"), "en")
        self.assertEqual(resolve_language("english"), "en")
        self.assertIn(resolve_language("auto"), ("zh", "en"))

    def test_translations(self):
        self.assertEqual(t("prev_close", "zh"), "昨收")
        self.assertEqual(t("prev_close", "en"), "Prev")
        self.assertEqual(t("high", "zh"), "最高")
        self.assertEqual(t("high", "en"), "High")
        self.assertEqual(t("unit_cny_g", "zh"), "元/克")
        self.assertEqual(t("unit_cny_g", "en"), "CNY/g")
        self.assertEqual(t("unit_usd_oz", "zh"), "美元/盎司")
        self.assertEqual(t("unit_usd_oz", "en"), "USD/oz")

    def test_fallback(self):
        self.assertEqual(t("non_existing_key_xyz", "zh"), "non_existing_key_xyz")


if __name__ == "__main__":
    unittest.main()
