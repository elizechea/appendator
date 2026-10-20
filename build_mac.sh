#!/bin/bash
# Compila Appendator.app y Appendator-macOS.dmg en un Mac con chip M.
# Requiere uv (https://docs.astral.sh/uv/) o Python 3.12 de python.org (incluye Tk).
set -euo pipefail
cd "$(dirname "$0")"
if command -v uv >/dev/null; then
    [ -d .venv ] || uv venv --python 3.12 .venv
    source .venv/bin/activate
    uv pip install -r requirements-build.txt
else
    [ -d .venv ] || "${PYTHON:-python3.12}" -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements-build.txt
fi
python -m pytest -q tests
pyinstaller --noconfirm --clean Appendator.spec
codesign --force --deep --sign - dist/Appendator.app
rm -rf dmg && mkdir dmg && cp -R dist/Appendator.app dmg/ && ln -s /Applications dmg/Aplicaciones
hdiutil create -volname Appendator -srcfolder dmg -ov -format UDZO dist/Appendator-macOS.dmg
rm -rf dmg
echo "Listo: dist/Appendator.app y dist/Appendator-macOS.dmg"
