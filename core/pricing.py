"""多源高可用黄金行情抓取、容灾冷却与汇率/点差引擎 (core/pricing.py)。"""
from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.constants import (
    COOL_DOWN_SECONDS,
    DEFAULT_BANK_SPREADS,
    SYMBOL_AU9999,
    SYMBOL_CCB_JCJ,
    SYMBOL_ICBC_JCJ,
    SYMBOL_META,
    SYMBOL_XAU_USD,
    SYMBOL_ZS_JCJ,
    TROY_OUNCE_TO_GRAM,
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
TANGDOUZ_URL = "https://api.tangdouz.com/a/zsgold.php"
SINA_HQ_URL = "https://hq.sinajs.cn/list="


@dataclass
class QuoteData:
    symbol: str
    price: float
    prev_close: float
    open_price: float
    high: float
    low: float
    change: float
    change_pct: float
    time_str: str
    source_id: str
    source_name: str
    is_estimated: bool = False
    fx_rate: float = 0.0
    usd_price: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "prev_close": self.prev_close,
            "open_price": self.open_price,
            "high": self.high,
            "low": self.low,
            "change": self.change,
            "change_pct": self.change_pct,
            "time_str": self.time_str,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "is_estimated": self.is_estimated,
            "fx_rate": self.fx_rate,
            "usd_price": self.usd_price,
            "error": self.error,
        }


def _get_ssl_context() -> ssl.SSLContext:
    """获取适配跨平台的标准 SSL 证书上下文。"""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
        return ctx
    except Exception:
        pass

    for cert_path in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt"):
        if os.path.exists(cert_path):
            try:
                ctx.load_verify_locations(cert_path)
                return ctx
            except Exception:
                pass

    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_GLOBAL_SSL_CTX: Optional[ssl.SSLContext] = None


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> bytes:
    """轻量 HTTP GET 请求。"""
    global _GLOBAL_SSL_CTX
    if _GLOBAL_SSL_CTX is None:
        _GLOBAL_SSL_CTX = _get_ssl_context()

    hdr = {"User-Agent": UA}
    if headers:
        hdr.update(headers)

    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout, context=_GLOBAL_SSL_CTX) as resp:
        return resp.read()


def _parse_num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def _calc_pack(price: float, prev: float, op: float, high: float, low: float, tm: str) -> Tuple[float, float, float, float, float, float, float, str]:
    price = round(float(price), 2)
    prev = round(float(prev or 0.0), 2)
    if prev <= 0:
        prev = round(float(op or price), 2)
    op = round(float(op or 0.0), 2)
    high = round(float(high or 0.0), 2)
    low = round(float(low or 0.0), 2)

    change = round(price - prev, 2)
    pct = round((change / prev * 100.0), 2) if prev > 0 else 0.0
    return price, prev, op, high, low, change, pct, tm or "--:--"


# ---------------- 原始底层数据源抓取 ----------------

def fetch_tangdouz_raw() -> Tuple[float, float, float, float, float, float, float, str]:
    """抓取糖豆子浙商积存金。"""
    raw = http_get(TANGDOUZ_URL)
    try:
        text = raw.decode("gb18030")
    except Exception:
        text = raw.decode("utf-8", "ignore")

    lines = {line.split(":")[0].strip(): line.split(":", 1)[1].strip() for line in text.splitlines() if ":" in line}

    def get_val(k: str) -> float:
        v = lines.get(k, "")
        num_str = "".join([c for c in v if c.isdigit() or c in ".-"])
        return _parse_num(num_str)

    price = get_val("最新价格")
    if price <= 0:
        raise ValueError("糖豆子接口未返回最新价格")

    tm = "--:--"
    update_str = lines.get("更新时间", "")
    if update_str:
        bits = update_str.split(" ")[-1].split(":")
        if len(bits) >= 2:
            tm = f"{int(bits[0]):02d}:{int(bits[1]):02d}"

    return _calc_pack(price, get_val("前收盘价"), get_val("开盘价"), get_val("最高价"), get_val("最低价"), tm)


def _fetch_sina_list(codes: str) -> Dict[str, List[str]]:
    """批量解析新浪财经行情列表。"""
    raw = http_get(SINA_HQ_URL + codes, headers={"Referer": "https://finance.sina.com.cn"})
    try:
        text = raw.decode("gb18030")
    except Exception:
        text = raw.decode("utf-8", "ignore")

    out = {}
    for line in text.splitlines():
        if "hq_str_" not in line or '="' not in line:
            continue
        key = line.split("hq_str_", 1)[1].split("=", 1)[0].strip()
        body = line.split('="', 1)[1].rstrip('";')
        out[key] = body.split(",")
    return out


