#!/usr/bin/env bash
# Build the Windows application in a reproducible Wine container on macOS/Linux.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"
docker build -f build-windows.Dockerfile -t goldticker-win-build .
docker run --rm -v "$PROJECT_DIR:/work" goldticker-win-build bash /work/build-windows-in-container.sh
