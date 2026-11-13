#!/usr/bin/env bash
# Compatibility alias for the maintained Wine build route.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/build-windows.sh" "$@"
