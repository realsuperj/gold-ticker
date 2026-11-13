"""Offline native smoke path, always isolated from user data."""
import json
import os
from pathlib import Path
import sys
import tempfile


def run_smoke():
    with tempfile.TemporaryDirectory(prefix="goldticker-smoke-") as tmp:
        os.environ["GOLDTICKER_DATA_DIR"] = tmp
        from core.product import resource_path, VERSION
        from core.config import load_config
        assert resource_path().is_file()
        cfg = load_config()
        if sys.platform == "darwin":
            from AppKit import NSApplication, NSStatusBar
            from mac.main import GoldTickerApp
            NSApplication.sharedApplication()
            ticker = GoldTickerApp()
            ticker.setup_ui()
            for lang, prefix in (("zh", "金"), ("en", "Au")):
                ticker.config["language"] = lang
                ticker.apply_all_config()
                ticker.window.display()
                assert ticker.status_item.button().title() == prefix + " --"
                alert = ticker.menu_controller.make_alert("about_title", VERSION)
                assert alert.icon() is not None
                assert alert.buttons()[0].title() == ("确定" if lang == "zh" else "OK")
            ticker.window.orderOut_(None)
            NSStatusBar.systemStatusBar().removeStatusItem_(ticker.status_item)
        elif sys.platform == "win32":
            from unittest.mock import patch
            from windows.main import GoldTickerWindowsApp
            with patch.object(GoldTickerWindowsApp, "_start_fetch_loop"), patch.object(GoldTickerWindowsApp, "_init_tray"):
                ticker = GoldTickerWindowsApp()
                for lang, prefix in (("zh", "金"), ("en", "Au")):
                    ticker._set_language(lang)
                    ticker.root.update()
                    assert ticker.lbl_prefix.cget("text") == prefix
                ticker.quit()
        else:
            raise RuntimeError("Native smoke requires macOS or Windows")
        print(json.dumps({"smoke": "passed", "platform": sys.platform,
              "frozen": bool(getattr(sys, "frozen", False)), "version": VERSION,
              "resource": str(resource_path()), "data_isolated": True}))
