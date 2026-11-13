#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX=/wine-clean WINEARCH=win64 WINEDEBUG=-all DISPLAY=:90
Xvfb :90 -screen 0 1280x800x24 >/tmp/goldticker-smoke-xvfb.log 2>&1 &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT
apt-get update -qq
apt-get install -y -qq --no-install-recommends wine >/tmp/goldticker-smoke-apt.log 2>&1
wine wineboot -u >/tmp/goldticker-smoke-boot.log 2>&1
wine winecfg -v win10 >/tmp/goldticker-smoke-config.log 2>&1
test ! -e /wine-clean/drive_c/Python/python.exe
wine 'Z:\work\dist\windows\GoldTicker\GoldTicker.exe' --self-test
printf 'CLEAN_WINE_EXE_SELF_TEST_PASSED\n'
