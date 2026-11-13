"""Build a native self-contained package using the common entry/spec."""
import hashlib
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.product import VERSION, COPYRIGHT


def main():
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit("Run with native macOS or Windows Python (Wine is experimental).")
    from PIL import Image
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    mac = sys.platform == "darwin"
    icon = Image.open(ROOT / "docs/icon-1024.png").convert("RGBA")
    icon.save(build / ("AppIcon.icns" if mac else "GoldTicker.ico"))
    if not mac:
        from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
        version = tuple(int(n) for n in VERSION.split(".")) + (0,)
        fields = {"CompanyName": "realsuperj", "FileDescription": "GoldTicker Desktop Gold Price Widget",
                  "FileVersion": VERSION, "InternalName": "GoldTicker", "LegalCopyright": COPYRIGHT,
                  "OriginalFilename": "GoldTicker.exe", "ProductName": "GoldTicker", "ProductVersion": VERSION}
        info = VSVersionInfo(ffi=FixedFileInfo(filevers=version, prodvers=version, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
            kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in fields.items()])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])])
        (ROOT / "windows/version.txt").write_text(str(info), encoding="utf-8")
    dist = ROOT / "dist" / ("macos" if mac else "windows")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist),
                    "--workpath", str(build / "pyinstaller"), str(ROOT / "GoldTicker.spec")], cwd=ROOT, check=True)
    if mac:
        app = dist / "GoldTicker.app"
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
        artifact = dist / "GoldTicker-macOS-Universal2.dmg"
        subprocess.run(["hdiutil", "create", "-volname", "GoldTicker", "-srcfolder", str(app), "-ov", "-format", "UDZO", str(artifact)], check=True)
    else:
        arch = "x64" if platform.machine().lower() in ("amd64", "x86_64") else platform.machine().lower()
        artifact = dist / f"GoldTicker-Windows-{arch}.zip"
        with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(dist / "GoldTicker.exe", "GoldTicker.exe")
        write_hash(dist / "GoldTicker.exe")
    write_hash(artifact)
    print(f"Built {artifact}")


def write_hash(path):
    path.with_name(path.name + ".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
