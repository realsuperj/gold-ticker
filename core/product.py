"""Shared product metadata & single-source-of-truth spec loader."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


def _base_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


@lru_cache(maxsize=1)
def load_spec() -> Dict[str, Any]:
    spec_file = _base_dir() / "shared" / "spec.json"
    return json.loads(spec_file.read_text(encoding="utf-8"))


_PRODUCT = load_spec()["product"]
VERSION: str = _PRODUCT["version"]
PRODUCT_NAME: str = _PRODUCT["name"]
BUNDLE_ID: str = _PRODUCT["bundleId"]
COPYRIGHT: str = _PRODUCT["copyright"]
GITHUB_URL: str = _PRODUCT["githubUrl"]


def resource_path(name: str = "icon-1024.png") -> Path:
    return _base_dir() / "docs" / name
