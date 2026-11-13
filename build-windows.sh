#!/usr/bin/env bash
# Build the Windows onedir application in a reproducible Wine container on macOS/Linux.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
/usr/local/bin/python3.9 - <<'PY'
from PIL import Image
image = Image.open('docs/icon-1024.png').convert('RGBA')
image.save('build/GoldTicker.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
PY
docker build -f build-windows.Dockerfile -t goldticker-win-build .
docker run --rm -v "$PROJECT_DIR:/work" goldticker-win-build bash /work/build-windows-in-container.sh
