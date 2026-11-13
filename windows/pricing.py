"""GoldTicker Windows pricing and intraday persistence (no macOS imports)."""

import json
import os
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / "GoldTicker"
CFG_PATH = APP_DIR / "config.json"
PRICE_URL = "https://api.tangdouz.com/a/zsgold.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
DEFAULTS = {
    "showOnDesktop": True, "showChart": True, "showDetails": True,
    "alwaysOnTop": True, "opacity": 0.88, "refreshSeconds": 10,
    "width": 216, "fontScale": 1.0, "showMenuBarIcon": False,
    "showTaskbarPrice": True,
    "changeBasis": "prevClose", "dataSource": "auto",
    "windowX": -1, "windowY": -1,
}
SOURCE_NAMES = {
    "tangdouz": ("浙商积存金", "糖豆子"),
    "sina_au9999": ("Au99.99", "新浪财经"),
    "sina_autd": ("Au(T+D)", "新浪财经"),
    "sina_xau": ("伦敦金折算", "新浪财经"),
}
COOLDOWN = 180
OUNCE_IN_GRAM = 31.1034768


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    for key, low, high in (("opacity", .25, 1), ("refreshSeconds", 2, 3600),
                            ("width", 140, 480), ("fontScale", .5, 2)):
        try:
            cfg[key] = min(high, max(low, float(cfg[key])))
        except (ValueError, TypeError):
            cfg[key] = DEFAULTS[key]
    for key in ("showOnDesktop", "showChart", "showDetails", "alwaysOnTop", "showMenuBarIcon", "showTaskbarPrice"):
        if not isinstance(cfg[key], bool):
            cfg[key] = DEFAULTS[key]
    for key in ("windowX", "windowY"):
        try:
            cfg[key] = int(cfg[key])
        except (ValueError, TypeError, OverflowError):
            cfg[key] = -1
    if cfg["changeBasis"] not in ("open", "prevClose"):
        cfg["changeBasis"] = "prevClose"
    if cfg["dataSource"] not in ("auto", *SOURCE_NAMES):
        cfg["dataSource"] = "auto"
    return cfg


def save_cfg(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CFG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CFG_PATH)


def _get(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=12, context=context) as response:
        data = response.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", errors="replace")


