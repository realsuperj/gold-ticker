"""验证唯一真源 shared/spec.json 与各端引用的一致性。"""
import json
import unittest
from pathlib import Path

from core.config import DEFAULT_CONFIG, VALID_REFRESH_INTERVALS
from core.constants import DEFAULT_BANK_SPREADS, DISCLAIMER_CN, DISCLAIMER_EN, SUPPORTED_SYMBOLS, SYMBOL_META
from core.i18n import TRANSLATIONS
from core.product import COPYRIGHT, GITHUB_URL, PRODUCT_NAME, VERSION, load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestSharedSpecSingleSource(unittest.TestCase):
    def test_spec_consistency_across_modules(self):
        spec = load_spec()
        self.assertEqual(VERSION, spec["product"]["version"])
        self.assertEqual(PRODUCT_NAME, spec["product"]["name"])
        self.assertEqual(COPYRIGHT, spec["product"]["copyright"])
        self.assertEqual(GITHUB_URL, spec["product"]["githubUrl"])
        self.assertEqual(DISCLAIMER_CN, spec["disclaimers"]["zh"])
        self.assertEqual(DISCLAIMER_EN, spec["disclaimers"]["en"])
        self.assertEqual(list(SUPPORTED_SYMBOLS), [s["id"] for s in spec["symbols"]])
        self.assertEqual(DEFAULT_BANK_SPREADS["icbc_jcj"], 0.80)
        self.assertEqual(DEFAULT_BANK_SPREADS["ccb_jcj"], 0.75)
        self.assertEqual(list(VALID_REFRESH_INTERVALS), spec["options"]["refreshIntervals"])
        self.assertEqual(TRANSLATIONS["menu_language"]["en"], "Language (语言)")
        self.assertEqual(spec["defaults"]["winWidth"], 136)
        self.assertEqual(spec["defaults"]["macWidth"], 216)
        self.assertEqual(spec["options"]["winWidths"][0], 120)

    def test_native_targets_consume_shared_spec(self):
        csproj = (REPO_ROOT / "windows-wpf" / "GoldTicker.Wpf.csproj").read_text(encoding="utf-8")
        self.assertIn("shared\\spec.json", csproj)
        self.assertIn("GoldTicker.spec.json", csproj)
        self.assertIn(VERSION, csproj)

        objc_src = (REPO_ROOT / "mac-native" / "GoldTicker.m").read_text(encoding="utf-8")
        self.assertIn('pathForResource:@"spec" ofType:@"json"', objc_src)
        self.assertIn("checkUpdate", objc_src)
        self.assertNotIn("1144", objc_src)


if __name__ == "__main__":
    unittest.main()
