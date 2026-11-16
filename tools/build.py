"""Build lightweight native self-contained packages (macOS ObjC Universal2 <1MB / Windows WPF <1MB)."""
from __future__ import annotations

import hashlib
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.product import BUNDLE_ID, COPYRIGHT, PRODUCT_NAME, VERSION


def _build_compact_icns(src_png: Path, out_icns: Path, work_dir: Path) -> None:
    """用系统原生 sips + iconutil 生成紧凑高清 .icns（无需 Pillow，体积仅约 150~220KB）。"""
    iconset = work_dir / "AppIcon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    # 包含菜单栏/Finder/关于框常用档位（省去冗余 512@2x 巨图，兼顾视网膜清晰度与 <1MB 目标）
    specs = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
    ]
    for filename, px in specs:
        dest = iconset / filename
        subprocess.run(
            ["sips", "-z", str(px), str(px), str(src_png), "--out", str(dest)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    out_icns.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out_icns)], check=True)
    shutil.rmtree(iconset)


def _make_macos_dmg(app: Path, artifact: Path) -> None:
    """DMG 含 GoldTicker.app + Applications 符号链接，支持标准拖拽安装。"""
    stage = app.parent / "dmg-stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    if artifact.exists():
        artifact.unlink()
    subprocess.run(
        [
            "hdiutil", "create",
            "-volname", PRODUCT_NAME,
            "-srcfolder", str(stage),
            "-ov", "-format", "UDZO",
            "-imagekey", "zlib-level=9",
            str(artifact),
        ],
        check=True,
    )
    shutil.rmtree(stage)


def build_macos() -> Path:
    build_dir = ROOT / "build" / "mac-native"
    dist_dir = ROOT / "dist" / "macos"
    build_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("GoldTicker-arm64", "GoldTicker-x86_64", PRODUCT_NAME, "dmg-stage", "AppIcon.iconset"):
        p = build_dir / stale
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    objc_src = ROOT / "mac-native" / "GoldTicker.m"
    uni_bin = build_dir / PRODUCT_NAME

    print("Compiling Universal2 (clang objc-arc)…", flush=True)
    subprocess.run(
        [
            "clang",
            "-fobjc-arc",
            "-Os",
            "-mmacosx-version-min=12.0",
            "-arch", "arm64",
            "-arch", "x86_64",
            "-framework", "AppKit",
            "-framework", "Foundation",
            str(objc_src),
            "-o", str(uni_bin),
        ],
        check=True,
    )
    subprocess.run(["strip", "-x", str(uni_bin)], check=True)
    print(f"Universal binary: {uni_bin.stat().st_size / 1024:.1f} KB", flush=True)

    app_dir = dist_dir / f"{PRODUCT_NAME}.app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    macos_dir = app_dir / "Contents" / "MacOS"
    res_dir = app_dir / "Contents" / "Resources"
    macos_dir.mkdir(parents=True)
    res_dir.mkdir(parents=True)

    shutil.copy2(uni_bin, macos_dir / PRODUCT_NAME)
    (macos_dir / PRODUCT_NAME).chmod(0o755)
    shutil.copy2(ROOT / "shared" / "spec.json", res_dir / "spec.json")
    _build_compact_icns(ROOT / "docs" / "icon-1024.png", res_dir / "AppIcon.icns", build_dir)

    info_plist = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": PRODUCT_NAME,
        "CFBundleExecutable": PRODUCT_NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": PRODUCT_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "12.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": COPYRIGHT,
    }
    (app_dir / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info_plist))

    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app_dir)], check=True)
    artifact = dist_dir / "GoldTicker-macOS-Universal2.dmg"
    _make_macos_dmg(app_dir, artifact)
    write_hash(artifact)
    return artifact


def write_hash(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")


def main() -> None:
    if sys.platform == "darwin":
        artifact = build_macos()
        print(f"Built {artifact} ({artifact.stat().st_size / 1024:.1f} KB)")
    elif sys.platform == "win32":
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "build_windows_wpf.ps1")],
            cwd=ROOT,
            check=True,
        )
    else:
        raise SystemExit("Run on native macOS or Windows.")


if __name__ == "__main__":
    main()
