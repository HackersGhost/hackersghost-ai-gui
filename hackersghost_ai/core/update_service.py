"""Signed GUI release checks and downloads. Never installs or executes downloaded code."""

import base64
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PUBLIC_KEY = "19dd92e2c039bacaded701a2866abb00c8fb76ad40219e46c7a72e3bd88273a7"
PRODUCT = "hackersghost-ai-gui"
DOWNLOAD_BASE = "https://hackersghost.com/downloads/hackersghost-ai-gui/"
FEED = DOWNLOAD_BASE + "latest.json"
MANIFEST_LIMIT = 16 * 1024
PACKAGE_LIMIT = 4 * 1024 * 1024
AUTO_CHECK_INTERVAL = 24 * 60 * 60
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
AUTO_CHECK_FILE = STATE_HOME / "hackersghost-ai" / "gui-last-update-check"


class UpdateError(Exception):
    """A user-safe failure; no response bodies or filesystem contents."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class Release:
    version: str
    sha256: str
    expires: int
    envelope: bytes = field(repr=False)

    @property
    def filename(self) -> str:
        return f"HackersGhost-AI-{self.version}.zip"

    @property
    def url(self) -> str:
        return DOWNLOAD_BASE + self.filename


@dataclass(frozen=True)
class UpdateStatus:
    current_version: str
    latest_version: str | None
    message: str
    release: Release | None = None


def version_tuple(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})", value, re.ASCII):
        raise UpdateError("Invalid GUI release version.")
    return tuple(map(int, value.split(".")))


def verify_manifest(raw: bytes, public_key: str = PUBLIC_KEY) -> Release:
    if len(raw) > MANIFEST_LIMIT:
        raise UpdateError("Update information exceeds the size limit.")
    try:
        envelope = json.loads(raw)
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature, payload)
        info = json.loads(payload)
        if info["product"] != PRODUCT or type(info["schema"]) is not int or info["schema"] != 1:
            raise UpdateError("This release is not a supported GUI update.")
        version_tuple(info["version"])
        if not isinstance(info["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"]):
            raise UpdateError("Invalid release checksum.")
        now = time.time()
        if type(info["expires"]) is not int or not now < info["expires"] <= now + 31 * 86400:
            raise UpdateError("Update information has expired or has an invalid date. Check your system clock.")
        release = Release(info["version"], info["sha256"], info["expires"], raw)
        if info["url"] != release.url:
            raise UpdateError("The update URL is outside the trusted GUI download location.")
        return release
    except (InvalidSignature, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise UpdateError("GUI update signature or format is invalid. Nothing was installed.") from None


def validate_package(package: bytes, release: Release) -> None:
    if len(package) > PACKAGE_LIMIT or hashlib.sha256(package).hexdigest() != release.sha256:
        raise UpdateError("Release checksum mismatch. The download was not saved.")
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(item.file_size for item in entries) > PACKAGE_LIMIT:
                raise UpdateError("The GUI archive exceeds the size limit.")
            names = set()
            files = set()
            root = f"HackersGhost-AI-{release.version}"
            for item in entries:
                parts = item.filename.rstrip("/").split("/")
                mode = stat.S_IFMT(item.external_attr >> 16)
                if (not parts or parts[0] != root or any(part in ("", ".", "..") for part in parts)
                        or "\\" in item.filename or ":" in item.filename
                        or any(ord(c) < 32 for c in item.filename)
                        or item.filename.casefold() in names or item.flag_bits & 1
                        or mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise UpdateError("The GUI archive contains unsafe paths or file types.")
                names.add(item.filename.casefold())
                if item.is_dir():
                    continue
                relative = PurePosixPath(*parts[1:])
                if (relative.as_posix() not in ("README.md", "pyproject.toml", "requirements.txt")
                        and not (len(relative.parts) > 1
                                 and relative.parts[0] in ("hackersghost_ai", "scripts", "tests")
                                 and relative.suffix in (".py", ".sh"))):
                    raise UpdateError("The GUI archive contains unsupported files.")
                archive.read(item)
                files.add(relative.as_posix())
            required = {"hackersghost_ai/gui/app.py", "hackersghost_ai/gui/main_window.py",
                        "hackersghost_ai/__init__.py", "hackersghost_ai/__main__.py",
                        "scripts/run_gui.sh", "requirements.txt", "pyproject.toml"}
            if not required <= files:
                raise UpdateError("The download is not a complete GUI release.")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError, OSError):
        raise UpdateError("The GUI archive is damaged or unsupported.") from None


class UpdateService:
    def __init__(self, current_version: str, *, public_key: str = PUBLIC_KEY):
        version_tuple(current_version)
        self.current_version = current_version
        self.public_key = public_key

    def get_status(self) -> UpdateStatus:
        return UpdateStatus(self.current_version, None, "Automatic update check will run at startup")

    def automatic_check_due(self, *, now: float | None = None) -> bool:
        """Return whether the GUI should make its once-per-day startup check."""
        now = time.time() if now is None else now
        try:
            age = now - AUTO_CHECK_FILE.stat().st_mtime
        except FileNotFoundError:
            return True
        except OSError:
            return True
        return age >= AUTO_CHECK_INTERVAL or age < 0

    def mark_automatic_check(self, *, now: float | None = None) -> None:
        """Persist the startup-check attempt without storing user data."""
        now = time.time() if now is None else now
        parent = AUTO_CHECK_FILE.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            parent.chmod(0o700)
        except OSError:
            pass
        temporary = parent / (AUTO_CHECK_FILE.name + ".new")
        temporary.write_text(str(int(now)), encoding="ascii")
        temporary.chmod(0o600)
        os.replace(temporary, AUTO_CHECK_FILE)
        os.utime(AUTO_CHECK_FILE, (now, now))

    def _fetch(self, url: str, limit: int) -> bytes:
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
            with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise UpdateError("The update download exceeds the size limit.")
            return raw
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code == 404 and url == FEED:
                raise UpdateError("The GUI update channel is not published yet. Your current version is unchanged.") from None
            raise UpdateError("The update server did not return a usable download. Try again later.") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise UpdateError("Could not reach the GUI update server. Check your connection and try again.") from None

    def check(self) -> UpdateStatus:
        release = verify_manifest(self._fetch(FEED, MANIFEST_LIMIT), self.public_key)
        available = version_tuple(release.version) > version_tuple(self.current_version)
        return UpdateStatus(
            self.current_version, release.version,
            f"HackersGhost AI {release.version} is available" if available else "No newer GUI release available.",
            release if available else None,
        )

    def download_release(self, release: Release, destination: str | Path) -> Path:
        verified = verify_manifest(release.envelope, self.public_key)
        if verified != release or version_tuple(verified.version) <= version_tuple(self.current_version):
            raise UpdateError("Check for updates again before downloading.")
        package = self._fetch(verified.url, PACKAGE_LIMIT)
        validate_package(package, verified)
        verify_manifest(verified.envelope, self.public_key)
        destination = Path(destination)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".hg-download-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(package)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            return destination
        except OSError:
            raise UpdateError("Could not save the verified download. Check folder permissions and free disk space.") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
