"""Public entry for source, local builds and release builds."""
import sys


def main():
    if "--smoke-test" in sys.argv:
        from core.smoke import run_smoke
        run_smoke()
        return
    if sys.platform == "darwin":
        from mac.main import main as run
    elif sys.platform == "win32":
        from windows.bootstrap import main as run
    else:
        raise SystemExit("GoldTicker supports macOS and Windows.")
    run()


if __name__ == "__main__":
    main()
