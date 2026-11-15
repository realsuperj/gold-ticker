"""JSON-lines IPC worker: WinUI (or any shell) talks to shared core over stdio.

Protocol: one JSON object per line on stdin; one JSON response per line on stdout.
Request:  {"id":1,"method":"fetch","params":{}}
Response: {"id":1,"ok":true,"result":{...}} | {"id":1,"ok":false,"error":"..."}
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import (
    VALID_REFRESH_INTERVALS,
    VALID_WIDTHS,
    get_app_data_dir,
    load_config,
    save_config,
    sanitize_config,
)
from core.constants import DISCLAIMER_CN, DISCLAIMER_EN, SUPPORTED_SYMBOLS, SYMBOL_META
from core.i18n import resolve_language, t
from core.pricing import default_engine
from core.product import COPYRIGHT, VERSION
from core.storage import (
    apply_frozen_basis,
    clear_intraday_cache,
    load_today_points,
    record_price_point,
)


def _cfg() -> Dict[str, Any]:
    return load_config()


def _quote_payload(quote) -> Optional[Dict[str, Any]]:
    if quote is None:
        return None
    q = apply_frozen_basis(quote)
    return q.to_dict()


def _samples(symbol: str) -> list:
    return [{"ts": p.get("ts"), "t": p.get("t"), "p": p.get("p"), "s": p.get("s")}
            for p in load_today_points(symbol) if p.get("p", 0) > 0]


def handle(method: str, params: Optional[Dict[str, Any]]) -> Any:
    params = params or {}
    if method == "hello":
        return {"version": VERSION, "copyright": COPYRIGHT, "platform": sys.platform}

    if method == "get_config":
        return _cfg()

    if method == "set_config":
        patch = params.get("patch") or {}
        cfg = sanitize_config({**_cfg(), **patch})
        save_config(cfg)
        return cfg

    if method == "meta":
        lang = resolve_language(_cfg().get("language", "auto"))
        symbols = []
        for sid in SUPPORTED_SYMBOLS:
            m = SYMBOL_META[sid]
            symbols.append({
                "id": sid,
                "name": m["name_cn" if lang == "zh" else "name_en"],
                "unit": m["unit_cn" if lang == "zh" else "unit_en"],
                "is_estimated": m["is_estimated"],
            })
        return {
            "symbols": symbols,
            "widths": list(VALID_WIDTHS),
            "refreshSeconds": list(VALID_REFRESH_INTERVALS),
            "opacities": [0.60, 0.75, 0.88, 0.95, 1.0],
            "disclaimer": DISCLAIMER_CN if lang == "zh" else DISCLAIMER_EN,
            "strings": {
                "high": t("high", lang),
                "low": t("low", lang),
                "prev": t("prev_close", lang),
                "open": t("open_price", lang),
                "unavailable": t("fetch_error", lang),
                "refreshing": t("refreshing", lang),
            },
            "version": VERSION,
            "copyright": COPYRIGHT,
        }

    if method == "fetch":
        cfg = _cfg()
        symbol = params.get("symbol") or cfg.get("symbol")
        quotes = default_engine.sample_all_quotes()
        for s, q in quotes.items():
            if q and q.price > 0 and not q.error:
                record_price_point(q.price, s)
        quote = quotes.get(symbol) or default_engine.get_quote(symbol)
        return {
            "config": cfg,
            "quote": _quote_payload(quote),
            "samples": _samples(symbol),
        }

    if method == "get_samples":
        symbol = params.get("symbol") or _cfg().get("symbol")
        return {"samples": _samples(symbol)}

    if method == "open_data_dir":
        path = str(get_app_data_dir())
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
        return {"path": path}

    if method == "clear_cache":
        clear_intraday_cache()
        return {"cleared": True}

    if method == "quit":
        return {"bye": True}

    raise ValueError(f"unknown method: {method}")


def _reply(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    # Unbuffered line protocol
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req["method"]
            result = handle(method, req.get("params"))
            _reply({"id": req_id, "ok": True, "result": result})
            if method == "quit":
                return
        except Exception as e:
            _reply({
                "id": req_id,
                "ok": False,
                "error": str(e),
                "trace": traceback.format_exc(limit=3),
            })


if __name__ == "__main__":
    main()
