"""日内分时行情持久化、当日冻结基准与历史清理 (core/storage.py)。

时间契约：
- 采样点以 UTC epoch 毫秒存储（"ts" 字段）；"t" 仅作向后兼容的显示字符串。
- 分时文件按客户端本地自然日命名（YYYY-MM-DD），当日边界 = 客户端时区的本地午夜。
- 当日冻结基准（day-basis）：当日首次成功采样时把该标的的昨收/今开固化到本地，
  之后刷新只更新价格，基准全天不变，避免备用数据源切换导致涨跌基准漂移。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_app_data_dir

# 超过该间隔（秒）的相邻采样在走势图上断开，避免长时间缺样连成"看似连续"的行情
SAMPLE_GAP_BREAK_SECONDS = 45 * 60

# 旧版数据源 ID → 当前标的（仅映射口径一致、可并入同图的序列）
LEGACY_SYMBOL_MAP = {
    "sina_au9999": "au9999",
    "tangdouz": "au9999",
}


def now_utc_ms() -> int:
    """当前 UTC epoch 毫秒（采样时间：组件本次成功获取报价的时间）。"""
    return int(time.time() * 1000)


def local_date_str(ts_ms: Optional[int] = None) -> str:
    """时间戳在客户端本地时区对应的自然日 (YYYY-MM-DD)。"""
    if ts_ms is None:
        return dt.date.today().isoformat()
    return dt.datetime.fromtimestamp(ts_ms / 1000.0).date().isoformat()


def get_today_str() -> str:
    """获取当前客户端本地日期字符串 (YYYY-MM-DD)。"""
    return dt.date.today().isoformat()


def get_intraday_file_path(date_str: str | None = None, data_dir: Path | None = None) -> Path:
    """获取指定日期的分时文件路径。"""
    d = date_str or get_today_str()
    base = data_dir or get_app_data_dir()
    return base / f"intraday-{d}.json"


def cleanup_old_history(keep_days: int = 3, data_dir: Path | None = None) -> int:
    """扫描并删除超过 keep_days 天的历史分时数据文件。"""
    base = data_dir or get_app_data_dir()
    if not base.exists():
        return 0

    today = dt.date.today()
    deleted_count = 0
    pattern = re.compile(r"^intraday-(\d{4}-\d{2}-\d{2})\.json$")

    for file_path in base.glob("intraday-*.json"):
        match = pattern.match(file_path.name)
        if not match:
            continue
        try:
            file_date = dt.date.fromisoformat(match.group(1))
            diff_days = (today - file_date).days
            if diff_days > keep_days:
                file_path.unlink(missing_ok=True)
                deleted_count += 1
        except Exception:
            continue

    return deleted_count


def _read_day_doc(file_path: Path) -> Dict[str, Any]:
    """分时文件统一为 {points: [...], basis: {...}} 文档；旧裸数组自动包装。"""
    if not file_path.exists():
        return {"points": [], "basis": {}}
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {"points": [], "basis": {}}
    if isinstance(raw, dict):
        raw.setdefault("points", [])
        raw.setdefault("basis", {})
        return raw
    # 旧格式：裸点数组
    return {"points": raw if isinstance(raw, list) else [], "basis": {}}


def _write_day_doc(file_path: Path, doc: Dict[str, Any]) -> bool:
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(file_path)
        return True
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to write day doc: {e}\n")
        return False


def _read_points(file_path: Path) -> List[Dict[str, Any]]:
    return _read_day_doc(file_path)["points"]


def _write_points(file_path: Path, points: List[Dict[str, Any]]) -> bool:
    doc = _read_day_doc(file_path)
    doc["points"] = points
    return _write_day_doc(file_path, doc)


def _normalize_symbol(symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return symbol
    return LEGACY_SYMBOL_MAP.get(symbol, symbol)


def _migrate_point(point: Dict[str, Any], date_str: str) -> Optional[Dict[str, Any]]:
    """旧格式点（仅 "t": "HH:MM"）按分时文件本地日补出 "ts"，并归一化标的 ID。"""
    if not isinstance(point, dict) or point.get("p", 0) <= 0:
        return None
    out = dict(point)
    out["s"] = _normalize_symbol(out.get("s"))
    if out.get("ts"):
        return out
    t_str = out.get("t")
    if not t_str or not date_str:
        return None
    try:
        hh_s, mm_s = str(t_str).split(":")[:2]
        local_dt = dt.datetime.combine(
            dt.date.fromisoformat(date_str),
            dt.time(int(hh_s), int(mm_s)),
        )
        out["ts"] = int(local_dt.timestamp() * 1000)
        out["t"] = f"{int(hh_s):02d}:{int(mm_s):02d}"
        return out
    except Exception:
        return None


def _load_migrated_points(file_path: Path) -> List[Dict[str, Any]]:
    date_str = get_today_str()
    match = re.match(r"^intraday-(\d{4}-\d{2}-\d{2})\.json$", file_path.name)
    if match:
        date_str = match.group(1)
    return [p for p in (_migrate_point(pt, date_str) for pt in _read_points(file_path)) if p]


def load_today_points(symbol: Optional[str] = None, data_dir: Path | None = None) -> List[Dict[str, Any]]:
    """读取当日分时采样点，可按标的过滤。

    返回点均带 "ts"（UTC ms）。旧版仅有本地 "t" 的点按文件日期还原时刻；
    旧数据源 ID 按 LEGACY_SYMBOL_MAP 并入当前标的。
    """
    file_path = get_intraday_file_path(data_dir=data_dir)
    points = _load_migrated_points(file_path)
    if symbol:
        want = _normalize_symbol(symbol)
        return [pt for pt in points if pt.get("s") == want]
    return points


def record_price_point(
    price: float,
    symbol: str,
    timestamp_str: Optional[str] = None,
    data_dir: Path | None = None,
    ts_ms: Optional[int] = None,
) -> bool:
    """记录一次有效价格采样点至当日分时文件。

    timestamp_str 兼容旧签名（仅作显示字符串）；ts_ms 缺省取当前 UTC 时间。
    同一分钟（同标的）内后点覆盖前点。写入前会先迁移旧点，避免把无 ts 历史冲掉。
    """
    if price <= 0:
        return False

    ts = ts_ms if ts_ms is not None else now_utc_ms()
    minute_key = dt.datetime.fromtimestamp(ts / 1000.0).strftime("%H:%M")
    t_str = timestamp_str or minute_key
    file_path = get_intraday_file_path(date_str=local_date_str(ts), data_dir=data_dir)
    points = _load_migrated_points(file_path)
    symbol = _normalize_symbol(symbol) or symbol

    new_point = {
        "ts": ts,
        "t": t_str,
        "p": round(float(price), 2),
        "s": symbol,
    }

    # 追加后按时间排序，并对同标的同本地分钟的点合并（后写覆盖先写）
    points.append(new_point)
    points.sort(key=lambda p: p["ts"])
    merged: List[Dict[str, Any]] = []
    for pt in points:
        pt_minute = dt.datetime.fromtimestamp(pt["ts"] / 1000.0).strftime("%H:%M")
        prev_pt = merged[-1] if merged else None
        if (prev_pt is not None and prev_pt.get("s") == pt.get("s")
                and dt.datetime.fromtimestamp(prev_pt["ts"] / 1000.0).strftime("%H:%M") == pt_minute):
            prev_pt["p"] = pt["p"]
            prev_pt["ts"] = pt["ts"]
            prev_pt["t"] = pt.get("t") or pt_minute
        else:
            merged.append(pt)

    return _write_points(file_path, merged)


# ---------------- 当日冻结基准 ----------------

def get_day_basis(symbol: str, data_dir: Path | None = None) -> Optional[Dict[str, float]]:
    """读取当日冻结基准。无则返回 None。"""
    file_path = get_intraday_file_path(data_dir=data_dir)
    doc = _read_day_doc(file_path)
    basis = doc.get("basis", {})
    entry = basis.get(symbol)
    if isinstance(entry, dict) and entry.get("prev_close", 0) > 0:
        return {"prev_close": float(entry["prev_close"]),
                "open": float(entry.get("open", 0.0))}
    return None


def apply_frozen_basis(quote, data_dir: Path | None = None):
    """若有当日冻结基准，则把 quote 的昨收/今开替换为冻结值并重算涨跌。

    在 quote 进入 UI 前调用，状态栏、卡片、托盘 Tooltip 全部自动一致，
    避免备用数据源切换导致涨跌基准漂移。无冻结值时原样返回。
    """
    symbol = getattr(quote, "symbol", "")
    basis = get_day_basis(symbol, data_dir) if symbol else None
    if not basis or not getattr(quote, "price", 0):
        return quote
    quote.prev_close = basis["prev_close"]
    if basis.get("open", 0) > 0:
        quote.open_price = basis["open"]
    base = quote.prev_close
    quote.change = round(quote.price - base, 2)
    quote.change_pct = round(quote.change / base * 100.0, 2) if base > 0 else 0.0
    return quote


def freeze_day_basis(
    symbol: str,
    prev_close: float,
    open_price: float,
    data_dir: Path | None = None,
) -> bool:
    """当日首次成功采样时冻结基准；当日已有冻结则不覆盖（先到先得）。"""
    if prev_close <= 0:
        return False
    file_path = get_intraday_file_path(data_dir=data_dir)
    doc = _read_day_doc(file_path)

    basis = doc.setdefault("basis", {})
    if isinstance(basis.get(symbol), dict) and basis[symbol].get("prev_close", 0) > 0:
        return True  # 已冻结，保持全天不变

    basis[symbol] = {"prev_close": round(float(prev_close), 2),
                     "open": round(float(open_price or 0.0), 2)}
    return _write_day_doc(file_path, doc)


def clear_intraday_cache(data_dir: Path | None = None) -> bool:
    """一键清理当天的分时缓存文件（含冻结基准）。"""
    file_path = get_intraday_file_path(data_dir=data_dir)
    try:
        if file_path.exists():
            file_path.unlink()
        return True
    except Exception:
        return False
