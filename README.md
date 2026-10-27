# Appendator

Aplicación de escritorio para **Windows** (un único `Appendator.exe`), **macOS con
chip Apple M1/M2/M3/M4…** (`Appendator.app`, macOS 13 Ventura o posterior) y **Linux
x86_64** (un único ejecutable `Appendator`) que une varios **PDF** y **Markdown**
e **imágenes** en un único PDF y lo guarda en la carpeta **Descargas**.

Todo el proceso ocurre en el propio equipo: los archivos no se envían a ningún servidor.

- **Sin límite de tamaño**: las páginas se copian de archivo a archivo con
  [qpdf](https://qpdf.readthedocs.io/) sin cargarlas en memoria (unir 1,1 GB de PDF
  usa unos 100 MB de RAM).
- **Markdown formateado**: los `.md` se convierten a PDF A4 con títulos, negritas,
  listas, tablas, bloques de código, citas e imágenes (rutas relativas al `.md`).
- **Imágenes como páginas**: PNG, JPG, GIF, BMP, TIFF (una página por fotograma),
  SVG, WebP, AVIF, JPEG 2000, PSD, ICO, TGA y otros formatos habituales (no HEIC).
  Cada imagen ocupa una página A4 en vertical u horizontal según su forma,
  respetando el giro de las fotos del móvil. Las de mapa de bits se reducen para
  caber pero nunca se amplían; los SVG se ajustan a la página.
- **Separadores para IA** (opcional): antes de cada archivo se añade una página con
  su nombre y «Archivo N de M», de modo que una IA que lea el PDF detecta fácilmente
  dónde empieza cada documento.
- **Compresión de imágenes** (opcional) con un control de calidad de 10 a 95.

## Primera ejecución: el sistema la bloquea

La aplicación no está firmada con un certificado de pago de Apple ni de Microsoft,
así que la primera vez el sistema la bloquea. Solo hay que autorizarla una vez.

### Mac: «No se ha abierto "Appendator.app"»

1. Descarga `Appendator-macOS.dmg` de la *Release*, ábrelo y arrastra
   **Appendator** a **Aplicaciones**.
2. Abre la app. Aparece el aviso *«Apple no ha podido verificar que
   "Appendator.app" no contenga software malicioso»*: pulsa **OK / Hecho**
   (**no** «Trasladar a la papelera»).
3. Ve a **Ajustes del Sistema → Privacidad y seguridad**, baja hasta la sección
   **Seguridad** y pulsa **Abrir igualmente** junto al mensaje sobre Appendator.
4. Vuelve a abrir la app, pulsa **Abrir igualmente** en el nuevo aviso y confirma
   con tu contraseña o Touch ID.

Alternativa en Terminal (hace lo mismo en un paso):

```bash
xattr -dr com.apple.quarantine /Applications/Appendator.app
```

La primera vez que guarde un PDF, macOS pedirá permiso para acceder a la carpeta
Descargas: acéptalo.

### Windows: «Windows protegió su PC»

1. Al abrir `Appendator.exe` aparece la pantalla azul de **SmartScreen**.
2. Pulsa **Más información** y después **Ejecutar de todas formas**.

Si el navegador avisa al descargarlo de que «no se descarga habitualmente», elige
**Conservar**. Si Windows lo bloquea sin ofrecer *Ejecutar de todas formas*, haz clic
derecho en el `.exe` → **Propiedades**, marca **Desbloquear** y pulsa **Aceptar**.

### Linux

Descomprime el `.tar.gz` (conserva el permiso de ejecución) y abre `Appendator`:

```bash
tar -xzf Appendator-linux-x86_64.tar.gz
./Appendator
```

Funciona en cualquier distribución con glibc 2.35 o posterior (Ubuntu 22.04,
Debian 12, Fedora 36 o más recientes) sin instalar nada. La CI lo prueba en Ubuntu
22.04 y en la última Fedora.

## Uso

1. Añade archivos con **Añadir archivos…** (en Windows también arrastrándolos a la
   ventana, incluso carpetas completas: se añaden sus PDF, `.md` e imágenes en orden
   alfabético).
