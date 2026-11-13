#!/usr/bin/env bash
# Packaging is part of the shared build, avoiding a second artifact layout.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$ROOT/tools/build.py"
