#!/usr/bin/env python3
"""Standalone first-time Linux GUI installer. No remote shell scripts.

Downloaded releases are never extracted or executed before an Ed25519
signature, SHA-256 checksum and archive layout have been verified.
The publisher's PRIVATE signing key is never used or requested.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

PUBLIC_KEY = "19dd92e2c039bacaded701a2866abb00c8fb76ad40219e46c7a72e3bd88273a7"
BASE_URL = "https://hackersghost.com/downloads/hackersghost-ai-gui/"
FEED = BASE_URL + "latest.json"
MAX_MANIFEST = 16 * 1024
MAX_ARCHIVE = 4 * 1024 * 1024
PYTHON_PACKAGES = ("cryptography>=46,<49", "PySide6>=6.6,<7")
SHORTCUT = "hackersghost-ai-gui.desktop"


class InstallError(Exception):
    """A safe, concise installation diagnostic."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, limit: int) -> bytes:
    if url != FEED and not re.fullmatch(
        re.escape(BASE_URL) + r"HackersGhost-AI-(0|[1-9][0-9]{0,5})\."
        r"(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.zip", url,
    ):
        raise InstallError("Untrusted download URL.")
    try:
        with urllib.request.build_opener(NoRedirect).open(
            urllib.request.Request(url, headers={"Accept": "application/octet-stream"}), timeout=20
        ) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError):
        raise InstallError("Could not download the official GUI release.") from None
    if len(data) > limit:
        raise InstallError("The download is larger than the permitted limit.")
    return data


