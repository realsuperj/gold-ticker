#!/usr/local/bin/python3.9
# -*- coding: utf-8 -*-
"""
GoldTicker — 浙商银行积存金桌面悬浮窗（macOS / PyObjC / AppKit）
无边框、半透明、置顶、圆角、可拖动；价格涨红跌绿，走势图可开关。
"""

import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime

import objc
from AppKit import (
    NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
    NSBezierPath, NSColor, NSFont, NSFontWeightBold, NSFontWeightMedium,
    NSGradient, NSGraphicsContext, NSImage, NSMenu, NSMenuItem, NSMutableParagraphStyle,
    NSOffState, NSOnState, NSPoint, NSRect, NSRectFill, NSScreen, NSTextAlignmentCenter,
    NSTextAlignmentRight, NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowCollectionBehaviorStationary,
    NSFloatingWindowLevel, NSNormalWindowLevel, NSBitmapImageFileTypePNG,
    NSForegroundColorAttributeName, NSFontAttributeName, NSParagraphStyleAttributeName,
    NSEvent, NSStatusBar, NSVariableStatusItemLength,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize, NSString

APP_DIR = os.path.expanduser("~/Library/Application Support/GoldTicker")
CFG_PATH = os.path.join(APP_DIR, "config.json")
PRICE_URL = "https://api.tangdouz.com/a/zsgold.php"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Safari/605.1.15")

DEFAULTS = {
    "showOnDesktop": True,
    "showChart": True,
    "showDetails": True,
    "alwaysOnTop": True,
    "opacity": 0.88,
    "refreshSeconds": 10,
    "width": 216,
    "fontScale": 1.0,
    "showMenuBarIcon": True,
    "changeBasis": "prevClose",
    "colorMode": "cny",
    "language": "auto",
    "dataSource": "auto",
    "windowX": -1,
    "windowY": -1,
}


def get_lang(cfg):
    """解析当前语言设置：'zh' 或 'en'"""
    l = str((cfg or {}).get("language", "auto")).lower()
    if l in ("zh", "cn", "zh_cn"):
        return "zh"
    if l in ("en", "english"):
        return "en"
    env_l = (os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")).lower()
    return "zh" if "zh" in env_l else "en"


# ------------------------------------------------------------------ 配置

def ensure_dir():
    try:
        os.makedirs(APP_DIR, exist_ok=True)
    except Exception:
        pass


def load_cfg():
    ensure_dir()
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        for k in DEFAULTS:
            if k in user:
                cfg[k] = user[k]
    except Exception:
        save_cfg(cfg)
    cfg["opacity"] = min(max(float(cfg["opacity"]), 0.25), 1.0)
    cfg["refreshSeconds"] = max(float(cfg["refreshSeconds"]), 2.0)
    cfg["width"] = min(max(float(cfg["width"]), 140.0), 480.0)
    cfg["fontScale"] = min(max(float(cfg["fontScale"]), 0.5), 2.0)
    return cfg


def save_cfg(cfg):
    ensure_dir()
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def window_height(cfg):
    h = 9 + 14 + 36 + 17
    if cfg["showDetails"]:
        h += 16
    if cfg["showChart"]:
        h += 2 + 48 + 12
    return h + 12


# ------------------------------------------------------------------ 行情

def _first_number(s):
    cur = ""
    for ch in s:
        if ch.isdigit() or ch == ".":
            cur += ch
        elif ch == "-" and not cur:
            cur += "-"
        elif cur:
            break
    try:
        return float(cur)
    except Exception:
        return None


def _field(text, key):
    for line in text.splitlines():
        if key + ":" in line or key + "：" in line:
            return line
    return None


def _ssl_context():
    """python.org 发行版默认不带根证书，这里显式绑定 CA 包"""
    import ssl
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
        return ctx
    except Exception:
        pass
    for path in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        try:
            if os.path.exists(path):
                ctx.load_verify_locations(path)
                return ctx
        except Exception:
            pass
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_SSL_CTX = None


# ------------------------------------------------------------------ 数据源

# (id, 卡片上显示的短名, 供应方, 取数函数) —— 顺序即自动切换的优先级
SOURCES = []


def _http_get(url, headers=None, timeout=5):
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = _ssl_context()
    hdr = {"User-Agent": UA}
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr)
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX).read()


