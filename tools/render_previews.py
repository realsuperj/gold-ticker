"""Render the production Mac view using explicitly illustrative data."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from AppKit import NSApplication, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSGraphicsContext, NSAffineTransform
from Foundation import NSMakeRect
from core.config import DEFAULT_CONFIG
from core.pricing import QuoteData
from core.storage import record_price_point
from mac.main import GoldCardView, calc_window_height


def render_to_png(view, output_path, scale=2):
    bounds = view.bounds()
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, int(bounds.size.width * scale), int(bounds.size.height * scale), 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0)
    context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    try:
        NSGraphicsContext.setCurrentContext_(context)
        transform = NSAffineTransform.transform()
        transform.scaleXBy_yBy_(scale, scale)
        transform.concat()
        view.displayRectIgnoringOpacity_inContext_(bounds, context)
    finally:
        NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    assert data.writeToFile_atomically_(str(output_path), True)
    print(f"Example data / production view: {output_path} ({rep.pixelsWide()}x{rep.pixelsHigh()})")


def main():
    NSApplication.sharedApplication()
    with tempfile.TemporaryDirectory(prefix="goldticker-previews-") as tmp:
        os.environ["GOLDTICKER_DATA_DIR"] = tmp
        import datetime as _dt
        import time as _time
        # 示例数据显式标注为非实时：采样时刻为今日 09:30 起每 45 分钟（本地时区）
        base = _dt.datetime.combine(_dt.date.today(), _dt.time(9, 30))
        start_ts = int(_time.mktime(base.timetuple())) * 1000
        step_ms = 45 * 60 * 1000
        for symbol, stem, values, prev in (
            ("zs_jcj", "zs", [868, 869.2, 867.5, 870.1, 872.8, 871.2, 873, 871.5], 868),
            ("xau_usd", "intl", [2740, 2743.5, 2741, 2736.2, 2738.5, 2731.8, 2730, 2735.6], 2740)):
            for i, value in enumerate(values):
                record_price_point(value, symbol, ts_ms=start_ts + i * step_ms)
            quote = QuoteData(symbol=symbol, price=values[-1], prev_close=prev, open_price=values[1],
                high=max(values), low=min(values), change=values[-1]-prev,
                change_pct=(values[-1]-prev)/prev*100, time_str="14:45", source_id="example", source_name="Example data")
            for lang in ("zh", "en"):
                cfg = dict(DEFAULT_CONFIG, language=lang, symbol=symbol)
                view = GoldCardView.alloc().initWithFrame_(NSMakeRect(0, 0, cfg["width"], calc_window_height(cfg)))
                view.set_controller(SimpleNamespace(config=cfg, current_quote=quote))
                output = REPO_ROOT / "docs" / f"preview-{stem}{'-en' if lang == 'en' else ''}.png"
                render_to_png(view, output)


if __name__ == "__main__":
    main()
