"""Original compact Mac card visuals, backed by shared core data."""
import datetime as _dt

from AppKit import (NSColor, NSFont, NSFontWeightBold, NSFontWeightMedium,
    NSMutableParagraphStyle, NSFontAttributeName, NSForegroundColorAttributeName,
    NSParagraphStyleAttributeName, NSBezierPath, NSGradient)
from Foundation import NSString, NSMakeRect, NSMakePoint
from core.i18n import resolve_language, t

UP_COLOR = (0.96, 0.28, 0.28)
DOWN_COLOR = (0.18, 0.80, 0.44)


def get_lang(cfg):
    return resolve_language(cfg.get("language", "auto"))


def normalize_symbol(symbol):
    return symbol


def rgba(rgb, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], a)


def gray(v, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(v, v, v, a)


def draw_text(view, s, x, top, w, h, size, color, bold=False, mono=False, align=0):
    scale = view.cfg.get("fontScale", 1.0) if view.cfg else 1.0
    sz = size * scale
    if mono:
        font = NSFont.monospacedDigitSystemFontOfSize_weight_(
            sz, NSFontWeightBold if bold else NSFontWeightMedium)
    else:
        font = NSFont.systemFontOfSize_weight_(sz, NSFontWeightBold if bold else 0.0)
    text = NSString.stringWithString_(s)
    measured = text.sizeWithAttributes_({NSFontAttributeName: font}).width
    if measured > w:
        font = NSFont.fontWithDescriptor_size_(font.fontDescriptor(), sz * w / measured)
    ps = NSMutableParagraphStyle.alloc().init()
    ps.setAlignment_(align)
    ps.setLineBreakMode_(4)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: ps,
    }
    NSString.stringWithString_(s).drawInRect_withAttributes_(
        NSMakeRect(x, top, w, h), attrs)


def basis_of(cfg, q):
    """涨跌基准：昨收（上一交易日收盘）或今开"""
    if cfg and cfg.get("changeBasis") == "open" and q.get("open"):
        return float(q["open"]), "今开"
    return float(q.get("prevClose") or 0.0), "昨收"


def delta_of(cfg, q):
    """返回 (涨跌额, 涨跌幅, 基准价, 基准名)"""
    price = float(q.get("price") or 0.0)
    basis, label = basis_of(cfg, q)
    if (cfg or {}).get("changeBasis") == "open" or not q.get("change"):
        change = price - basis if basis else 0.0
        pct = (change / basis * 100.0) if basis else 0.0
    else:
        change = float(q.get("change") or 0.0)
        pct = float(q.get("changePct") or 0.0)
    return change, pct, basis, label


def visible_samples(view):
    return [p for p in view.samples if p.get("p", 0) > 0 and p.get("ts")]


def draw_chart(view, x, y, w, h, tone):
    """当日走势：采样点等距铺满（看全日形态），不做真实时间轴拉伸。"""
    samples = visible_samples(view)
    if len(samples) < 2:
        mid = y + h / 2.0
        dash = NSBezierPath.bezierPath()
        dash.moveToPoint_(NSMakePoint(x, mid))
        dash.lineToPoint_(NSMakePoint(x + w, mid))
        dash.setLineDash_count_phase_([4.0, 4.0], 2, 0.0)
        dash.setLineWidth_(1.0)
        gray(1.0, 0.15).setStroke()
        dash.stroke()
        return

    prev = basis_of(view.cfg, view.quote or {})[0]
    prices = [s["p"] for s in samples]
    all_vals = list(prices) + ([prev] if prev and prev > 0 else [])
    lo, hi = min(all_vals), max(all_vals)
    if abs(hi - lo) < 1e-5:
        lo -= 1.0
        hi += 1.0
    inset = max((hi - lo) * 0.12, 0.05)
    lo -= inset
    hi += inset
    span = max(hi - lo, 0.001)
    step_x = w / float(len(prices) - 1)

    def py(v):
        return y + h - (v - lo) / span * h

    if prev and lo < prev < hi:
        yy = py(prev)
        dash = NSBezierPath.bezierPath()
        dash.moveToPoint_(NSMakePoint(x, yy))
        dash.lineToPoint_(NSMakePoint(x + w, yy))
        dash.setLineDash_count_phase_([2.0, 3.0], 2, 0.0)
        dash.setLineWidth_(0.8)
        gray(1.0, 0.22).setStroke()
        dash.stroke()

    line = NSBezierPath.bezierPath()
    points = []
    for idx, price in enumerate(prices):
        pt = NSMakePoint(x + idx * step_x, py(price))
        points.append(pt)
        if idx == 0:
            line.moveToPoint_(pt)
        else:
            line.lineToPoint_(pt)

    # flipped 视图：底边是 y+h；先铺渐变再描线
    fill = NSBezierPath.bezierPath()
    fill.moveToPoint_(points[0])
    for pt in points[1:]:
        fill.lineToPoint_(pt)
    fill.lineToPoint_(NSMakePoint(points[-1].x, y + h))
    fill.lineToPoint_(NSMakePoint(points[0].x, y + h))
    fill.closePath()
    grad = NSGradient.alloc().initWithStartingColor_endingColor_(
        tone.colorWithAlphaComponent_(0.22),
        tone.colorWithAlphaComponent_(0.02),
    )
    # flipped 下 90° 朝向 +y（视觉向下），自曲线淡到图表底
    grad.drawInBezierPath_angle_(fill, 90.0)

    line.setLineWidth_(1.5)
    line.setLineJoinStyle_(1)
    line.setLineCapStyle_(1)
    tone.setStroke()
    line.stroke()

    lx, ly = points[-1].x, points[-1].y
    dot = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(lx - 2, ly - 2, 4, 4))
    tone.setFill()
    dot.fill()