def fetch_sina_au9999_raw() -> Tuple[float, float, float, float, float, float, float, str]:
    """抓取上金所 Au99.99 现货基准。"""
    data = _fetch_sina_list("SGE_AU9999").get("SGE_AU9999") or []
    if len(data) < 10:
        raise ValueError("新浪 Au99.99 字段不足")

    tm = "--:--"
    if len(data) > 16 and data[16]:
        bits = data[16].split(" ")[-1].split(":")
        if len(bits) >= 2:
            tm = f"{int(bits[0]):02d}:{int(bits[1]):02d}"

    # f[3]=最新, f[5]=昨收, f[9]=今开, f[7]=最高, f[8]=最低
    return _calc_pack(_parse_num(data[3]), _parse_num(data[5]), _parse_num(data[9]), _parse_num(data[7]), _parse_num(data[8]), tm)


def fetch_sina_autd_raw() -> Tuple[float, float, float, float, float, float, float, str]:
    """抓取上金所 Au(T+D) 现货延期。"""
    data = _fetch_sina_list("gds_AUTD").get("gds_AUTD") or []
    if len(data) < 9:
        raise ValueError("新浪 Au(T+D) 字段不足")

    tm = "--:--"
    bits = (data[6] or "").split(":")
    if len(bits) >= 2:
        tm = f"{int(bits[0]):02d}:{int(bits[1]):02d}"

    # f[0]=最新, f[7]=昨收, f[8]=今开, f[4]=最高, f[5]=最低
    return _calc_pack(_parse_num(data[0]), _parse_num(data[7]), _parse_num(data[8]), _parse_num(data[4]), _parse_num(data[5]), tm)


def fetch_sina_xau_raw() -> Tuple[Tuple[float, float, float, float, float, float, float, str], float, float]:
    """抓取国际伦敦金现货 (USD/oz) 与 USD/CNY 汇率。返回: (pack, raw_usd, fx_rate)"""
    resp = _fetch_sina_list("hf_XAU,fx_susdcny")
    f_xau = resp.get("hf_XAU") or []
    f_fx = resp.get("fx_susdcny") or []
    if len(f_xau) < 9 or len(f_fx) < 2:
        raise ValueError("国际金或汇率数据字段不足")

    rate = _parse_num(f_fx[1])
    if rate <= 0:
        raise ValueError("未能获取有效美元汇率")

    raw_usd = _parse_num(f_xau[0])
    tm = "--:--"
    bits = (f_xau[6] or "").split(":")
    if len(bits) >= 2:
        tm = f"{int(bits[0]):02d}:{int(bits[1]):02d}"

    # 盎司美元价格
    usd_pack = _calc_pack(raw_usd, _parse_num(f_xau[7]), _parse_num(f_xau[8]), _parse_num(f_xau[4]), _parse_num(f_xau[5]), tm)
    return usd_pack, raw_usd, rate


# ---------------- 容灾与调度引擎 ----------------

