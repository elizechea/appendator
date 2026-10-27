# Appendator

App de escritorio (tkinter + PyInstaller) que une PDF, Markdown e imágenes en un único PDF,
en local. Windows `.exe`, macOS arm64 `.app`/`.dmg`, Linux x86_64. Hermana de
`elizechea/transcriptor`: mismo esqueleto (paths, selftest, spec, CI); si cambias
algo común, mira cómo está allí.

## Comandos

- Entorno: `uv venv --python 3.12 && uv pip install -r requirements-build.txt`
- Tests: `.venv/bin/python -m pytest -q tests`
- Ejecutar: `.venv/bin/python main.py`
- Autotest: `.venv/bin/python main.py --self-test`
- Compilar: `./build_mac.sh`, `./build_linux.sh`, `build.bat`

## Decisiones que no se deben deshacer

- **La unión la hace `pikepdf.Job` (qpdf `--empty --pages`)**, no
  `Pdf.pages.extend()`: `extend()` carga todos los flujos en memoria (1,2 GB de RAM
  para 1,1 GB de PDF) y Job los copia en streaming (~100 MB). Es lo que garantiza
  «sin límite de tamaño».
- **PyMuPDF fijado en 1.x**: la 2.x arrastra onnxruntime, numpy y pymupdf4llm.
  Solo se usa para generar páginas (Story HTML) y `rewrite_images`, siempre sobre
  un archivo cada vez.
- **markdown-it-py en modo CommonMark** (+ tablas, tachado), con `html=False`.
  Python-Markdown no reconoce listas anidadas con 2 espacios.
- Imágenes: MuPDF abre las de `MUPDF_IMAGE_EXTENSIONS` (incl. SVG, respeta EXIF);
  las de `PILLOW_IMAGE_EXTENSIONS` pasan antes a PNG con Pillow (ya viene con
  pikepdf, no es dependencia nueva). HEIC necesitaría pillow-heif: no está.
- MuPDF no parte líneas de `<pre>`: `merge.py` corta el código a `CODE_COLUMNS`.
- Las páginas generadas se guardan con `subset_fonts()`: sin ello cada separador
  ocupa ~90 KB.
- La salida se escribe en `.part` y se renombra al final; error o cancelación no
  dejan PDF a medias.
- Licencia: código propio MIT; los ejecutables son AGPL-3.0 por PyMuPDF. No añadas
  dependencias GPL/AGPL nuevas ni código copiado de PyMuPDF sin revisarlo.

## Convenciones

- Textos de la interfaz, comentarios, docs y commits en español.
- Versión en tres sitios: `appendator/__init__.py`, `Appendator.spec`,
  `version_info.txt`.
- Release: etiqueta `v*` o *Run workflow* con el campo *release*.
