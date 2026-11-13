"""日内分时行情持久化与历史清理 (core/storage.py)。"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_app_data_dir


def get_today_str() -> str:
    """获取当前日期字符串 (YYYY-MM-DD)。"""
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


def load_today_points(symbol: Optional[str] = None, data_dir: Path | None = None) -> List[Dict[str, Any]]:
    """读取当日分时采样点，可按标的过滤。"""
    file_path = get_intraday_file_path(data_dir=data_dir)
    if not file_path.exists():
        return []

    try:
        raw_text = file_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if not isinstance(data, list):
            return []
        if symbol:
            return [pt for pt in data if pt.get("s") == symbol]
        return data
    except Exception:
        return []


def record_price_point(
    price: float,
    symbol: str,
    timestamp_str: Optional[str] = None,
    data_dir: Path | None = None,
) -> bool:
    """记录一次有效价格采样点至当日分时文件 (分钟级去重/更新)。"""
    if price <= 0:
        return False

    t_str = timestamp_str or dt.datetime.now().strftime("%H:%M")
    file_path = get_intraday_file_path(data_dir=data_dir)
    points = load_today_points(symbol=None, data_dir=data_dir)

    new_point = {
        "t": t_str,
        "p": round(float(price), 2),
        "s": symbol,
    }

    # 查重优化：若最新一条数据同时间、同标的，更新价格；否则追加
    if points and points[-1].get("t") == t_str and points[-1].get("s") == symbol:
        points[-1]["p"] = new_point["p"]
    else:
        points.append(new_point)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(file_path)
        return True
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to record price point: {e}\n")
        return False


def clear_intraday_cache(data_dir: Path | None = None) -> bool:
    """一键清理当天的分时缓存文件。"""
    file_path = get_intraday_file_path(data_dir=data_dir)
    try:
        if file_path.exists():
            file_path.unlink()
        return True
    except Exception:
        return False
