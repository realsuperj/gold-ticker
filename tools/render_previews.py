"""Render README previews from live quotes + today's real intraday points."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from AppKit import NSApplication, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSGraphicsContext, NSAffineTransform
from Foundation import NSMakeRect
from core.config import DEFAULT_CONFIG, get_app_data_dir
from core.constants import SYMBOL_XAU_USD, SYMBOL_ZS_JCJ
from core.pricing import default_engine
from core.storage import apply_frozen_basis, load_today_points
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
    print(f"Live preview: {output_path} ({rep.pixelsWide()}x{rep.pixelsHigh()})")


def main():
    # 使用本机真实分时目录，保证走势是当天实际采样
    os.environ.pop("GOLDTICKER_DATA_DIR", None)
    data_dir = get_app_data_dir()
    NSApplication.sharedApplication()

    targets = (
        (SYMBOL_ZS_JCJ, "zs"),
        (SYMBOL_XAU_USD, "intl"),
    )
    for symbol, stem in targets:
        pts = load_today_points(symbol, data_dir=data_dir)
        if len(pts) < 2:
            raise SystemExit(f"Need >=2 real intraday points for {symbol}, got {len(pts)} in {data_dir}")
        quote = default_engine.get_quote(symbol)
        if not quote or quote.price <= 0:
            raise SystemExit(f"Failed to fetch live quote for {symbol}: {getattr(quote, 'error', None)}")
        quote = apply_frozen_basis(quote, data_dir=data_dir)
        for lang in ("zh", "en"):
            cfg = dict(DEFAULT_CONFIG, language=lang, symbol=symbol, width=200, showChart=True, showDetails=True)
            view = GoldCardView.alloc().initWithFrame_(NSMakeRect(0, 0, cfg["width"], calc_window_height(cfg)))
            view.set_controller(SimpleNamespace(config=cfg, current_quote=quote))
            output = REPO_ROOT / "docs" / f"preview-{stem}{'-en' if lang == 'en' else ''}.png"
            render_to_png(view, output)
            print(f"  {symbol}/{lang}: price={quote.price} points={len(pts)}")


if __name__ == "__main__":
    main()