def verify_manifest(raw: bytes, *, public_key: str = PUBLIC_KEY, now: int | None = None) -> dict:
    """Return trusted release metadata only after verifying the signed payload."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if len(raw) > MAX_MANIFEST:
        raise InstallError("The signed release manifest is too large.")
    try:
        envelope = json.loads(raw)
        payload = base64.b64decode(envelope["payload"], validate=True)
        signature = base64.b64decode(envelope["signature"], validate=True)
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature, payload)
        info = json.loads(payload)
        if info["product"] != "hackersghost-ai-gui" or type(info["schema"]) is not int or info["schema"] != 1:
            raise InstallError("The signed release is not a supported GUI package.")
        version = info["version"]
        if not isinstance(version, str) or not re.fullmatch(
            r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})", version
        ):
            raise InstallError("Invalid signed GUI version.")
        if not isinstance(info["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", info["sha256"]):
            raise InstallError("Invalid signed checksum.")
        current = int(time.time()) if now is None else now
        if type(info["expires"]) is not int or not current < info["expires"] <= current + 31 * 86400:
            raise InstallError("The release signature has expired or your system clock is incorrect.")
        if info["url"] != BASE_URL + f"HackersGhost-AI-{version}.zip":
            raise InstallError("The signed release URL is not trusted.")
    except (InvalidSignature, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise InstallError("GUI release signature or manifest format is invalid.") from None
    return info


def verify_archive(data: bytes, info: dict) -> list:
    """Validate all ZIP entries before any filesystem extraction or execution."""
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != info["sha256"]:
        raise InstallError("GUI download failed its SHA-256 checksum.")
    names = set()
    files = set()
    expected_root = "HackersGhost-AI-" + info["version"]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 200 or sum(item.file_size for item in entries) > MAX_ARCHIVE:
                raise InstallError("GUI release archive exceeds safety limits.")
            for item in entries:
                name = item.filename
                parts = name.rstrip("/").split("/")
                mode = stat.S_IFMT(item.external_attr >> 16)
                if (
                    len(parts) < 2 or parts[0] != expected_root
                    or any(part in ("", ".", "..") for part in parts)
                    or "\\" in name or ":" in name or any(ord(char) < 32 for char in name)
                    or name.casefold() in names or item.flag_bits & 1
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                ):
                    raise InstallError("GUI release archive has unsafe paths or types.")
                names.add(name.casefold())
                if item.is_dir():
                    continue
                relative = "/".join(parts[1:])
                if not (
                    relative in ("README.md", "requirements.txt", "pyproject.toml")
                    or (
                        len(parts) > 2 and parts[1] in ("hackersghost_ai", "scripts", "tests")
                        and Path(relative).suffix in (".py", ".sh")
                    )
                ):
                    raise InstallError("GUI release archive contains an unsupported file.")
                # Read the entire member before trusting it (ZIP integrity check).
                archive.read(item)
                files.add(relative)
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        raise InstallError("The GUI release archive is corrupted.") from None
    required = {
        "hackersghost_ai/gui/app.py", "hackersghost_ai/gui/main_window.py",
        "hackersghost_ai/__init__.py", "hackersghost_ai/__main__.py",
        "scripts/run_gui.sh", "scripts/launch_gui.py",
        "requirements.txt", "pyproject.toml",
    }
    if not required <= files:
        raise InstallError("The GUI release is missing required application files.")
    return entries


def load_release(*, manifest_path: Path | None = None, archive_path: Path | None = None) -> tuple[dict, bytes]:
    if (manifest_path is None) != (archive_path is None):
        raise InstallError("Provide both a local manifest and ZIP, or neither.")
    if manifest_path:
        if manifest_path.stat().st_size > MAX_MANIFEST or archive_path.stat().st_size > MAX_ARCHIVE:
            raise InstallError("Local release file exceeds size limits.")
        envelope = manifest_path.read_bytes()
    else:
        envelope = _fetch(FEED, MAX_MANIFEST)
    info = verify_manifest(envelope)
    package = archive_path.read_bytes() if archive_path else _fetch(info["url"], MAX_ARCHIVE)
    verify_archive(package, info)
    return info, package


def _root() -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data.is_absolute():
        data = Path.home() / ".local/share"
    return data / "hackersghost-ai-gui"


def _secure_dir(folder: Path) -> None:
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise InstallError("Unsafe existing installation directory.")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if hasattr(os, "getuid") and folder.stat().st_uid != os.getuid():
        raise InstallError("Installation folder is not owned by your Linux user.")
    folder.chmod(0o700)


def _existing_launcher() -> bool:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data.is_absolute():
        data = Path.home() / ".local/share"
    shortcut = data / "applications" / SHORTCUT
    return shortcut.exists() or shortcut.is_symlink()


def _run(command: list[str], *, timeout: int, extra_env: dict | None = None) -> None:
    env = {
        key: value for key, value in os.environ.items()
        if key not in ("OPENAI_API_KEY", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")
        and not key.endswith("_API_KEY") and not key.startswith("HACKERSGHOST_")
    }
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise InstallError("The Python setup or GUI startup check could not complete.") from None
    if result.returncode != 0:
        raise InstallError("The Python setup or GUI startup check failed. Review the installation requirements.")


def prepare_runtime(base: Path) -> Path:
    """Create a private runtime once, without changing system Python or the CLI."""
    _secure_dir(base)
    runtime = base / "runtime"
    if runtime.is_symlink():
        raise InstallError("The GUI runtime is a symbolic link.")
    if not runtime.exists():
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(runtime)],
                check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise InstallError(
                "Could not create a Python environment. Install python3-venv and python3-pip "
                "from your distribution first."
            ) from None
    python = runtime / "bin/python"
    if not python.is_file():
        raise InstallError("The GUI Python runtime is incomplete.")
    # Downloads exclusively from PyPI; no sudo, system-wide pip or shell pipe.
    _run([
        str(python), "-m", "pip", "--isolated", "install", "--no-input",
        "--disable-pip-version-check", "--index-url", "https://pypi.org/simple",
        *PYTHON_PACKAGES,
    ], timeout=240)
    return python


def install_verified(package: bytes, info: dict, *, python: Path, base: Path) -> Path:
    """Install signed GUI side-by-side; never overwrite existing app or shortcut."""
    verify_archive(package, info)
    if _existing_launcher():
        raise InstallError(
            "A HackersGhost AI GUI shortcut already exists. Use your existing GUI's update button instead."
        )
    _secure_dir(base)
    releases = base / "releases"
    _secure_dir(releases)
    destination = releases / f"HackersGhost-AI-{info['version']}"
    if destination.exists() or destination.is_symlink():
        raise InstallError("This GUI version is already installed. Nothing was overwritten.")
    stage = Path(tempfile.mkdtemp(prefix=".hg-install-", dir=releases))
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            prefix = f"HackersGhost-AI-{info['version']}/"
            for item in archive.infolist():
                if item.is_dir():
                    continue
                name = item.filename.removeprefix(prefix)
                output = stage.joinpath(*name.split("/"))
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("xb") as handle:
                    handle.write(archive.read(item))
                output.chmod(0o600)

        # Code execution only after signed checksum, ZIP verification and extraction.
        check = (
            "import sys; sys.path.insert(0,sys.argv[1]); "
            "from hackersghost_ai import __version__; "
            "from hackersghost_ai.gui.app import build_window; "
            "assert __version__ == sys.argv[2]"
        )
        _run([str(python), "-I", "-c", check, str(stage), info["version"]], timeout=30)
        stage.rename(destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    # Using the verified GUI's existing guarded launcher writer ensures unrelated
    # shortcuts and symlinks are never replaced by the first-time installer.
    launch = (
        "import sys; sys.path.insert(0,sys.argv[1]); "
        "from pathlib import Path; "
        "from hackersghost_ai.core.desktop_launcher import install_launchers; "
        "install_launchers(desktop_dir=None, replace_existing=False, "
        "project_dir=Path(sys.argv[1]), python_executable=Path(sys.argv[2]), "
        "target_version=sys.argv[3])"
    )
    try:
        _run(
            [str(python), "-I", "-c", launch, str(destination), str(python), info["version"]],
            timeout=30,
        )
    except InstallError:
        # Do not remove the release when the launcher may have been created.
        raise InstallError(
            "The signed GUI is installed, but its menu shortcut could not be created. "
            "The installation folder was kept for recovery."
        ) from None
    return destination


def _platform_check() -> None:
    if sys.platform != "linux" or sys.version_info < (3, 10):
        raise InstallError("Requires Linux with Python 3.10 or newer.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise InstallError("Run as your ordinary Linux user, not with sudo.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="First-time HackersGhost AI GUI installer (Linux)")
    parser.add_argument("--verify-only", action="store_true", help="Check signed release without installation")
    parser.add_argument("--manifest", type=Path, help="Optional local signed latest.json")
    parser.add_argument("--archive", type=Path, help="Optional local versioned ZIP")
    parser.add_argument("--runtime-step", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    _platform_check()
    if (args.manifest is None) != (args.archive is None):
        raise InstallError("Provide both --manifest and --archive for offline verification.")

    if args.verify_only or args.runtime_step:
        info, package = load_release(manifest_path=args.manifest, archive_path=args.archive)
        print(f"Signed HackersGhost AI GUI {info['version']} verified.")
        if args.verify_only:
            return 0
        path = install_verified(package, info, python=Path(sys.executable), base=_root())
        print(f"Installed: {path}")
        print("Open HackersGhost AI from your Linux application menu.")
        print("Later updates are available through the GUI's Install button.")
        return 0

    if _existing_launcher():
        raise InstallError("HackersGhost AI GUI is already installed. Use its update button.")
    print("HackersGhost AI GUI first-time installer")
    print("Installs a private Python environment and official signed GUI release.")
    print("Downloads Python dependencies from PyPI; does not use sudo or alter the CLI.")
    if input("Type INSTALL to continue: ").strip() != "INSTALL":
        print("Cancelled. Nothing was installed.")
        return 0
    base = _root()
    python = prepare_runtime(base)
    options = [str(python), "-I", str(Path(__file__).resolve()), "--runtime-step"]
    if args.manifest:
        options += ["--manifest", str(args.manifest.resolve()), "--archive", str(args.archive.resolve())]
    _run(options, timeout=120)
    print("Installation complete. Open HackersGhost AI from your Linux application menu.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (InstallError, OSError, ValueError, EOFError, KeyboardInterrupt) as exc:
        print(f"Installation stopped: {exc}", file=sys.stderr)
        sys.exit(1)
