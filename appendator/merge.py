"""Combinación de PDF, Markdown e imágenes en un único PDF.

pikepdf (qpdf) une las páginas sin cargar los archivos en memoria: los flujos se
copian desde los originales al guardar, así que no hay límite de tamaño práctico.
PyMuPDF solo se usa para generar páginas nuevas (Markdown y separadores) y para
recomprimir imágenes, siempre de un archivo cada vez.
"""

from __future__ import annotations

import html
import io
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pikepdf
import pymupdf
from PIL import Image, ImageOps
from markdown_it import MarkdownIt

PDF_EXTENSIONS = (".pdf",)
MD_EXTENSIONS = (".md", ".markdown")
# MuPDF abre estas directamente (SVG incluido) y respeta la orientación EXIF.
MUPDF_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".bmp",
                          ".tif", ".tiff", ".pnm", ".ppm", ".pgm", ".pbm", ".pam",
                          ".jp2", ".jpx", ".j2k", ".jxr", ".psd", ".svg")
# Estas no las abre MuPDF: Pillow (ya empaquetado con pikepdf) las pasa a PNG.
PILLOW_IMAGE_EXTENSIONS = (".webp", ".avif", ".ico", ".cur", ".tga", ".pcx", ".qoi",
                           ".icns", ".dds", ".sgi", ".xbm", ".xpm")
IMAGE_EXTENSIONS = MUPDF_IMAGE_EXTENSIONS + PILLOW_IMAGE_EXTENSIONS
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS + MD_EXTENSIONS + IMAGE_EXTENSIONS

