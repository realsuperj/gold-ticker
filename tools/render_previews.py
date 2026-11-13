# -*- coding: utf-8 -*-
"""
生成高质量的 macOS 原生悬浮小组件中英文预览截图
输出：
- docs/preview-zs.png (中文 浙商积存金)
- docs/preview-intl.png (中文 国际现货黄金)
- docs/preview-zs-en.png (英文 CZBank Gold)
- docs/preview-intl-en.png (英文 Spot Gold XAU/USD)
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import objc
from AppKit import (
    NSApplication, NSBitmapImageFileTypePNG, NSBitmapImageRep,
    NSColor, NSGraphicsContext, NSImage, NSRect,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize

app = NSApplication.sharedApplication()

# 导入 app/goldticker.py 的渲染方法
from app.goldticker import (
    DEFAULTS, TickerView, draw_card,
)


class MockView:
    def __init__(self, cfg, quote, samples, w=216, h=146):
        self.cfg = cfg
        self.quote = quote
        self.samples = samples
        self._w = w
        self._h = h

    def bounds(self):
        return NSMakeRect(0, 0, self._w, self._h)


def render_to_png(view, output_path, scale=2.0):
    w = int(view._w * scale)
    h = int(view._h * scale)
    image = NSImage.alloc().initWithSize_(NSMakeSize(view._w, view._h))
    image.lockFocus()

    ctx = NSGraphicsContext.currentContext()
    ctx.setImageInterpolation_(2)  # High quality
    draw_card(view)

    image.unlockFocus()

    # 生成 Retina 高清 PNG
    rep = NSBitmapImageRep.alloc().initWithData_(image.TIFFRepresentation())
    png_data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    png_data.writeToFile_atomically_(output_path, True)
    print(f"Generated: {output_path}")


def main():
    docs_dir = os.path.join(REPO_ROOT, "docs")

    # 生成今日 00:00 到 15:30 的仿真走势点
    zs_samples = [
        {"t": "00:00", "p": 868.00, "s": "zs_jcj"},
        {"t": "09:30", "p": 869.20, "s": "zs_jcj"},
        {"t": "10:15", "p": 867.50, "s": "zs_jcj"},
        {"t": "11:30", "p": 870.10, "s": "zs_jcj"},
        {"t": "13:30", "p": 872.80, "s": "zs_jcj"},
        {"t": "14:15", "p": 871.20, "s": "zs_jcj"},
        {"t": "15:00", "p": 873.00, "s": "zs_jcj"},
        {"t": "15:30", "p": 871.50, "s": "zs_jcj"},
    ]

    intl_samples = [
        {"t": "00:00", "p": 2740.00, "s": "xau_usd"},
        {"t": "04:00", "p": 2743.50, "s": "xau_usd"},
        {"t": "08:30", "p": 2741.00, "s": "xau_usd"},
        {"t": "11:00", "p": 2736.20, "s": "xau_usd"},
        {"t": "13:45", "p": 2738.50, "s": "xau_usd"},
        {"t": "14:30", "p": 2731.80, "s": "xau_usd"},
        {"t": "15:15", "p": 2730.00, "s": "xau_usd"},
        {"t": "15:30", "p": 2735.60, "s": "xau_usd"},
    ]

    # 1. 中文版 - 浙商银行积存金
    cfg_zh = dict(DEFAULTS)
    cfg_zh.update({"language": "zh", "colorMode": "cny", "showChart": True, "showDetails": True, "width": 216})
    q_zs_zh = {
        "price": 871.50, "prevClose": 868.00, "open": 869.00,
        "high": 873.00, "low": 867.00, "change": 3.50, "changePct": 0.40,
        "source": "zs_jcj", "sourceName": "浙商银行 · 积存金", "unit": "元/克",
    }
    view_zs_zh = MockView(cfg_zh, q_zs_zh, zs_samples)
    render_to_png(view_zs_zh, os.path.join(docs_dir, "preview-zs.png"))

    # 2. 中文版 - 国际现货黄金 XAU/USD (国内习惯：下跌为绿)
    q_intl_zh = {
        "price": 2735.60, "prevClose": 2740.00, "open": 2742.00,
        "high": 2745.00, "low": 2730.00, "change": -4.40, "changePct": -0.16,
        "source": "xau_usd", "sourceName": "国际现货黄金 · XAU/USD", "unit": "美元/盎司",
    }
    view_intl_zh = MockView(cfg_zh, q_intl_zh, intl_samples)
    render_to_png(view_intl_zh, os.path.join(docs_dir, "preview-intl.png"))

    # 3. 英文版 - CZBank Gold (language="en")
    cfg_en = dict(DEFAULTS)
    cfg_en.update({"language": "en", "colorMode": "cny", "showChart": True, "showDetails": True, "width": 216})
    q_zs_en = {
        "price": 871.50, "prevClose": 868.00, "open": 869.00,
        "high": 873.00, "low": 867.00, "change": 3.50, "changePct": 0.40,
        "source": "zs_jcj", "sourceName": "CZBank · Gold", "unit": "CNY/g",
    }
    view_zs_en = MockView(cfg_en, q_zs_en, zs_samples)
    render_to_png(view_zs_en, os.path.join(docs_dir, "preview-zs-en.png"))

    # 4. 英文版 - Spot Gold XAU/USD (language="en")
    q_intl_en = {
        "price": 2735.60, "prevClose": 2740.00, "open": 2742.00,
        "high": 2745.00, "low": 2730.00, "change": -4.40, "changePct": -0.16,
        "source": "xau_usd", "sourceName": "Spot Gold · XAU/USD", "unit": "USD/oz",
    }
    view_intl_en = MockView(cfg_en, q_intl_en, intl_samples)
    render_to_png(view_intl_en, os.path.join(docs_dir, "preview-intl-en.png"))


if __name__ == "__main__":
    main()