class PricingEngine:
    def __init__(self):
        # failure tracker: {source_id: {"fails": int, "until": float, "last_err": str}}
        self._failures: Dict[str, Dict[str, Any]] = {}
        self._last_good_quote: Dict[str, QuoteData] = {}

    def is_cooling_down(self, source_id: str) -> bool:
        rec = self._failures.get(source_id)
        if not rec:
            return False
        return time.time() < rec.get("until", 0)

    def record_failure(self, source_id: str, error_msg: str) -> None:
        now = time.time()
        rec = self._failures.setdefault(source_id, {"fails": 0, "until": 0, "last_err": ""})
        rec["fails"] += 1
        rec["last_err"] = error_msg
        if rec["fails"] >= 2:
            rec["until"] = now + COOL_DOWN_SECONDS
            sys.stderr.write(f"Source {source_id} entered cooldown for {COOL_DOWN_SECONDS}s. Reason: {error_msg}\n")

    def record_success(self, source_id: str) -> None:
        if source_id in self._failures:
            del self._failures[source_id]

    def get_source_statuses(self) -> List[Dict[str, Any]]:
        now = time.time()
        res = []
        for sid in ("tangdouz", "sina_au9999", "sina_autd", "sina_xau"):
            rec = self._failures.get(sid, {})
            until = rec.get("until", 0)
            in_cd = until > now
            res.append({
                "source_id": sid,
                "cooling": in_cd,
                "remaining_seconds": max(0, int(until - now)) if in_cd else 0,
                "last_error": rec.get("last_err", ""),
            })
        return res

    def fetch_benchmark_au9999(self) -> Tuple[Tuple[float, float, float, float, float, float, float, str], str, str]:
        """按优先级尝试抓取国内现货基准 (sina_au9999 -> sina_autd -> tangdouz)。"""
        sources = [
            ("sina_au9999", "上金所 Au99.99", fetch_sina_au9999_raw),
            ("sina_autd", "上金所 Au(T+D)", fetch_sina_autd_raw),
            ("tangdouz", "浙商积存金", fetch_tangdouz_raw),
        ]
        last_ex = None
        for sid, sname, fn in sources:
            if self.is_cooling_down(sid):
                continue
            try:
                pack = fn()
                self.record_success(sid)
                return pack, sid, sname
            except Exception as e:
                self.record_failure(sid, str(e))
                last_ex = e

        # 全部都在冷却中，强制尝试主源一次
        try:
            return fetch_sina_au9999_raw(), "sina_au9999", "上金所 Au99.99"
        except Exception:
            raise last_ex or RuntimeError("国内现货金所有行情源均不可用")

    def get_quote(self, symbol: str) -> QuoteData:
        """主入口：获取指定标的的最新行情数据。"""
        meta = SYMBOL_META.get(symbol, SYMBOL_META[SYMBOL_AU9999])

        try:
            # 1. 国际伦敦金 (XAU/USD)
            if symbol == SYMBOL_XAU_USD:
                usd_pack, raw_usd, rate = fetch_sina_xau_raw()
                self.record_success("sina_xau")
                p, prev, op, h, l, chg, pct, tm = usd_pack
                quote = QuoteData(
                    symbol=symbol,
                    price=p,
                    prev_close=prev,
                    open_price=op,
                    high=h,
                    low=l,
                    change=chg,
                    change_pct=pct,
                    time_str=tm,
                    source_id="sina_xau",
                    source_name="伦敦金现货",
                    is_estimated=False,
                    fx_rate=rate,
                    usd_price=raw_usd,
                )
                self._last_good_quote[symbol] = quote
                return quote

            # 2. 浙商银行积存金 (官方直连优先)
            if symbol == SYMBOL_ZS_JCJ:
                if not self.is_cooling_down("tangdouz"):
                    try:
                        p, prev, op, h, l, chg, pct, tm = fetch_tangdouz_raw()
                        self.record_success("tangdouz")
                        quote = QuoteData(
                            symbol=symbol,
                            price=p,
                            prev_close=prev,
                            open_price=op,
                            high=h,
                            low=l,
                            change=chg,
                            change_pct=pct,
                            time_str=tm,
                            source_id="tangdouz",
                            source_name="浙商银行直连",
                            is_estimated=False,
                        )
                        self._last_good_quote[symbol] = quote
                        return quote
                    except Exception as e:
                        self.record_failure("tangdouz", str(e))

            # 3. 国内现货基准 Au99.99 或各商业银行点差估算
            pack, sid, sname = self.fetch_benchmark_au9999()
            p, prev, op, h, l, chg, pct, tm = pack

            # 点差叠加
            spread = DEFAULT_BANK_SPREADS.get(symbol, 0.0)
            if spread > 0:
                p = round(p + spread, 2)
                prev = round(prev + spread, 2)
                op = round(op + spread, 2)
                h = round(h + spread, 2)
                l = round(l + spread, 2)
                chg = round(p - prev, 2)
                pct = round((chg / prev * 100.0), 2) if prev > 0 else 0.0

            quote = QuoteData(
                symbol=symbol,
                price=p,
                prev_close=prev,
                open_price=op,
                high=h,
                low=l,
                change=chg,
                change_pct=pct,
                time_str=tm,
                source_id=sid,
                source_name=f"{sname} (点差估算)" if spread > 0 else sname,
                is_estimated=(spread > 0),
            )
            self._last_good_quote[symbol] = quote
            return quote

        except Exception as ex:
            # 异常时若有最后一次缓存，优雅降级返回并附带错误提示
            last = self._last_good_quote.get(symbol)
            if last:
                copy_last = QuoteData(**last.to_dict())
                copy_last.error = f"网络连接重试中: {ex}"
                return copy_last
            # 零数据且首抓失败
            return QuoteData(
                symbol=symbol,
                price=0.0,
                prev_close=0.0,
                open_price=0.0,
                high=0.0,
                low=0.0,
                change=0.0,
                change_pct=0.0,
                time_str="--:--",
                source_id="none",
                source_name="行情连接中",
                is_estimated=meta["is_estimated"],
                error=str(ex),
            )


# 全局单例
default_engine = PricingEngine()


def get_quote(symbol: str) -> QuoteData:
    """快捷全局取数函数。"""
    return default_engine.get_quote(symbol)