def _num(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _pack(price, prev, op, high, low, tm, unit="元/克"):
    price = float(price)
    prev = float(prev or 0.0)
    if not prev:
        prev = float(op or price)
    change = price - prev
    pct = (change / prev * 100.0) if prev else 0.0
    return {
        "price": price, "prevClose": prev, "open": float(op or 0.0),
        "high": float(high or 0.0), "low": float(low or 0.0),
        "change": change, "changePct": pct, "time": tm or "--:--",
        "unit": unit, "error": None,
    }


def fetch_tangdouz():
    """浙商积存金，纯文本 key: value"""
    raw = _http_get(PRICE_URL)
    try:
        text = raw.decode("gb18030")
    except Exception:
        text = raw.decode("utf-8", "ignore")

    def val(key):
        line = _field(text, key)
        return _first_number(line) if line else None

    price = val("最新价格")
    if not price:
        raise ValueError("缺少最新价格")
    tm = "--:--"
    line = _field(text, "更新时间")
    if line:
        stamp = line.replace("更新时间", "").strip().split(" ")[-1]
        bits = stamp.split(":")
        if len(bits) >= 2:
            try:
                tm = "%02d:%02d" % (int(bits[0]), int(bits[1]))
            except Exception:
                tm = "--:--"
    return _pack(price, val("前收盘价"), val("开盘价"), val("最高价"), val("最低价"), tm)


def _sina(codes):
    raw = _http_get("https://hq.sinajs.cn/list=" + codes,
                    {"Referer": "https://finance.sina.com.cn"})
    try:
        text = raw.decode("gb18030")
    except Exception:
        text = raw.decode("utf-8", "ignore")
    out = {}
    for line in text.splitlines():
        if "var hq_str_" not in line or "=" not in line:
            continue
        name = line.split("hq_str_", 1)[1].split("=", 1)[0].strip()
        body = line.split('="', 1)[-1].rstrip('";')
        out[name] = body.split(",")
    return out


def fetch_sina_au9999():
    """上金所 Au99.99：0 代码 1 名称 2 品种 3 最新 5 昨收 7 最高 8 最低 9 开盘"""
    f = (_sina("SGE_AU9999").get("SGE_AU9999") or [])
    if len(f) < 10:
        raise ValueError("字段不足")
    tm = "--:--"
    if len(f) > 16 and f[16]:
        bits = f[16].split(" ")[-1].split(":")
        if len(bits) >= 2:
            tm = "%02d:%02d" % (int(bits[0]), int(bits[1]))
    return _pack(_num(f[3]), _num(f[5]), _num(f[9]), _num(f[7]), _num(f[8]), tm)


def fetch_sina_autd():
    """上金所黄金延期 Au(T+D)：0 最新 4 最高 5 最低 6 时间 7 昨收 8 开盘"""
    f = (_sina("gds_AUTD").get("gds_AUTD") or [])
    if len(f) < 9:
        raise ValueError("字段不足")
    tm = "--:--"
    bits = (f[6] or "").split(":")
    if len(bits) >= 2:
        tm = "%02d:%02d" % (int(bits[0]), int(bits[1]))
    return _pack(_num(f[0]), _num(f[7]), _num(f[8]), _num(f[4]), _num(f[5]), tm, "元/克")


def _pack_spread(base, spread):
    p = round(base["price"] + spread, 2)
    prev = round(base["prevClose"] + spread, 2) if base.get("prevClose") else 0.0
    op = round(base["open"] + spread, 2) if base.get("open") else 0.0
    h = round(base["high"] + spread, 2) if base.get("high") else 0.0
    l = round(base["low"] + spread, 2) if base.get("low") else 0.0
    chg = round(p - prev, 2) if prev else 0.0
    pct = round((chg / prev * 100.0), 2) if prev else 0.0
    return {
        "price": p, "prevClose": prev, "open": op,
        "high": h, "low": l, "change": chg, "changePct": pct,
        "time": base.get("time", "--:--"), "unit": "元/克", "error": None,
    }


def fetch_icbc_jcj():
    """工商银行积存金：基于上金所 Au99.99 基准价 + 0.80 元/克点差"""
    base = fetch_sina_au9999()
    return _pack_spread(base, 0.80)


def fetch_ccb_jcj():
    """建设银行积存金：基于上金所 Au99.99 基准价 + 0.75 元/克点差"""
    base = fetch_sina_au9999()
    return _pack_spread(base, 0.75)


def fetch_sina_xau_usd():
    """国际现货黄金 (XAU/USD)：单位 美元/盎司，展示原生国际金现货美元行情"""
    q = _sina("hf_XAU")
    f = q.get("hf_XAU") or []
    if len(f) < 9:
        raise ValueError("新浪国际金字段不足")
    tm = "--:--"
    bits = (f[6] or "").split(":")
    if len(bits) >= 2:
        tm = "%02d:%02d" % (int(bits[0]), int(bits[1]))
    # f[0]=最新, f[7]=昨收, f[8]=今开, f[4]=最高, f[5]=最低
    return _pack(_num(f[0]), _num(f[7]), _num(f[8]), _num(f[4]), _num(f[5]), tm, "美元/盎司")


# 约定的 5 大核心行情标的（严格遵循规范顺序与元数据定义）
SYMBOLS = [
    ("au9999", "上金所 Au99.99", "上海黄金交易所", "元/克", fetch_sina_au9999),
    ("zs_jcj", "浙商银行积存金", "浙商银行", "元/克", fetch_tangdouz),
    ("icbc_jcj", "工商银行积存金", "工商银行 (点差估算)", "元/克", fetch_icbc_jcj),
    ("ccb_jcj", "建设银行积存金", "建设银行 (点差估算)", "元/克", fetch_ccb_jcj),
    ("xau_usd", "国际现货黄金 (XAU/USD)", "伦敦金现货", "美元/盎司", fetch_sina_xau_usd),
]
SYMBOL_MAP = {s[0]: {"id": s[0], "name": s[1], "vendor": s[2], "unit": s[3], "fetch": s[4]} for s in SYMBOLS}
SYMBOL_IDS = [s[0] for s in SYMBOLS]
COOLDOWN = 180.0
_FAIL = {}


def normalize_symbol(key):
    """标的代码标准化，兼顾历史键名与默认回退"""
    if not key or key in ("auto", "sina_au9999", "sge_au9999"):
        return "au9999"
    if key == "tangdouz":
        return "zs_jcj"
    if key in ("sina_xau", "xau"):
        return "xau_usd"
    if key in SYMBOL_MAP:
        return key
    return "au9999"


def source_state():
    """给菜单用：返回 [(id, 名称, 供应方, 状态文字)]"""
    now = time.time()
    out = []
    for sid, name, vendor, _unit, _fn in SYMBOLS:
        st = _FAIL.get(sid) or {}
        if st.get("until", 0) > now:
            state = "失败 %d 次，冷却 %d 秒" % (st.get("count", 1), int(st["until"] - now))
        else:
            state = "正常"
        out.append((sid, name, vendor, state))
    return out


def fetch_price(cfg=None):
    """按配置取价：指定单一标的，主源失败时优雅降级并返回标准化行情"""
    cfg = cfg or {}
    want = normalize_symbol(cfg.get("dataSource"))
    order = [want]
    for sid in SYMBOL_IDS:
        if sid not in order:
            order.append(sid)

    now = time.time()
    tried = []
    for sid in order:
        info = SYMBOL_MAP.get(sid)
        if info is None:
            continue
        st = _FAIL.get(sid) or {}
        if len(order) > 1 and sid != want and st.get("until", 0) > now:
            tried.append("%s:冷却中" % info["name"])
            continue
        try:
            q = info["fetch"]()
            if not q.get("price"):
                raise ValueError("无价格")
            _FAIL.pop(sid, None)
            q["source"] = sid
            q["sourceName"] = info["name"]
            q["sourceVendor"] = info["vendor"]
            q["unit"] = info.get("unit") or q.get("unit") or "元/克"
            q["error"] = None
            return q
        except Exception as e:
            _FAIL[sid] = {"until": now + COOLDOWN,
                          "count": (st.get("count") or 0) + 1}
            tried.append("%s:%s" % (info["name"], str(e)[:30] or "失败"))
            if sid == want and want in ("icbc_jcj", "ccb_jcj"):
                # 银行积存金依赖上金所，若基准失败则跳出
                pass

    return {"price": 0.0, "error": "数据获取中…",
            "detail": "；".join(tried), "source": want,
            "sourceName": SYMBOL_MAP.get(want, {}).get("name", "上金所 Au99.99"),
            "unit": SYMBOL_MAP.get(want, {}).get("unit", "元/克")}


class IntradayStore:
    """当日分时采样，落盘跨重启保留"""

    def __init__(self):
        self.day = ""
        self.samples = []
        self.reload()

    def _path(self):
        return os.path.join(APP_DIR, "intraday-%s.json" % self.day)

    def reload(self):
        self.day = datetime.now().strftime("%Y-%m-%d")
        self.samples = []
        try:
            with open(self._path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.samples = data
        except Exception:
            self.samples = []

    def append(self, price, source="tangdouz"):
        if not price or price <= 0:
            return
        now = datetime.now()
        key = now.strftime("%Y-%m-%d")
        if key != self.day:
            self._rotate()
            self.day = key
            self.samples = []
        t = now.strftime("%H:%M")
        last_src = (self.samples[-1].get("s") or "tangdouz") if self.samples else source
        if self.samples and self.samples[-1]["t"] == t and last_src == source:
            self.samples[-1]["p"] = price
        else:
            self.samples.append({"t": t, "p": price, "s": source})
        try:
            ensure_dir()
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump(self.samples, f)
        except Exception:
            pass

    def _rotate(self):
        try:
            names = sorted(n for n in os.listdir(APP_DIR)
                           if n.startswith("intraday-") and n.endswith(".json"))
            for n in names[:-3]:
                os.remove(os.path.join(APP_DIR, n))
        except Exception:
            pass


# ------------------------------------------------------------------ 视图

UP_COLOR = (1.00, 0.34, 0.30)
DOWN_COLOR = (0.28, 0.87, 0.53)


def rgba(rgb, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(rgb[0], rgb[1], rgb[2], a)


def gray(v, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(v, v, v, a)



# ------------------------------------------------------------------ 绘制原语

def draw_text(view, s, x, top, w, h, size, color, bold=False, mono=False, align=0):
    scale = view.cfg["fontScale"] if view.cfg else 1.0
    sz = size * scale
    if mono:
        font = NSFont.monospacedDigitSystemFontOfSize_weight_(
            sz, NSFontWeightBold if bold else NSFontWeightMedium)
    else:
        font = NSFont.systemFontOfSize_weight_(sz, NSFontWeightBold if bold else 0.0)
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
        return float(q["open"]), "\u4eca\u5f00"
    return float(q.get("prevClose") or 0.0), "\u6628\u6536"


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
    """切换标的后，提取对应标的的走势采样点，自动补全 00:00 昨收基准起点，确保反映全天真实走势"""
    rows = view.samples or []
    sym = normalize_symbol((view.quote or {}).get("source"))
    cur_rows = [r for r in rows if normalize_symbol(r.get("s")) == sym]

    # 清洗：过滤异常脏数据 (如国际金曾混入元/克低价点)
    if sym == "xau_usd":
        cur_rows = [r for r in cur_rows if r.get("p", 0) > 1500]
    else:
        cur_rows = [r for r in cur_rows if r.get("p", 0) < 1500]

    # 如果是工行或建行，且自身专属采样不足，继承 Au99.99 或浙商的采样点并加上点差
    if sym in ("icbc_jcj", "ccb_jcj") and len(cur_rows) < 2:
        spread = 0.80 if sym == "icbc_jcj" else 0.75
        base_rows = [r for r in rows if normalize_symbol(r.get("s")) in ("au9999", "zs_jcj")]
        base_rows = [r for r in base_rows if r.get("p", 0) < 1500]
        if base_rows:
            cur_rows = [{"t": r["t"], "p": round(r["p"] + spread, 2), "s": sym} for r in base_rows]

    # 核心金融走势逻辑：无论哪个标的，若首个采样点不是 00:00，必须以昨收/开盘基准价作为今日 00:00 起始锚点！
    q = view.quote or {}
    base_p = q.get("prevClose") or q.get("open")
    if base_p and base_p > 0:
        if not cur_rows:
            if q.get("price"):
                cur_rows = [
                    {"t": "00:00", "p": base_p, "s": sym},
                    {"t": q.get("time", datetime.now().strftime("%H:%M")), "p": q["price"], "s": sym}
                ]
        elif cur_rows[0]["t"] != "00:00":
            # 在首部插入 00:00 基准点，保证走势图从全天起点连贯绘制到当前最新点
            cur_rows = [{"t": "00:00", "p": base_p, "s": sym}] + cur_rows

    return cur_rows


def draw_chart(view, x, y, w, h, tone):
    pts = [s["p"] for s in visible_samples(view)]
    if len(pts) < 2:
        draw_text(view, "今日走势累积中",
                  x, y + h / 2 - 6, w, 12, 8.5, gray(1.0, 0.30), align=2)
        return

    # 基准参考价（昨收或今开）
    prev = basis_of(view.cfg, view.quote or {})[0]

    # 关键定界：Y 轴范围把所有点与基准价 prev 共同纳入，这样基准虚线永远完整可见，涨跌相对关系一目了然
    all_vals = list(pts)
    if prev and prev > 0:
        all_vals.append(prev)
    lo, hi = min(all_vals), max(all_vals)
    inset = max((hi - lo) * 0.18, 0.05)
    lo -= inset
    hi += inset
    span = max(hi - lo, 0.001)
    n = len(pts)

    def px(i):
        return x + w * i / (n - 1)

    def py(v):
        return y + h - (v - lo) / span * h

    # 绘制基准参考虚线
    if prev and lo < prev < hi:
        yy = py(prev)
        dash = NSBezierPath.bezierPath()
        dash.moveToPoint_(NSMakePoint(x, yy))
        dash.lineToPoint_(NSMakePoint(x + w, yy))
        dash.setLineDash_count_phase_([2.0, 3.0], 2, 0.0)
        dash.setLineWidth_(0.8)
        gray(1.0, 0.22).setStroke()
        dash.stroke()

    fill = NSBezierPath.bezierPath()
    fill.moveToPoint_(NSMakePoint(x, y + h))
    for i, v in enumerate(pts):
        fill.lineToPoint_(NSMakePoint(px(i), py(v)))
    fill.lineToPoint_(NSMakePoint(x + w, y + h))
    fill.closePath()
    NSGraphicsContext.saveGraphicsState()
    fill.addClip()
    grad = NSGradient.alloc().initWithColors_([
        tone.colorWithAlphaComponent_(0.38),
        tone.colorWithAlphaComponent_(0.03),
    ])
    if grad is not None:
        grad.drawInRect_angle_(NSMakeRect(x, y, w, h), -90)
    NSGraphicsContext.restoreGraphicsState()

    line = NSBezierPath.bezierPath()
    line.moveToPoint_(NSMakePoint(px(0), py(pts[0])))
    for i in range(1, n):
        line.lineToPoint_(NSMakePoint(px(i), py(pts[i])))
    line.setLineWidth_(1.4)
    line.setLineJoinStyle_(1)
    line.setLineCapStyle_(1)
    tone.setStroke()
    line.stroke()

    dot = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(px(n - 1) - 2, py(pts[-1]) - 2, 4, 4))
    tone.setFill()
    dot.fill()


def draw_card(view):
    W = view.bounds().size.width
    H = view.bounds().size.height
    cfg = view.cfg
    pad = 11

    bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(0.5, 0.5, W - 1, H - 1), 14, 14)
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.07, 0.08, 0.10, 0.74).setFill()
    bg.fill()
    gray(1.0, 0.10).setStroke()
    bg.setLineWidth_(1.0)
    bg.stroke()

    q = view.quote or {}
    if not q.get("price"):
        draw_text(view, q.get("error", "正在获取积存金价格…"),
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
    dim2 = gray(1.0, 0.32)
    top = 9
    lang = get_lang(cfg)
    is_en = (lang == "en")

    # 标的名称与计量单位（遵循需求规范：国际金为 美元/盎司，国内现货及银行积存金为 元/克）
    sym_id = normalize_symbol(q.get("source"))
    if is_en:
        en_names = {
            "au9999": ("SGE · Au99.99", "CNY/g"),
            "zs_jcj": ("CZBank · Gold", "CNY/g"),
            "icbc_jcj": ("ICBC · Gold (Est. Spread)", "CNY/g"),
            "ccb_jcj": ("CCB · Gold (Est. Spread)", "CNY/g"),
            "xau_usd": ("Spot Gold · XAU/USD", "USD/oz"),
        }
        disp_name, disp_unit = en_names.get(sym_id, (q.get("sourceName") or "Gold", "USD/oz" if sym_id == "xau_usd" else "CNY/g"))
    else:
        disp_name = q.get("sourceName") or "上金所 Au99.99"
        disp_unit = q.get("unit") or ("美元/盎司" if sym_id == "xau_usd" else "元/克")

    draw_text(view, "%s · %s" % (disp_name, disp_unit),
              pad, top, W - pad * 2, 12, 9.5, gray(1.0, 0.55))
    top += 14

    price_size = 30.0 if W >= 200 else 26.0
    draw_text(view, "%.2f" % q["price"], pad - 1, top, W - pad * 2 + 2, 36,
              price_size, tone, bold=True, mono=True)
    top += 36

    # 涨跌变动文字（严格跟随配色方案 tone 联动，杜绝大字与标签红绿混搭）
    sign = "+" if up else ""
    draw_text(view, "%s%.2f   %s%.2f%%" % (sign, change, sign, pct),
              pad, top, W - pad * 2, 14, 11,
              tone.colorWithAlphaComponent_(0.92),
              bold=True, mono=True)
    top += 17

    if cfg and cfg["showDetails"]:
        colw = (W - pad * 2) / 3.0
        h_tag = "High" if is_en else "高"
        l_tag = "Low" if is_en else "低"
        b_tag = ("Open" if basis_label == "今开" else "Prev") if is_en else basis_label
        draw_text(view, "%s %.2f" % (h_tag, q.get("high", 0)), pad, top, colw, 12, 8.4, dim2, mono=True)
        draw_text(view, "%s %.2f" % (l_tag, q.get("low", 0)), pad + colw, top, colw, 12, 8.4, dim2, mono=True)
        draw_text(view, "%s %.2f" % (b_tag, basis), pad + colw * 2, top, colw, 12,
                  8.4, dim2, mono=True, align=1)
        top += 16

    if cfg and cfg["showChart"]:
        draw_chart(view, pad, top + 2, W - pad * 2, 48, tone)
        top += 50
        rows = visible_samples(view)
        if rows:
            draw_text(view, rows[0]["t"], pad, top, 80, 11, 8.5, dim2, mono=True)
            draw_text(view, rows[-1]["t"],
                      W - pad - 80, top, 80, 11, 8.5, dim2, mono=True, align=1)
        else:
            accum_text = "Accumulating trend..." if is_en else "今日走势累积中"
            draw_text(view, accum_text, pad, top,
                      W - pad * 2, 11, 8.5, dim2, align=2)


class TickerView(objc.lookUpClass("NSView")):
    """自绘卡片：标题 / 价格 / 涨跌 / 高·低·昨收 / 走势图"""

    def initWithFrame_(self, frame):
        self = objc.super(TickerView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.cfg = None
        self.quote = {}
        self.samples = []
        self.menu_provider = None
        self._drag_start = None
        self._drag_origin = None
        return self

    def isFlipped(self):
        return True

    def acceptsFirstResponder(self):
        return True

    def drawRect_(self, rect):
        draw_card(self)

    # ---------- 交互 ----------

    def mouseDown_(self, event):
        self._drag_start = NSEvent.mouseLocation()
        win = self.window()
        self._drag_origin = win.frame().origin if win else NSMakePoint(0, 0)

    def mouseDragged_(self, event):
        win = self.window()
        if win is None or self._drag_start is None:
            return
        m = NSEvent.mouseLocation()
        win.setFrameOrigin_(NSMakePoint(
            self._drag_origin.x + (m.x - self._drag_start.x),
            self._drag_origin.y + (m.y - self._drag_start.y)))

    def mouseUp_(self, event):
        win = self.window()
        if win is not None and self.cfg is not None:
            o = win.frame().origin
            self.cfg["windowX"] = float(o.x)
            self.cfg["windowY"] = float(o.y)
            save_cfg(self.cfg)

    def rightMouseDown_(self, event):
        if self.menu_provider is None:
            return
        menu = self.menu_provider()
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        menu.popUpMenuPositioningItem_atLocation_inView_(None, p, self)


# ------------------------------------------------------------------ 应用

class App(objc.lookUpClass("NSObject")):
    def init(self):
        self = objc.super(App, self).init()
        if self is None:
            return None
        self.cfg = load_cfg()
        self.store = IntradayStore()
        self.quote = {"price": 0.0, "error": "正在获取积存金价格…"}
        self.quote_cache = {}
        self.request_seq = 0
        self.busy = False
        self.window = None
        self.view = None
        self.timer = None
        self.status_item = None
        return self

    # ---------- 构建 ----------

    def start(self):
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        w = self.cfg["width"]
        h = window_height(self.cfg)
        x, y = self.initial_xy(w, h)

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), 0, NSBackingStoreBuffered, False)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(True)
        win.setLevel_(NSFloatingWindowLevel if self.cfg["alwaysOnTop"] else NSNormalWindowLevel)
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorFullScreenAuxiliary |
            NSWindowCollectionBehaviorStationary)
        win.setAlphaValue_(self.cfg["opacity"])
        win.setReleasedWhenClosed_(False)

        view = TickerView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        view.cfg = self.cfg
        view.quote = self.quote
        view.samples = self.store.samples
        view.menu_provider = self.build_menu
        win.setContentView_(view)
        self.style_layer(view)

        self.window = win
        self.view = view
        if self.cfg["showOnDesktop"]:
            win.orderFrontRegardless()

        self.sync_status_item()
        self.schedule()
        self.refresh()
        app.run()


    def style_layer(self, view):
        """透明窗口里必须让 Core Animation 铺底板，否则纯色填充会被窗口 alpha 吞掉"""
        try:
            view.setWantsLayer_(True)
            layer = view.layer()
            if layer is not None:
                layer.setBackgroundColor_(
                    NSColor.colorWithSRGBRed_green_blue_alpha_(0.09, 0.10, 0.13, 0.80).CGColor())
                layer.setCornerRadius_(14.0)
                layer.setMasksToBounds_(True)
        except Exception as e:
            print("layer style failed:", e)

    def initial_xy(self, w, h):
        x = self.cfg.get("windowX", -1)
        y = self.cfg.get("windowY", -1)
        if x != -1 and y != -1:
            return float(x), float(y)
        scr = NSScreen.mainScreen()
        vf = scr.visibleFrame()
        return (vf.origin.x + vf.size.width - w - 24,
                vf.origin.y + vf.size.height - h - 24)


    # ---------- 菜单栏图标 ----------

    def sync_status_item(self):
        if self.cfg.get("showMenuBarIcon"):
            if self.status_item is None:
                bar = NSStatusBar.systemStatusBar()
                self.status_item = bar.statusItemWithLength_(
                    NSVariableStatusItemLength)
                btn = self.status_item.button()
                if btn is not None:
                    btn.setTitle_("\u91d1 --")
                self.status_item.setMenu_(self.build_menu())
        else:
            if self.status_item is not None:
                NSStatusBar.systemStatusBar().removeStatusItem_(self.status_item)
                self.status_item = None
        self.update_status_title()

    def update_status_title(self):
        if self.status_item is None:
            return
        btn = self.status_item.button()
        if btn is None:
            return
        q = self.quote or {}
        prefix = "Au" if normalize_symbol(q.get("source")) == "xau_usd" else "\u91d1"
        if q.get("price"):
            change, pct, _, _ = delta_of(self.cfg, q)
            sign = "+" if change >= 0 else ""
            btn.setTitle_("%s %.2f %s%.2f%%" % (prefix, q["price"], sign, pct))
        else:
            btn.setTitle_("%s --" % prefix)

    # ---------- 布局 ----------

    def apply_layout(self):
        win = self.window
        if win is None:
            return
        w = self.cfg["width"]
        h = window_height(self.cfg)
        f = win.frame()
        top = f.origin.y + f.size.height
        win.setFrame_display_(NSMakeRect(f.origin.x, top - h, w, h), True)
        self.view.setFrame_(NSMakeRect(0, 0, w, h))
        self.view.cfg = self.cfg
        self.view.setNeedsDisplay_(True)
        win.setAlphaValue_(self.cfg["opacity"])
        win.setLevel_(NSFloatingWindowLevel if self.cfg["alwaysOnTop"] else NSNormalWindowLevel)
        if self.cfg["showOnDesktop"]:
            win.orderFrontRegardless()
            win.displayIfNeeded()
        else:
            win.orderOut_(None)

    # ---------- 数据 ----------

    def schedule(self):
        from Foundation import NSTimer, NSRunLoopCommonModes, NSRunLoop
        if self.timer is not None:
            self.timer.invalidate()
        t = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            float(self.cfg["refreshSeconds"]), self, "tick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(t, NSRunLoopCommonModes)
        self.timer = t

    def tick_(self, timer):
        self.refresh()

    @objc.python_method
    def refresh(self, force=False):
        if self.busy and not force:
            return
        self.busy = True
        self.request_seq += 1
        seq = self.request_seq
        cfg_copy = dict(self.cfg)
        threading.Thread(target=self.worker, args=(cfg_copy, seq), daemon=True).start()

    @objc.python_method
    def worker(self, cfg, seq):
        data = fetch_price(cfg)
        from PyObjCTools import AppHelper
        AppHelper.callAfter(self.apply_quote, data, seq)

    @objc.python_method
    def apply_quote(self, data, seq=None):
        self.busy = False
        # 竞态防护 1：丢弃过期请求序列号，确保旧线程迟来的响应绝不会覆盖新标的
        if seq is not None and seq != self.request_seq:
            return
        # 竞态防护 2：核验返回标的是否与当前用户选中的标的一致，不一致则仅写入缓存、绝不刷上视图
        cur_sym = normalize_symbol(self.cfg.get("dataSource"))
        data_sym = normalize_symbol(data.get("source"))
        if data.get("price"):
            self.quote_cache[data_sym] = data
            self.store.append(data["price"], data_sym)
            if data_sym == "au9999":
                self.store.append(round(data["price"] + 0.80, 2), "icbc_jcj")
                self.store.append(round(data["price"] + 0.75, 2), "ccb_jcj")

        if data_sym != cur_sym:
            return

        if data.get("price"):
            self.quote = data
            self.view.samples = self.store.samples
        elif not self.view.quote.get("price"):
            self.quote = data

        self.view.quote = self.quote
        self.view.setNeedsDisplay_(True)
        self.update_status_title()

    # ---------- 菜单 ----------

    def add_toggle(self, menu, title, key, selector, enabled=True):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setState_(NSOnState if self.cfg.get(key) else NSOffState)
        item.setEnabled_(enabled)
        item.setTarget_(self)
        menu.addItem_(item)

    def build_menu(self):
        m = NSMenu.alloc().init()
        m.setDelegate_(self)
        m.setAutoenablesItems_(False)
        self.fill_menu(m)
        return m

    def menuNeedsUpdate_(self, menu):
        """菜单弹出前按当前配置重填，保证勾选永远和真实状态一致"""
        self.fill_menu(menu)

    def fill_menu(self, m):
        m.removeAllItems()
        lang = get_lang(self.cfg)
        is_en = (lang == "en")

        # 1. 核心视图与窗口入口（双入口互锁防幽灵置灰）
        can_disable_desk = bool(self.cfg.get("showMenuBarIcon", True))
        can_disable_bar = bool(self.cfg.get("showOnDesktop", True))
        self.add_toggle(m, "Show on Desktop" if is_en else "显示到桌面", "showOnDesktop", "toggleDesktop:",
                        enabled=can_disable_desk or not self.cfg.get("showOnDesktop", True))
        self.add_toggle(m, "Show on Menu Bar / Tray" if is_en else "显示到菜单栏/托盘", "showMenuBarIcon", "toggleMenuBar:",
                        enabled=can_disable_bar or not self.cfg.get("showMenuBarIcon", True))
        self.add_toggle(m, "Always on Top" if is_en else "窗口置顶", "alwaysOnTop", "toggleTop:")
        m.addItem_(NSMenuItem.separatorItem())

        # 2. 视觉组件开关
        self.add_toggle(m, "Show Trend Chart" if is_en else "显示走势图", "showChart", "toggleChart:")
        self.add_toggle(m, "Show High/Low/Base Details" if is_en else "显示 高/低/基准价", "showDetails", "toggleDetails:")
        m.addItem_(NSMenuItem.separatorItem())

        # 3. 行情标的子菜单 (约定的 5 大核心标的：上金所、浙商、工行、建行、国际黄金)
        src = NSMenu.alloc().init()
        cur_src = normalize_symbol(self.cfg.get("dataSource"))
        for idx, (sid, name, vendor, _unit, _fn) in enumerate(SYMBOLS):
            if is_en:
                en_names = {
                    "au9999": "SGE Au99.99 (Spot)",
                    "zs_jcj": "CZBank Gold Accumulation",
                    "icbc_jcj": "ICBC Gold (Est. Spread)",
                    "ccb_jcj": "CCB Gold (Est. Spread)",
                    "xau_usd": "Spot Gold (XAU/USD)",
                }
                title = en_names.get(sid, name)
            else:
                title = "%s（%s）" % (name, vendor)
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "setSource:", "")
            it.setTag_(idx)
            it.setState_(NSOnState if cur_src == sid else NSOffState)
            it.setTarget_(self)
            src.addItem_(it)
        src_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Select Target" if is_en else "行情标的", "", "")
        src_root.setSubmenu_(src)
        m.addItem_(src_root)

        # 4. 涨跌对比基准
        basis = NSMenu.alloc().init()
        cur_open = self.cfg.get("changeBasis") == "open"
        basis_items = (
            (0, "Prev Close (Previous Trading Day)" if is_en else "昨收（上一交易日收盘）"),
            (1, "Open Price (Today's Opening)" if is_en else "今开（今日开盘价）")
        )
        for tag, title in basis_items:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "setBasis:", "")
            it.setTag_(tag)
            it.setState_(NSOnState if (1 if cur_open else 0) == tag else NSOffState)
            it.setTarget_(self)
            basis.addItem_(it)
        basis_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Change Basis" if is_en else "涨跌基准", "", "")
        basis_root.setSubmenu_(basis)
        m.addItem_(basis_root)

        # 5. 涨跌配色子菜单 (红涨绿跌 / 绿涨红跌)
        col_menu = NSMenu.alloc().init()
        cur_col = self.cfg.get("colorMode", "cny")
        col_items = (
            ("cny", "Red Up / Green Down (CN Default)" if is_en else "红涨绿跌 (国内习惯 - 默认)"),
            ("intl", "Green Up / Red Down (International)" if is_en else "绿涨红跌 (国际习惯)")
        )
        for tag, (cid, ctitle) in enumerate(col_items):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(ctitle, "setColorMode:", "")
            it.setTag_(tag)
            it.setState_(NSOnState if cur_col == cid else NSOffState)
            it.setTarget_(self)
            col_menu.addItem_(it)
        col_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Color Scheme" if is_en else "色彩偏好", "", "")
        col_root.setSubmenu_(col_menu)
        m.addItem_(col_root)

        # 语言切换 (Language)
        lang_menu = NSMenu.alloc().init()
        cur_lang_cfg = self.cfg.get("language", "auto")
        lang_items = (
            ("auto", "跟随系统 (Auto)" if not is_en else "Auto (System Default)"),
            ("zh", "简体中文 (Chinese)"),
            ("en", "English")
        )
        for tag, (lid, ltitle) in enumerate(lang_items):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(ltitle, "setLanguage:", "")
            it.setTag_(tag)
            it.setState_(NSOnState if cur_lang_cfg == lid else NSOffState)
            it.setTarget_(self)
            lang_menu.addItem_(it)
        lang_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Language (语言)", "", "")
        lang_root.setSubmenu_(lang_menu)
        m.addItem_(lang_root)

        m.addItem_(NSMenuItem.separatorItem())

        # 6. 刷新频率 (>= 10秒)
        rate = NSMenu.alloc().init()
        for sec in (10, 15, 30, 60, 300):
            title = ("%d Seconds" if is_en else "%d 秒") % sec
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "setRate:", "")
            it.setTag_(sec)
            it.setState_(NSOnState if int(self.cfg["refreshSeconds"]) == sec else NSOffState)
            it.setTarget_(self)
            rate.addItem_(it)
        rate_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Refresh Interval" if is_en else "刷新频率", "", "")
        rate_root.setSubmenu_(rate)
        m.addItem_(rate_root)

        # 7. 宽度与透明度
        size = NSMenu.alloc().init()
        for wdt in (180, 200, 216, 240, 280):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("%d pt" % wdt, "setWidth:", "")
            it.setTag_(wdt)
            it.setState_(NSOnState if int(self.cfg["width"]) == wdt else NSOffState)
            it.setTarget_(self)
            size.addItem_(it)
        size_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Card Width" if is_en else "卡片宽度", "", "")
        size_root.setSubmenu_(size)
        m.addItem_(size_root)

        opac = NSMenu.alloc().init()
        for pct in (60, 75, 88, 95, 100):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("%d%%" % pct, "setOpacity:", "")
            it.setTag_(pct)
            it.setState_(NSOnState if abs(self.cfg["opacity"] * 100 - pct) < 1 else NSOffState)
            it.setTarget_(self)
            opac.addItem_(it)
        opac_root = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Card Opacity" if is_en else "窗口透明度", "", "")
        opac_root.setSubmenu_(opac)
        m.addItem_(opac_root)

        m.addItem_(NSMenuItem.separatorItem())
        maint_items = (
            ("Reset Position (Top Right)" if is_en else "重置位置（右上角）", "resetPosition:"),
            ("Open Config Directory" if is_en else "打开配置文件夹", "openConfig:"),
            ("Reload Configuration" if is_en else "重新加载配置", "reloadConfig:")
        )
        for title, sel in maint_items:
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
            it.setTarget_(self)
            m.addItem_(it)
        m.addItem_(NSMenuItem.separatorItem())
        about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("About GoldTicker..." if is_en else "关于 GoldTicker...", "showAbout:", "")
        about_item.setTarget_(self)
        m.addItem_(about_item)
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit GoldTicker" if is_en else "退出", "quitApp:", "q")
        quit_item.setTarget_(self)
        m.addItem_(quit_item)
        return m

    # ---------- 动作 ----------

    def toggleDesktop_(self, sender):
        if self.cfg.get("showOnDesktop", True) and not self.cfg.get("showMenuBarIcon", True):
            return  # 唯一入口锁定
        self.cfg["showOnDesktop"] = not self.cfg["showOnDesktop"]
        save_cfg(self.cfg)
        self.apply_layout()

    def toggleMenuBar_(self, sender):
        if self.cfg.get("showMenuBarIcon", True) and not self.cfg.get("showOnDesktop", True):
            return  # 唯一入口锁定
        self.cfg["showMenuBarIcon"] = not self.cfg["showMenuBarIcon"]
        save_cfg(self.cfg)
        self.sync_status_item()

    def setColorMode_(self, sender):
        modes = ["cny", "intl"]
        tag = sender.tag()
        if 0 <= tag < len(modes):
            self.cfg["colorMode"] = modes[tag]
            save_cfg(self.cfg)
            self.view.setNeedsDisplay_(True)
            self.update_status_title()

    def setLanguage_(self, sender):
        langs = ["auto", "zh", "en"]
        tag = int(sender.tag())
        if 0 <= tag < len(langs):
            self.cfg["language"] = langs[tag]
            save_cfg(self.cfg)
            if self.view is not None:
                self.view.setNeedsDisplay_(True)
            self.update_status_title()

    def toggleChart_(self, sender):
        self.cfg["showChart"] = not self.cfg["showChart"]
        save_cfg(self.cfg)
        self.apply_layout()

    def toggleDetails_(self, sender):
        self.cfg["showDetails"] = not self.cfg["showDetails"]
        save_cfg(self.cfg)
        self.apply_layout()

    def toggleTop_(self, sender):
        self.cfg["alwaysOnTop"] = not self.cfg["alwaysOnTop"]
        save_cfg(self.cfg)
        self.apply_layout()

    def setSource_(self, sender):
        tag = int(sender.tag())
        if 0 <= tag < len(SYMBOLS):
            new_sym = SYMBOLS[tag][0]
            self.cfg["dataSource"] = new_sym
            save_cfg(self.cfg)

            # 1. 缓存优先毫秒渲染：若内存中已有该标的的最近行情，直接 0 延迟呈现！
            if new_sym in self.quote_cache and self.quote_cache[new_sym].get("price"):
                self.quote = dict(self.quote_cache[new_sym])
            else:
                self.quote = {
                    "price": 0.0,
                    "source": new_sym,
                    "sourceName": SYMBOLS[tag][1],
                    "unit": SYMBOLS[tag][3],
                    "error": "正在获取价格…",
                }

            if self.view is not None:
                self.view.quote = self.quote
                self.view.setNeedsDisplay_(True)
            self.update_status_title()

            # 2. 强制拉取最新数据：重置 busy 标记，force=True 递增序列号并发起新请求
            self.busy = False
            self.refresh(force=True)

    def setBasis_(self, sender):
        self.cfg["changeBasis"] = "open" if sender.tag() == 1 else "prevClose"
        save_cfg(self.cfg)
        if self.view is not None:
            self.view.setNeedsDisplay_(True)
        self.update_status_title()

    def setRate_(self, sender):
        self.cfg["refreshSeconds"] = float(sender.tag())
        save_cfg(self.cfg)
        self.schedule()

    def setWidth_(self, sender):
        self.cfg["width"] = float(sender.tag())
        save_cfg(self.cfg)
        self.apply_layout()

    def setOpacity_(self, sender):
        self.cfg["opacity"] = float(sender.tag()) / 100.0
        save_cfg(self.cfg)
        self.apply_layout()

    def resetPosition_(self, sender):
        vf = NSScreen.mainScreen().visibleFrame()
        w = self.cfg["width"]
        h = window_height(self.cfg)
        x = vf.origin.x + vf.size.width - w - 24
        y = vf.origin.y + vf.size.height - h - 24
        self.window.setFrameOrigin_(NSMakePoint(x, y))
        self.cfg["windowX"] = float(x)
        self.cfg["windowY"] = float(y)
        save_cfg(self.cfg)

    def openConfig_(self, sender):
        save_cfg(self.cfg)
        ensure_dir()
        os.system('open "%s"' % APP_DIR)

    def reloadConfig_(self, sender):
        self.cfg = load_cfg()
        self.store.reload()
        self.view.cfg = self.cfg
        self.view.samples = self.store.samples
        self.apply_layout()
        self.sync_status_item()
        self.schedule()
        self.refresh()

    def showAbout_(self, sender):
        from AppKit import NSAlert
        alert = NSAlert.alloc().init()
        alert.setMessageText_("关于 GoldTicker")
        info = (
            "GoldTicker 跨平台金价悬浮小组件 v1.0.0\n\n"
            "支持行情标的：\n"
            "• 上金所 Au99.99 现货基准 (元/克)\n"
            "• 浙商银行积存金 (元/克)\n"
            "• 工商银行积存金 (元/克，点差估算)\n"
            "• 建设银行积存金 (元/克，点差估算)\n"
            "• 国际现货黄金 XAU/USD (美元/盎司)\n\n"
            "【免责声明】\n"
            "本软件仅供个人行情参考与学习交流，不构成任何投资建议或交易依据。"
            "商业银行积存金价格基于基准行情或常规点差估算，实际成交以各银行客户端为准。"
            "数据来源于公开公共网络接口，存在网络传输延迟，据此操作风险自担。\n\n"
            "Copyright © 2026 realsuperj. MIT License."
        )
        alert.setInformativeText_(info)
        alert.addButtonWithTitle_("确定")
        alert.runModal()

    def quitApp_(self, sender):
        save_cfg(self.cfg)
        NSApplication.sharedApplication().terminate_(None)


# ------------------------------------------------------------------ 入口

def snapshot(path):
    """离屏渲染一张 PNG，用于检查外观"""
    cfg = load_cfg()
    q = fetch_price(cfg)
    store = IntradayStore()
    if q.get("price"):
        store.append(q["price"], q.get("source"))
    w = cfg["width"]
    h = window_height(cfg)
    view = TickerView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    view.cfg = cfg
    view.quote = q
    view.samples = store.samples

    view.setNeedsDisplay_(True)
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    ok = data.writeToFile_atomically_(path, True)
    print("snapshot", path, "ok" if ok else "failed",
          "price=%.2f" % q.get("price", 0),
          "samples=%d" % len(store.samples),
          "err=%s" % (q.get("error") or "-"))


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        out = sys.argv[sys.argv.index("--snapshot") + 1]
        snapshot(out)
        sys.exit(0)
    App.alloc().init().start()
