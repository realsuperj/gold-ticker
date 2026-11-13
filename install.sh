#!/bin/bash
# GoldTicker 安装脚本：打包成 ~/Applications/GoldTicker.app
# 用法：./install.sh                安装 / 覆盖安装
#       ./install.sh --autostart      安装并设置开机自启动（无需任何账号登录）
#       ./install.sh --login          同 --autostart（向后兼容别名）
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/Applications/GoldTicker.app"
BIN_DIR="$APP_DIR/Contents/MacOS"
RES_DIR="$APP_DIR/Contents/Resources"
PLIST="$HOME/Library/LaunchAgents/com.superj.goldticker.plist"

PY=""
for cand in /usr/local/bin/python3.9 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if [ -x "$cand" ] && "$cand" -c "import objc, AppKit" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "没有找到带 PyObjC 的 Python（需要 python3.9 + pyobjc）。"
  echo "装法：/usr/local/bin/python3.9 -m pip install pyobjc-framework-Cocoa"
  exit 1
fi
echo "使用解释器：$PY"

mkdir -p "$BIN_DIR" "$RES_DIR"
rm -rf "$BIN_DIR/bin"
cp "$SRC_DIR/app/goldticker.py" "$RES_DIR/goldticker.py"

# 图标：缺失时现生成
if [ ! -f "$SRC_DIR/build/AppIcon.icns" ]; then
  "$PY" "$SRC_DIR/tools/make_icon.py" >/dev/null 2>&1 || true
fi
if [ -f "$SRC_DIR/build/AppIcon.icns" ]; then
  cp "$SRC_DIR/build/AppIcon.icns" "$RES_DIR/AppIcon.icns"
fi

cat > "$BIN_DIR/GoldTicker" <<LAUNCH
#!/bin/bash
exec "$PY" "$RES_DIR/goldticker.py" "\$@"
LAUNCH
chmod +x "$BIN_DIR/GoldTicker"

cat > "$APP_DIR/Contents/Info.plist" <<'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>GoldTicker</string>
  <key>CFBundleDisplayName</key><string>金价</string>
  <key>CFBundleIdentifier</key><string>com.superj.goldticker</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>GoldTicker</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLISTEOF

codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true
echo "已安装：$APP_DIR"

pkill -f "goldticker.py" 2>/dev/null || true

if [ "${1:-}" = "--login" ] || [ "${1:-}" = "--autostart" ]; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.superj.goldticker</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BIN_DIR/GoldTicker</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
</dict>
</plist>
PLISTEOF
  launchctl unload "$PLIST" >/dev/null 2>&1 || true
  launchctl load "$PLIST"
  echo "已设置开机自启动（开机进入桌面自动运行，无需账号）：$PLIST"
fi

open "$APP_DIR"
echo "启动完成。右键小窗可调显示项/透明度/刷新频率。"
