#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist/windows"
EXE="$DIST/GoldTicker/GoldTicker.exe"
if [ ! -s "$EXE" ]; then
  printf 'Missing Windows executable: %s\n' "$EXE" >&2
  exit 1
fi
cp "$ROOT/windows/README.md" "$DIST/GoldTicker/README.md"
python3 - "$DIST" <<'PY'
import hashlib
import pathlib
import sys
import zipfile
root = pathlib.Path(sys.argv[1])
archive = root / 'GoldTicker-Windows-x64.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
    for path in sorted((root / 'GoldTicker').rglob('*')):
        if path.is_file():
            target.write(path, path.relative_to(root))
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
(root / 'GoldTicker-Windows-x64.sha256').write_text(
    f'{sha}  {archive.name}\n', encoding='ascii')
print(f'{archive}: {archive.stat().st_size:,} bytes')
print('SHA-256:', sha)
PY
