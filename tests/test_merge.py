import threading
from pathlib import Path

import pikepdf
import pymupdf
import pytest

from appendator.merge import Cancelled, MergeError, Options, merge
from appendator.paths import output_path_for


def make_pdf(path: Path, pages: int, image: bool = False) -> Path:
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{path.stem} página {n + 1}")
        if image:
            # Imagen de ruido 1500x1500 sin pérdida: mucho margen para comprimir.
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1500, 1500), False)
            import random
            pix.set_rect(pix.irect, (200, 120, 40))
            for _ in range(20000):
                pix.set_pixel(random.randrange(1500), random.randrange(1500),
                              (random.randrange(256),) * 3)
            page.insert_image(pymupdf.Rect(72, 100, 300, 328), pixmap=pix)
    doc.save(path)
    return path


def texts(path: Path) -> list[str]:
    with pymupdf.open(path) as doc:
        return [p.get_text() for p in doc]


def test_merge_pdf_and_markdown_with_separators(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 2)
    md = tmp_path / "notas.md"
    md.write_text("# Título\n\nTexto **negrita** y `código`.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
                  "```\nprint('hola')\n" + "x" * 200 + "\n```\n\n- uno\n- dos\n", "utf-8")
    out = tmp_path / "out.pdf"
    pages = merge([a, md], out, Options(separators=True))
    t = texts(out)
    assert pages == len(t) == 5  # separador + 2 + separador + 1
    assert "a.pdf" in t[0] and "Archivo 1 de 2" in t[0]
    assert "a página 2" in t[2]
    assert "notas.md" in t[3] and "Archivo 2 de 2" in t[3]
    assert "Título" in t[4] and "print('hola')" in t[4]
    assert t[4].count("x") >= 200  # la línea larga de código se parte, no se recorta
    assert not (tmp_path / "out.pdf.part").exists()


def test_merge_without_separators_keeps_order(tmp_path):
    files = [make_pdf(tmp_path / f"{n}.pdf", 1) for n in ("z", "b", "m")]
    out = tmp_path / "out.pdf"
    assert merge(files, out, Options()) == 3
    assert [t.split()[0] for t in texts(out)] == ["z", "b", "m"]


def test_compression_reduces_size(tmp_path):
    big = make_pdf(tmp_path / "img.pdf", 1, image=True)
    plain, small = tmp_path / "plain.pdf", tmp_path / "small.pdf"
    merge([big], plain, Options())
    merge([big], small, Options(compress=True, quality=30))
    assert small.stat().st_size < plain.stat().st_size / 2
    assert len(texts(small)) == 1


def test_password_protected_pdf_is_reported(tmp_path):
    src = make_pdf(tmp_path / "plain.pdf", 1)
    locked = tmp_path / "secreto.pdf"
    with pikepdf.open(src) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(user="x", owner="y"))
    out = tmp_path / "out.pdf"
    with pytest.raises(MergeError, match="secreto.pdf.*contraseña"):
        merge([src, locked], out, Options())
    assert not out.exists() and not (tmp_path / "out.pdf.part").exists()


def test_cancel_leaves_nothing(tmp_path):
    cancel = threading.Event()
    cancel.set()
    out = tmp_path / "out.pdf"
    with pytest.raises(Cancelled):
        merge([make_pdf(tmp_path / "a.pdf", 1)], out, Options(), cancel=cancel)
    assert list(tmp_path.iterdir()) == [tmp_path / "a.pdf"]


def test_output_name_does_not_overwrite(tmp_path):
    first = output_path_for(Path("x/Informe: final.pdf"), tmp_path)
    assert first.name == "Informe_ final - combinado.pdf"
    first.write_bytes(b"")
    assert output_path_for(Path("Informe: final.md"), tmp_path).name == "Informe_ final - combinado (2).pdf"


def test_images_become_pages(tmp_path):
    from PIL import Image

    Image.new("RGB", (3000, 1000), (200, 60, 60)).save(tmp_path / "ancha.png")
    Image.new("RGB", (40, 60), (0, 0, 255)).save(tmp_path / "icono.webp")  # vía Pillow
    (tmp_path / "dibujo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">'
        '<text x="10" y="100">Hola SVG</text></svg>', "utf-8")
    frames = [Image.new("RGB", (100, 100), c) for c in ((255, 0, 0), (0, 255, 0))]
    frames[0].save(tmp_path / "multi.tiff", save_all=True, append_images=frames[1:])
    files = [tmp_path / n for n in ("ancha.png", "icono.webp", "dibujo.svg", "multi.tiff")]
    out = tmp_path / "out.pdf"
    assert merge(files, out, Options(separators=True)) == 9  # 4 separadores + 5 páginas
    with pymupdf.open(out) as doc:
        ancha, icono, svg = doc[1], doc[3], doc[5]
        assert ancha.rect.width > ancha.rect.height  # imagen apaisada → A4 horizontal
        assert "Hola SVG" in svg.get_text()
        span = svg.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
        assert span["size"] > 20  # el SVG (vectorial) sí se amplía: 12 pt → ~29 pt
        # El icono no se amplía: ocupa sus 40x60 px (30x45 pt), no la página entera.
        assert pymupdf.Rect(icono.get_image_info()[0]["bbox"]).width < 100
