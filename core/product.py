"""Product metadata and resources shared by source and frozen apps."""
from pathlib import Path
import sys
VERSION = "1.0.0"
PRODUCT_NAME = "GoldTicker"
COPYRIGHT = "Copyright © 2026 realsuperj. MIT License."
def resource_path(name="icon-1024.png"):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "docs" / name
