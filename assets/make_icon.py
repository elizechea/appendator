"""Genera assets/icon.png, icon.ico (Windows) e icon.icns (macOS) (tres páginas apiladas).

    uv run --with pillow assets/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
S = 512


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(31, 78, 121))
    # Tres páginas desplazadas: varios documentos que se convierten en uno.
    for i, color in enumerate(((120, 200, 255), (190, 228, 255), (255, 255, 255))):
        x, y = 96 + i * 44, 80 + i * 44
        d.rounded_rectangle((x, y, x + 236, y + 300), radius=22, fill=color,
                            outline=(31, 78, 121), width=8)
    for j, width in enumerate((150, 120, 150, 90)):
        y = 230 + j * 44
        d.rounded_rectangle((218, y, 218 + width, y + 18), radius=9, fill=(31, 78, 121))
    return img


if __name__ == "__main__":
    img = draw()
    img.save(HERE / "icon.png")
    img.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                       (128, 128), (256, 256)])
    img.resize((1024, 1024), Image.LANCZOS).save(HERE / "icon.icns")