def draw_card(view):
    W = view.bounds().size.width
    H = view.bounds().size.height
    cfg = view.cfg
    pad = 14

    bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(0.5, 0.5, W - 1, H - 1), 12, 12)
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.08, 0.11, 0.16, cfg.get("opacity", 0.88)).setFill()
    bg.fill()
    gray(1.0, 0.12).setStroke()
    bg.setLineWidth_(1.0)
    bg.stroke()

    q = view.quote or {}
    if not q.get("price"):
        draw_text(view, t("fetch_error" if q.get("error") else "refreshing", get_lang(cfg)),
                  pad, H / 2 - 16, W - pad * 2, 16, 10.5, gray(1.0, 0.62), align=2)
        detail = (q.get("detail") or "").strip()
        if detail:
            draw_text(view, detail[:46], pad, H / 2 + 2, W - pad * 2, 14, 8.0,
                      gray(1.0, 0.34), align=2)
        return

    change, pct, basis, basis_label = delta_of(cfg, q)
    up = change >= 0
    color_mode = cfg.get("colorMode", "cny")
    if color_mode == "cny":
        tone = rgba(UP_COLOR) if up else rgba(DOWN_COLOR)
    else:
        tone = rgba(DOWN_COLOR) if up else rgba(UP_COLOR)
    top = 9
    lang = get_lang(cfg)
    is_en = (lang == "en")

    sym_id = normalize_symbol(q.get("source"))
    if is_en:
        en_names = {
            "au9999": ("SGE · Au99.99", "CNY/g"),
            "zs_jcj": ("CZBank · Gold", "CNY/g"),
            "icbc_jcj": ("ICBC · Gold (Est. Spread)", "CNY/g"),
            "ccb_jcj": ("CCB · Gold (Est. Spread)", "CNY/g"),
            "xau_usd": ("Spot Gold · XAU/USD", "USD/oz"),
        }
        disp_name, disp_unit = en_names.get(
            sym_id, (q.get("sourceName") or "Gold", "USD/oz" if sym_id == "xau_usd" else "CNY/g"))
    else:
        disp_name = q.get("sourceName") or "上金所 Au99.99"
        disp_unit = q.get("unit") or ("美元/盎司" if sym_id == "xau_usd" else "元/克")

    draw_text(view, "%s · %s" % (disp_name, disp_unit),
              pad, top, W - pad * 2, 12, 11.0, gray(1.0, 0.70))
    top += 14

    price_size = 28.0 if W >= 200 else 26.0
    draw_text(view, "%.2f" % q["price"], pad - 1, top, W - pad * 2 + 2, 34,
              price_size, tone, bold=True, mono=True)
    top += 34

    sign = "+" if up else ""
    draw_text(view, "%s%.2f  (%s%.2f%%)" % (sign, change, sign, pct),
              pad, top, W - pad * 2, 14, 12,
              tone.colorWithAlphaComponent_(0.95),
              bold=False, mono=True)
    top += 16

    if cfg and cfg["showDetails"]:
        h_tag = "High" if is_en else "高"
        l_tag = "Low" if is_en else "低"
        b_tag = ("Open" if basis_label == "今开" else "Prev") if is_en else basis_label
        detail = "%s %.2f  %s %.2f  %s %.2f" % (
            h_tag, q.get("high", 0), l_tag, q.get("low", 0), b_tag, basis)
        draw_text(view, detail, pad, top, W - pad * 2, 12, 10.0, gray(1.0, 0.50), mono=True)
        top += 16

    if cfg and cfg["showChart"]:
        draw_chart(view, pad, top + 2, W - pad * 2, 44, tone)
        top += 48
        rows = visible_samples(view)
        if rows:
            first_t = _dt.datetime.fromtimestamp(rows[0]["ts"] / 1000.0).strftime("%H:%M")
            last_t = _dt.datetime.fromtimestamp(rows[-1]["ts"] / 1000.0).strftime("%H:%M")
            draw_text(view, first_t, pad, top, 80, 11, 8.5, gray(1.0, 0.38), mono=True)
            draw_text(view, last_t,
                      W - pad - 80, top, 80, 11, 8.5, gray(1.0, 0.38), mono=True, align=1)