def _number(text):
    match = re.search(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", str(text))
    return float(match.group().replace(",", "")) if match else 0.0


def _pack(price, prev, opened, high, low, stamp):
    price = float(price)
    if price <= 0:
        raise ValueError("价格无效")
    prev = float(prev or opened or price)
    return {"price": price, "prevClose": prev, "open": float(opened or 0),
            "high": float(high or 0), "low": float(low or 0),
            "change": price - prev, "changePct": (price - prev) / prev * 100,
            "time": stamp or "--:--", "error": None}


def _clock(text):
    match = re.search(r"(?:^|\s)(\d{1,2}):(\d{2})(?::\d{2})?", text)
    return f"{int(match[1]):02d}:{int(match[2]):02d}" if match else "--:--"


def fetch_tangdouz():
    fields = {}
    for line in _get(PRICE_URL).splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            key, sep, value = line.partition("：")
        if sep:
            fields[key.strip()] = value.strip()
    return _pack(*(_number(fields.get(k, "")) for k in
                   ("最新价格", "前收盘价", "开盘价", "最高价", "最低价")),
                 _clock(fields.get("更新时间", "")))


def _sina(codes):
    raw = _get("https://hq.sinajs.cn/list=" + codes,
               {"Referer": "https://finance.sina.com.cn"})
    return {name: body.split(",") for name, body in
            re.findall(r'var hq_str_([\w]+)="([^"]*)"', raw)}


def fetch_sina_au9999():
    f = _sina("SGE_AU9999").get("SGE_AU9999", [])
    if len(f) < 10:
        raise ValueError("字段不足")
    return _pack(*(_number(f[i]) for i in (3, 5, 9, 7, 8)),
                 _clock(f[16]) if len(f) > 16 else "--:--")


def fetch_sina_autd():
    f = _sina("gds_AUTD").get("gds_AUTD", [])
    if len(f) < 9:
        raise ValueError("字段不足")
    return _pack(*(_number(f[i]) for i in (0, 7, 8, 4, 5)), _clock(f[6]))


def fetch_sina_xau():
    q = _sina("hf_XAU,fx_susdcny")
    f, fx = q.get("hf_XAU", []), q.get("fx_susdcny", [])
    if len(f) < 9 or len(fx) < 2 or _number(fx[1]) <= 0:
        raise ValueError("金价或汇率字段不足")
    def convert(index):
        return _number(f[index]) * _number(fx[1]) / OUNCE_IN_GRAM
    return _pack(*(convert(i) for i in (0, 7, 8, 4, 5)), _clock(f[6]))


FETCHERS = {"tangdouz": fetch_tangdouz, "sina_au9999": fetch_sina_au9999,
            "sina_autd": fetch_sina_autd, "sina_xau": fetch_sina_xau}


class PriceFetcher:
    def __init__(self):
        self.failures = {}

    def fetch(self, source="auto"):
        tried = []
        for sid in SOURCE_NAMES if source == "auto" else (source,):
            name, vendor = SOURCE_NAMES[sid]
            failed = self.failures.get(sid, {})
            if source == "auto" and failed.get("until", 0) > time.monotonic():
                tried.append(f"{name}:冷却中")
                continue
            try:
                quote = FETCHERS[sid]()
                self.failures.pop(sid, None)
                quote.update(source=sid, sourceName=name, sourceVendor=vendor)
                return quote
            except (OSError, ValueError, KeyError, IndexError) as exc:
                self.failures[sid] = {"until": time.monotonic() + COOLDOWN,
                                      "count": failed.get("count", 0) + 1}
                tried.append(f"{name}:{str(exc)[:30]}")
        return {"price": 0, "error": ("数据源暂时都不可用，重试中…" if source == "auto"
                                       else "这个数据源连不上，重试中…"),
                "detail": "；".join(tried)}


class IntradayStore:
    """Local calendar day partitions; minute samples retain source identity."""

    def __init__(self):
        self.day = ""
        self.samples = []
        self.reload()

    def _path(self):
        return APP_DIR / f"intraday-{self.day}.json"

    def reload(self):
        self.day = datetime.now().astimezone().date().isoformat()
        try:
            rows = json.loads(self._path().read_text(encoding="utf-8"))
            self.samples = [r for r in rows if isinstance(r, dict) and
                            isinstance(r.get("p"), (int, float)) and r["p"] > 0 and
                            isinstance(r.get("t"), str) and r.get("s", "tangdouz") in SOURCE_NAMES]
        except (OSError, ValueError, TypeError):
            self.samples = []

    def ensure_today(self):
        if self.day != datetime.now().astimezone().date().isoformat():
            self.reload()

    def append(self, price, source):
        if not price or price <= 0:
            return
        now = datetime.now().astimezone()
        day = now.date().isoformat()
        if day != self.day:
            self.day = day
            self.samples = []
        stamp = now.strftime("%H:%M")
        if self.samples and self.samples[-1]["t"] == stamp and self.samples[-1].get("s") == source:
            self.samples[-1]["p"] = price
        else:
            self.samples.append({"t": stamp, "p": price, "s": source})
        APP_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self._path().with_suffix(".tmp")
        tmp.write_text(json.dumps(self.samples, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path())
        for old in sorted(APP_DIR.glob("intraday-????-??-??.json"))[:-3]:
            try:
                old.unlink()
            except OSError:
                pass


def delta(cfg, quote):
    use_open = cfg["changeBasis"] == "open" and bool(quote.get("open"))
    basis = float((quote.get("open") if use_open else quote.get("prevClose")) or 0)
    amount = float(quote.get("price") or 0) - basis if basis else 0
    return amount, amount / basis * 100 if basis else 0, basis, ("今开" if use_open else "昨收")
