"""Autocomprobación del ejecutable (se usa en CI para validar cada versión).

    Appendator --self-test [--report ruta.txt]

Verifica que PyMuPDF, pikepdf y Tk están empaquetados y funcionan, y combina de
principio a fin un PDF con imagen y un Markdown, con separadores y compresión.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def _arg(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def run_self_test(argv: list[str]) -> int:
    report_path = _arg(argv, "--report")
    lines: list[str] = []
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f"OK   {name}: {fn()}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}:\n{traceback.format_exc()}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        def combine():
            import pymupdf
            from appendator.merge import Options, merge

            pdf = tmp_path / "imagen.pdf"
            doc = pymupdf.open()
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1200, 1200), False)
            pix.set_rect(pix.irect, (30, 120, 200))
            doc.new_page().insert_image(pymupdf.Rect(72, 72, 400, 400), pixmap=pix)
            doc.save(pdf)
            md = tmp_path / "notas.md"
            md.write_text("# Notas\n\n| A | B |\n|---|---|\n| ñ | 日本 |\n", "utf-8")
            out = tmp_path / "out.pdf"
            pages = merge([pdf, md], out, Options(separators=True, compress=True, quality=50))
            text = "".join(p.get_text() for p in pymupdf.open(out))
            if pages != 4 or "notas.md" not in text or "Notas" not in text:
                raise RuntimeError(f"{pages} páginas, texto: {text!r}")
            return f"{pages} páginas, {out.stat().st_size} bytes"

        def versions():
            import markdown_it
            import pikepdf
            import pymupdf
            return (f"PyMuPDF {pymupdf.VersionBind}, pikepdf {pikepdf.__version__} "
                    f"(qpdf {pikepdf.__libqpdf_version__}), markdown-it {markdown_it.__version__}")

        def tk():
            import tkinter
            if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
                # Abrir una ventana comprueba que Tcl/Tk encuentra sus archivos.
                root = tkinter.Tk()
                root.destroy()
            return f"Tk {tkinter.TkVersion}"

        def downloads():
            from appendator.paths import downloads_dir
            return str(downloads_dir())

        check("bibliotecas", versions)
        check("combinar PDF + Markdown con separadores y compresión", combine)
        check("tkinter", tk)
        check("carpeta Descargas", downloads)

    text = "\n".join(lines) + f"\n\nRESULTADO: {'OK' if ok else 'FALLO'}\n"
    print(text)
    if report_path:
        Path(report_path).write_text(text, encoding="utf-8")
    return 0 if ok else 1