2. Ordénalos con **Subir** y **Bajar**: el PDF final sigue el orden de la lista.
3. Elige las opciones:
   - **Página con el nombre del archivo antes de cada uno**.
   - **Comprimir imágenes** y su **calidad**. La etiqueta indica la calidad JPEG y la
     resolución máxima a la que se reducen las imágenes (de 95 ppp con calidad 10 a
     289 ppp con calidad 95). Las imágenes por debajo de esa resolución solo se
     recomprimen.
4. Pulsa **Combinar**. El resultado se guarda como `<primer archivo> - combinado.pdf`
   en Descargas (sin sobrescribir nunca: `… (2).pdf`, `… (3).pdf`…).

Si un archivo está dañado o protegido con contraseña, se avisa indicando cuál y no
se guarda nada. Al cancelar tampoco queda ningún PDF a medias.

## Descargar

Las versiones publicadas están en
[Releases](https://github.com/elizechea/appendator/releases): `Appendator.exe`
para Windows, `Appendator-macOS.dmg` para Mac y `Appendator-linux-x86_64.tar.gz`
para Linux.

Cada push compila las tres en GitHub Actions (workflow *Build*), las prueba con una
combinación real y las publica como artefactos. Para publicar una *Release*, crea una
etiqueta `v*` (por ejemplo `v1.1.0`) o lanza el workflow a mano (*Run workflow*)
indicando la versión en el campo *release*: la release solo se crea si las tres
versiones superan el autotest.

## Compilar en local

| Sistema | Comando | Resultado |
|---|---|---|
| Windows (Python 3.12 de python.org) | `build.bat` | `dist\Appendator.exe` |
| Mac con chip M ([uv](https://docs.astral.sh/uv/) o Python 3.12 de python.org) | `./build_mac.sh` | `dist/Appendator.app` y `.dmg` |
| Linux (preferiblemente con uv) | `./build_linux.sh` | `dist/Appendator` y `.tar.gz` |

En Linux el ejecutable funciona en distribuciones con una glibc igual o más nueva
que la del equipo donde se compila (la CI usa Ubuntu 22.04).

Para ejecutar desde el código fuente:

```bash
uv venv --python 3.12 && uv pip install -r requirements-build.txt
.venv/bin/python main.py
```

Autotest del ejecutable (lo usa la CI): `Appendator --self-test [--report informe.txt]`
(en Mac: `Appendator.app/Contents/MacOS/Appendator --self-test …`).

## Estructura

- `main.py` — punto de entrada.
- `appendator/gui.py` — interfaz (tkinter).
- `appendator/merge.py` — conversión de Markdown e imágenes, separadores, compresión y unión.
- `appendator/paths.py` — carpeta Descargas real, ajustes y registros.
- `appendator/selftest.py` — autotest del ejecutable.
- `Appendator.spec` — configuración de PyInstaller.

Los registros de errores están en `%LOCALAPPDATA%\Appendator\appendator.log`
(Windows), `~/Library/Application Support/Appendator/appendator.log` (Mac) o
`~/.local/share/Appendator/appendator.log` (Linux).

## Licencia

El código de este repositorio es [MIT](LICENSE): úsalo, modifícalo y redistribúyelo
como quieras.

Los **ejecutables** publicados incluyen [PyMuPDF](https://pymupdf.readthedocs.io/),
que es [AGPL-3.0](LICENSE.AGPL-3.0); por eso cada ejecutable, como obra combinada,
se distribuye bajo AGPL-3.0 (su código fuente es este repositorio). Si reutilizas el
código sin PyMuPDF, solo aplica la MIT.

Resto de dependencias empaquetadas: pikepdf (MPL-2.0), qpdf (Apache-2.0),
markdown-it-py y mdurl (MIT), Pillow (MIT-CMU), lxml (BSD-3-Clause), windnd (MIT,
solo Windows) y el cargador de PyInstaller (GPL-2.0 con excepción que permite
distribuir el ejecutable bajo cualquier licencia).
