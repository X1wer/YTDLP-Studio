"""Belépési pont: ``python -m ytstudio`` vagy a PyInstaller EXE."""


def main() -> int:
    from .ui.app import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