PAGE = pymupdf.paper_rect("a4")
MARGINS = (56, 56, -56, -56)  # 2 cm
CONTENT = PAGE + MARGINS
CODE_COLUMNS = 80  # caracteres de 9 pt monoespaciados que caben en CONTENT

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.4; color: #222; }
h1 { font-size: 20pt; color: #1f4e79; margin: 0 0 10pt 0; }
h2 { font-size: 16pt; color: #1f4e79; margin: 14pt 0 6pt 0; }
h3 { font-size: 13pt; margin: 12pt 0 4pt 0; }
h4, h5, h6 { font-size: 11pt; margin: 10pt 0 4pt 0; }
p, ul, ol, table, pre, blockquote { margin: 0 0 8pt 0; }
code { font-family: monospace; font-size: 9.5pt; background-color: #f2f2f2; }
pre { font-family: monospace; font-size: 9pt; white-space: pre-wrap; background-color: #f2f2f2; padding: 6pt; }
blockquote { color: #555; margin-left: 12pt; padding-left: 8pt; border-left: 3px solid #ccc; }
table { border-collapse: collapse; }
th, td { border: 1px solid #bbb; padding: 3pt 6pt; }
th { background-color: #e8eef5; }
a { color: #1f4e79; }
.sep { text-align: center; margin-top: 260pt; }
.sep h1 { font-size: 24pt; }
.sep p { color: #666; }
"""


class Cancelled(Exception):
    pass


class MergeError(Exception):
    pass


@dataclass
class Options:
    separators: bool = False
    compress: bool = False
    quality: int = 60  # 10-95


def target_dpi(quality: int) -> int:
    """Resolución máxima de las imágenes para una calidad dada (10 → 95 ppp, 95 → 289 ppp)."""
    return round(72 + (300 - 72) * quality / 100)


def html_to_pdf(body: str, target: Path, base_dir: Path | None = None) -> None:
    # archive permite que el Markdown cargue imágenes con rutas relativas a su carpeta.
    story = pymupdf.Story(html=body, user_css=CSS,
                          archive=str(base_dir) if base_dir else None)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(CONTENT)
        story.draw(device)
        writer.end_page()
    writer.close()
    # Sin subconjunto cada separador incrustaría las fuentes completas (~90 KB).
    with pymupdf.open("pdf", buffer.getvalue()) as doc:
        doc.subset_fonts()
        doc.save(target, garbage=3, deflate=True)


def markdown_to_pdf(source: Path, target: Path) -> None:
    text = source.read_text("utf-8", errors="replace").lstrip("﻿")
    # CommonMark + tablas y tachado, como en GitHub; html=False no ejecuta HTML incrustado.
    md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    tokens = md.parse(text)
    for token in tokens:
        if token.type in ("fence", "code_block"):
            # MuPDF no parte las líneas de <pre>: se cortan a mano para que no se salgan.
            token.content = "\n".join(
                line[i:i + CODE_COLUMNS]
                for line in token.content.split("\n")
                for i in range(0, max(len(line), 1), CODE_COLUMNS))
    body = md.renderer.render(tokens, md.options, {})
    html_to_pdf(body, target, source.parent)


def image_to_pdf(source: Path, target: Path) -> None:
    """Una página A4 por imagen (o por fotograma de un TIFF de varias páginas).

    La orientación sigue a la imagen y se ajusta a los márgenes. Las de mapa de bits
    no se amplían, para que un icono no se convierta en una mancha borrosa.
    """
    if source.suffix.lower() in PILLOW_IMAGE_EXTENSIONS:
        buffer = io.BytesIO()
        with Image.open(source) as im:
            ImageOps.exif_transpose(im).convert("RGBA").save(buffer, "PNG")
        image = pymupdf.open("png", buffer.getvalue())
    else:
        image = pymupdf.open(source)
    vector = source.suffix.lower() == ".svg"
    with image, pymupdf.open("pdf", image.convert_to_pdf()) as src, pymupdf.open() as out:
        for page in src:
            r = page.rect
            width, height = (PAGE.height, PAGE.width) if r.width > r.height else (PAGE.width, PAGE.height)
            new = out.new_page(width=width, height=height)
            area = new.rect + MARGINS
            scale = min(area.width / r.width, area.height / r.height)
            if not vector:
                scale = min(scale, 1)
            w, h = r.width * scale, r.height * scale
            x, y = area.x0 + (area.width - w) / 2, area.y0 + (area.height - h) / 2
            new.show_pdf_page(pymupdf.Rect(x, y, x + w, y + h), src, page.number)
        out.save(target, garbage=3, deflate=True)


def separator_pdf(name: str, index: int, total: int, target: Path) -> None:
    html_to_pdf(f"<div class='sep'><h1>{html.escape(name)}</h1>"
                f"<p>Archivo {index} de {total}</p></div>", target)


def compress_images(source: Path, target: Path, quality: int) -> None:
    dpi = target_dpi(quality)
    with pymupdf.open(source) as doc:
        if doc.needs_pass:
            raise pikepdf.PasswordError
        doc.rewrite_images(dpi_threshold=dpi + 10, dpi_target=dpi, quality=quality)
        doc.save(target, garbage=3, deflate=True)


def merge(files: list[Path], output: Path, options: Options,
          on_progress: Callable[[float | None, str], None] = lambda fraction, text: None,
          cancel: threading.Event | None = None) -> int:
    """Une `files` en `output` y devuelve el número de páginas.

    `on_progress` recibe la fracción completada (None mientras se guarda, sin
    medida) y un texto. Se escribe en un .part que se renombra al terminar: si
    algo falla o se cancela no queda un PDF a medias.
    """
    cancel = cancel or threading.Event()
    total = len(files)
    part = output.with_name(output.name + ".part")
    try:
        with tempfile.TemporaryDirectory(prefix="appendator-") as tmp:
            tmp_dir = Path(tmp)
            parts: list[Path] = []
            pages = 0
            for i, src in enumerate(files, 1):
                if cancel.is_set():
                    raise Cancelled
                on_progress((i - 1) / total, f"({i}/{total}) {src.name}")
                try:
                    if options.separators:
                        parts.append(tmp_dir / f"{i}-separador.pdf")
                        separator_pdf(src.name, i, total, parts[-1])
                        pages += 1
                    pdf = src
                    if src.suffix.lower() in MD_EXTENSIONS:
                        pdf = tmp_dir / f"{i}-markdown.pdf"
                        markdown_to_pdf(src, pdf)
                    elif src.suffix.lower() in IMAGE_EXTENSIONS:
                        pdf = tmp_dir / f"{i}-imagen.pdf"
                        image_to_pdf(src, pdf)
                    if options.compress:
                        compressed = tmp_dir / f"{i}-comprimido.pdf"
                        compress_images(pdf, compressed, options.quality)
                        pdf = compressed
                    with pikepdf.open(pdf, access_mode=pikepdf.AccessMode.stream) as check:
                        pages += len(check.pages)  # también valida el PDF antes de unir
                    parts.append(pdf)
                except pikepdf.PasswordError:
                    raise MergeError(f"{src.name}: está protegido con contraseña.") from None
                except Cancelled:
                    raise
                except Exception as exc:
                    raise MergeError(f"{src.name}: {exc}") from exc

            if cancel.is_set():
                raise Cancelled
            on_progress(None, f"Uniendo y guardando {output.name}…")
            # El trabajo de qpdf (como `qpdf --empty --pages …`) copia los flujos de
            # archivo a archivo sin cargarlos en memoria; pages.extend() sí los carga.
            pikepdf.Job({
                "inputFile": "", "empty": "", "outputFile": str(part),
                "pages": [{"file": str(p)} for p in parts],
                "warningExit0": "",
            }).run()
        if cancel.is_set():
            raise Cancelled
        part.replace(output)
        on_progress(1.0, "Completado")
        return pages
    finally:
        part.unlink(missing_ok=True)
