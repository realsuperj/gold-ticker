#!/usr/bin/env bash
set -euo pipefail
export WINEDEBUG=-all WINEPREFIX=/wine WINEARCH=win64 DISPLAY=:88
Xvfb :88 -screen 0 1280x800x24 >/tmp/goldticker-xvfb.log 2>&1 &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT
sleep 2
# Debian splits the Wine executables from the small architecture-selecting launcher.
if ! command -v wine >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends wine >/tmp/goldticker-wine-launcher.log 2>&1
fi
WINE=/usr/bin/wine
"$WINE" wineboot -u >/tmp/goldticker-wineboot.log 2>&1
# Wine 8 defaults to Windows 7; CPython 3.11 requires Windows 8.1+.
"$WINE" winecfg -v win10 >/tmp/goldticker-winecfg.log 2>&1
if [ ! -f /wine/drive_c/Python/python.exe ]; then
  if ! WINEDEBUG=err+all "$WINE" /tmp/python.exe /quiet InstallAllUsers=0 Include_pip=1 Include_tcltk=1 TargetDir='C:\Python' /log 'C:\goldticker-install.log' > /tmp/goldticker-installer-output.log 2>&1; then
    printf 'Windows Python installer exited with an error:\n' >&2
    tail -80 /tmp/goldticker-installer-output.log >&2
    tail -80 /wine/drive_c/goldticker-install.log 2>/dev/null >&2 || true
    exit 1
  fi
fi
if [ ! -f /wine/drive_c/Python/python.exe ]; then
  tail -80 /tmp/goldticker-install.log 2>/dev/null || true
  printf 'Windows Python installation did not create C:\\Python\\python.exe\n' >&2
  exit 1
fi
PY='C:\Python\python.exe'
cd /work
"$WINE" "$PY" -m pip install --disable-pip-version-check -r 'Z:\work\requirements.txt' 'pyinstaller>=6.11,<7'
"$WINE" "$PY" 'Z:\work\tools\build.py'
test -s /work/dist/windows/GoldTicker.exe
