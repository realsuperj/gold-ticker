#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX=/wine-gui WINEARCH=win64 WINEDEBUG=err+all DISPLAY=:91
Xvfb :91 -screen 0 1280x800x24 >/tmp/goldticker-gui-xvfb.log 2>&1 &
XVFB_PID=$!
APP_PID=
cleanup() {
  if [ -n "$APP_PID" ]; then kill "$APP_PID" 2>/dev/null || true; fi
  kill "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT
apt-get update -qq
apt-get install -y -qq --no-install-recommends wine scrot >/tmp/goldticker-gui-apt.log 2>&1
wine wineboot -u >/tmp/goldticker-gui-boot.log 2>&1
wine winecfg -v win10 >/tmp/goldticker-gui-config.log 2>&1
test ! -e /wine-gui/drive_c/Python/python.exe
wine 'Z:\work\dist\windows\GoldTicker\GoldTicker.exe' --self-test > /work/build/wine-gui-selftest.log 2>&1
wine 'Z:\work\dist\windows\GoldTicker\GoldTicker.exe' > /tmp/goldticker-gui-app.log 2>&1 &
APP_PID=$!
sleep 20
if ! kill -0 "$APP_PID" 2>/dev/null; then
  printf 'GoldTicker exited before GUI screenshot\n' >&2
  tail -50 /tmp/goldticker-gui-app.log >&2
  exit 1
fi
scrot -o /work/docs/windows-wine-preview.png
cp /tmp/goldticker-gui-app.log /work/build/wine-gui-app.log
printf 'CLEAN_WINE_GUI_RUNNING_AND_CAPTURED\n'
