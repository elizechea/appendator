import hashlib
import io
import sys
import tarfile
import threading

import pytest

from appendator import updater
from appendator.updater import Update, UpdateError, parse_release, parse_version

URL = f"{updater.DOWNLOAD_PREFIX}v2.0.0/{updater.ASSET}"


def release(tag="v2.0.0", url=URL, digest="sha256:" + "a" * 64):
    return {"tag_name": tag, "body": "Novedades", "html_url": "https://github.com/x",
            "assets": [{"name": updater.ASSET, "browser_download_url": url,
                        "digest": digest, "size": 10}]}


def test_parse_release_only_accepts_newer_verified_assets():
    assert parse_version("v1.10.0") > parse_version("1.9.3")
    update = parse_release(release(), current="1.1.0")
    assert update and update.version == "2.0.0" and update.sha256 == "a" * 64
    assert parse_release(release(tag="v1.1.0"), current="1.1.0") is None
    assert parse_release(release(url="https://evil.example/x"), current="1.1.0") is None
    assert parse_release(release(digest=None), current="1.1.0") is None


def fake_update(tmp_path, content: bytes, digest: str | None = None) -> Update:
    src = tmp_path / "publicado"
    src.write_bytes(content)
    return Update("2.0.0", "", "", src.as_uri(), digest or hashlib.sha256(content).hexdigest(),
                  len(content))


def test_download_rejects_wrong_digest(tmp_path):
    dest = tmp_path / "descarga"
    updater.download(fake_update(tmp_path, b"bueno"), dest, lambda *a: None, threading.Event())
    assert dest.read_bytes() == b"bueno"
    with pytest.raises(UpdateError, match="SHA-256"):
        updater.download(fake_update(tmp_path, b"malo", "0" * 64), dest, lambda *a: None,
                         threading.Event())
    assert not dest.exists()


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_replace_executable(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    exe = tmp_path / "Appendator.exe"
    new = updater.staging_path(exe)
    exe.write_bytes(b"viejo")
    new.write_bytes(b"nuevo")
    updater.replace_executable(new, exe)
    assert exe.read_bytes() == b"nuevo" and not new.exists()
    assert updater.old_path(exe).exists() == (platform == "win32")


@pytest.mark.skipif(sys.platform == "win32", reason="permisos de ejecución de Unix")
def test_install_linux_package(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("Appendator")
        info.size = 5
        tar.addfile(info, io.BytesIO(b"nuevo"))
    exe = tmp_path / "bin" / "Appendator"
    exe.parent.mkdir()
    exe.write_bytes(b"viejo")
    updater.install(fake_update(tmp_path, buffer.getvalue()), exe, lambda *a: None,
                    threading.Event())
    assert exe.read_bytes() == b"nuevo" and exe.stat().st_mode & 0o111
    assert list(exe.parent.iterdir()) == [exe]
