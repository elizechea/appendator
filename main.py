"""Punto de entrada de Appendator (también el del ejecutable generado con PyInstaller)."""

from __future__ import annotations

import logging
import os
import sys

# En un .exe sin consola sys.stdout/sys.stderr son None y cualquier print de una
# librería provocaría una excepción.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _setup_logging() -> None:
    from appendator.paths import log_file

    handlers: list[logging.Handler] = []
    try:
        path = log_file()
        if path.exists() and path.stat().st_size > 5_000_000:
            path.unlink()
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    except Exception:
        pass
    handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> int:
    _setup_logging()
    if "--self-test" in sys.argv:
        from appendator.selftest import run_self_test

        return run_self_test(sys.argv)
    _enable_dpi_awareness()
    from appendator.gui import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
