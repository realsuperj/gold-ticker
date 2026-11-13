#!/bin/bash
# docker_build_windows.sh
# 在 Mac/Linux 上用 Docker 交叉编译 Windows GoldTicker.exe
# 用法: ./docker_build_windows.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
IMAGE="batonogov/pyinstaller-windows:latest"
OUT="$REPO/dist/windows"

echo "==> 检查 Docker..."
docker info > /dev/null 2>&1 || { echo "Docker 未运行"; exit 1; }

echo "==> 准备输出目录..."
mkdir -p "$OUT"

echo "==> 开始交叉编译 Windows EXE..."
docker run --rm \
  -v "$REPO:/src" \
  -w /src \
  "$IMAGE" \
  /bin/bash -c "
    pip install pillow pystray --quiet &&
    pip install pyinstaller --quiet &&
    pyinstaller build_windows.spec \
      --distpath /src/dist/windows \
      --workpath /tmp/build_windows \
      --noconfirm \
      --clean 2>&1
  "

echo ""
echo "==> 编译完成！输出目录: $OUT/GoldTicker/"
echo "    将整个 GoldTicker/ 文件夹复制到 Windows 机器，双击 GoldTicker.exe 即可运行。"
ls -lh "$OUT/GoldTicker/" 2>/dev/null || true
