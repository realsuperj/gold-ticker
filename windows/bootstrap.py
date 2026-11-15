"""Windows entry: prefer WinUI shell; GOLD_TICKER_UI=tk falls back to legacy Tk."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _find_winui_exe() -> Path | None:
    env = os.environ.get("GOLDTICKER_WINUI")
    if env and Path(env).is_file():
        return Path(env)
    candidates = [
        REPO / "winui" / "GoldTicker.WinUI" / "bin" / "x64" / "Release" / "net8.0-windows10.0.19041.0" / "GoldTicker.WinUI.exe",
        REPO / "winui" / "GoldTicker.WinUI" / "bin" / "x64" / "Debug" / "net8.0-windows10.0.19041.0" / "GoldTicker.WinUI.exe",
        REPO / "winui" / "GoldTicker.WinUI" / "bin" / "Release" / "net8.0-windows10.0.19041.0" / "win-x64" / "GoldTicker.WinUI.exe",
        REPO / "dist" / "windows" / "GoldTicker.WinUI.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p
    # Any built exe under winui/
    matches = sorted((REPO / "winui").rglob("GoldTicker.WinUI.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def main() -> None:
    if os.environ.get("GOLD_TICKER_UI", "").lower() == "tk":
        from windows.main import main as run_tk
        run_tk()
        return

    exe = _find_winui_exe()
    if exe:
        env = os.environ.copy()
        env.setdefault("GOLDTICKER_ROOT", str(REPO))
        raise SystemExit(subprocess.call([str(exe)], cwd=str(REPO), env=env))

    dotnet = shutil.which("dotnet")
    proj = REPO / "winui" / "GoldTicker.WinUI" / "GoldTicker.WinUI.csproj"
    if dotnet and proj.is_file():
        env = os.environ.copy()
        env.setdefault("GOLDTICKER_ROOT", str(REPO))
        raise SystemExit(subprocess.call(
            [dotnet, "run", "--project", str(proj), "-c", "Release", "-p:Platform=x64"],
            cwd=str(REPO), env=env))

    # 发布包 / 无 SDK 环境：回退现有 Tk 壳，避免直接起不来
    from windows.main import main as run_tk
    run_tk()

