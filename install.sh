#!/usr/bin/env bash
# Build and install the same self-contained app produced by CI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$ROOT/tools/build.py"
APP_DIR="$HOME/Applications/GoldTicker.app"
mkdir -p "$HOME/Applications"
# Preserve any existing app so replacement is recoverable.
if [ -e "$APP_DIR" ]; then
  mv "$APP_DIR" "$APP_DIR.backup.$(date +%Y%m%d%H%M%S)"
fi
ditto "$ROOT/dist/macos/GoldTicker.app" "$APP_DIR"
if [ "${1:-}" = "--autostart" ] || [ "${1:-}" = "--login" ]; then
  "$PYTHON" - "$APP_DIR" <<'PY'
import pathlib, plistlib, sys
p = pathlib.Path.home() / "Library/LaunchAgents/com.superj.goldticker.plist"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_bytes(plistlib.dumps({"Label": "com.superj.goldticker", "ProgramArguments": [sys.argv[1] + "/Contents/MacOS/GoldTicker"], "RunAtLoad": True, "KeepAlive": False}))
PY
fi
open "$APP_DIR"
