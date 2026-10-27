"""Búsqueda e instalación de versiones nuevas publicadas en las releases de GitHub.

Solo se consulta GitHub; los archivos del usuario nunca salen del equipo. Lo que
descarga la propia app no lleva la marca de «descargado de Internet», así que la
versión nueva no vuelve a pasar por SmartScreen ni Gatekeeper.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

import certifi

from . import APP_NAME, __version__
from .merge import Cancelled
from .paths import system_env

REPO = "elizechea/appendator"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSET = {"win32": "Appendator.exe", "darwin": "Appendator-macOS.dmg"}.get(
    sys.platform, "Appendator-linux-x86_64.tar.gz")
# Con los certificados de certifi: el Python de la CI de macOS los buscaría en una
# ruta que no existe en los equipos de los usuarios.
_SSL = ssl.create_default_context(cafile=certifi.where())


class UpdateError(Exception):
    pass


@dataclass
class Update:
    version: str
    notes: str
    page: str  # página de la release, por si hay que descargarla a mano
    url: str
    sha256: str
    size: int


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def can_update() -> bool:
    """Desde el código fuente no hay ejecutable que sustituir."""
    return bool(getattr(sys, "frozen", False))


def _get(url: str, timeout: float, headers: dict[str, str] | None = None):
    return urlopen(Request(url, headers={"User-Agent": APP_NAME,
                                         "Accept": "application/vnd.github+json",
                                         **(headers or {})}),
                   timeout=timeout, context=_SSL)


def parse_release(data: dict, current: str = __version__) -> Update | None:
    """La release si es más nueva y trae el archivo de esta plataforma con su huella."""
    if parse_version(data.get("tag_name", "")) <= parse_version(current):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET), None)
    if asset is None:
        return None
    url, digest = asset.get("browser_download_url", ""), asset.get("digest") or ""
    # Solo descargas del propio repositorio y con SHA-256 publicado por GitHub.
    if not url.startswith(DOWNLOAD_PREFIX) or not digest.startswith("sha256:"):
        return None
    return Update(data["tag_name"].lstrip("v"), data.get("body") or "",
                  data.get("html_url", f"https://github.com/{REPO}/releases"),
                  url, digest.removeprefix("sha256:"), int(asset.get("size") or 0))


def check(current: str = __version__) -> Update | None:
    # Sin autenticar, la API admite 60 consultas por hora e IP; en la CI (IP compartida)
    # se usa GITHUB_TOKEN. Solo va a la API, nunca a la URL de descarga.
    token = os.environ.get("GITHUB_TOKEN")
    with _get(LATEST_URL, 10, {"Authorization": f"Bearer {token}"} if token else None) as response:
        return parse_release(json.load(response), current)


def download(update: Update, dest: Path, on_progress: Callable[[float | None, str], None],
             cancel: threading.Event) -> None:
    sha, done = hashlib.sha256(), 0
    total_mb = update.size / 2**20
    try:
        with _get(update.url, 30) as response, open(dest, "wb") as out:
            while chunk := response.read(1 << 20):
                if cancel.is_set():
                    raise Cancelled
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                on_progress(done / update.size if update.size else None,
                            f"Descargando la versión {update.version}… "
                            f"{done / 2**20:.0f} de {total_mb:.0f} MB")
        if sha.hexdigest() != update.sha256:
            raise UpdateError("La descarga no coincide con la huella SHA-256 publicada.")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def current_target() -> Path:
    """Lo que hay que sustituir: el .app en macOS, el ejecutable en Windows y Linux."""
    exe = Path(sys.executable)
    return exe.parents[2] if sys.platform == "darwin" else exe


def staging_path(target: Path) -> Path:
    # Junto al destino (mismo disco), para que el cambio final sea un simple renombrado.
    # Conserva la extensión: PyInstaller solo se reconoce dentro de un *.app.
    return target.with_name(f".{target.stem}.nuevo{target.suffix}")


def old_path(exe: Path) -> Path:
    return exe.with_name(f"{exe.stem}.old{exe.suffix}")


def replace_executable(new: Path, exe: Path) -> None:
    if sys.platform == "win32":
        # Windows deja renombrar un .exe en uso, pero no sobrescribirlo.
        old = old_path(exe)
        old.unlink(missing_ok=True)
        exe.rename(old)
        try:
            new.replace(exe)
        except BaseException:
            old.rename(exe)
            raise
    else:
        new.replace(exe)


def install(update: Update, target: Path, on_progress: Callable[[float | None, str], None],
            cancel: threading.Event) -> Path:
    """Descarga y verifica la versión nueva y la deja lista; devuelve el ejecutable nuevo.

    En Windows y Linux sustituye ya `target`. En macOS deja el .app en staging_path()
    y lo cambia relaunch() cuando esta app se haya cerrado.
    """
    if not os.access(target.parent, os.W_OK):
        raise UpdateError(f"No hay permiso para escribir en {target.parent}.")
    staged = staging_path(target)
    with tempfile.TemporaryDirectory(prefix="appendator-update-") as tmp:
        package = Path(tmp) / ASSET
        download(update, package, on_progress, cancel)
        on_progress(None, f"Instalando la versión {update.version}…")
        if sys.platform == "darwin":
            mount = Path(tmp) / "volumen"
            subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint",
                            str(mount), str(package)], check=True, capture_output=True)
            try:
                shutil.rmtree(staged, ignore_errors=True)
                subprocess.run(["ditto", str(mount / "Appendator.app"), str(staged)],
                               check=True, capture_output=True)
            finally:
                subprocess.run(["hdiutil", "detach", "-force", str(mount)], capture_output=True)
            return staged / "Contents" / "MacOS" / "Appendator"
        try:
            if sys.platform == "win32":
                shutil.copyfile(package, staged)
            else:
                with tarfile.open(package) as tar, open(staged, "wb") as out:
                    member = tar.extractfile("Appendator")
                    if member is None:
                        raise UpdateError("El paquete no contiene el ejecutable.")
                    shutil.copyfileobj(member, out)
                staged.chmod(0o755)
            replace_executable(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        return target


def launch_env() -> dict[str, str]:
    # Sin esto, un ejecutable de PyInstaller lanzado desde otro reutilizaría su entorno.
    env = system_env() or dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def relaunch(target: Path) -> None:
    """Abre la versión nueva; la app debe cerrarse justo después."""
    if sys.platform == "darwin":
        app, staged, old = shlex.quote(str(target)), shlex.quote(str(staging_path(target))), \
            shlex.quote(str(target.with_name(f".{target.name}.old")))
        # Espera a que esta app termine; si algo falla se recupera la versión anterior.
        script = (f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.2; done; "
                  f"rm -rf {old}; mv {app} {old} && "
                  f"{{ mv {staged} {app} || mv {old} {app}; }}; rm -rf {old}; open {app}")
        subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True)
    else:
        subprocess.Popen([str(target)], env=launch_env(),
                         **({"creationflags": subprocess.DETACHED_PROCESS}
                            if sys.platform == "win32" else {"start_new_session": True}))


def cleanup_previous() -> None:
    """Borra lo que dejó una actualización anterior (en Windows, el .exe renombrado)."""
    if can_update() and sys.platform == "win32":
        try:
            old_path(current_target()).unlink(missing_ok=True)
        except OSError:
            pass  # la versión anterior aún se está cerrando: se borrará la próxima vez
