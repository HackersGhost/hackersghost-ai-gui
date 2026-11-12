"""Explicit, per-user GUI installer for publisher-verified release archives.

The running app and CLI are never modified. New GUI files are staged and
preflight-checked before a managed Linux desktop launcher points to them.
"""
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from hackersghost_ai.core.desktop_launcher import LauncherError, LauncherResult, install_launchers
from hackersghost_ai.core.update_service import Release, UpdateError, validate_package


@dataclass(frozen=True)
class InstallResult:
    version: str
    folder: Path
    menu_path: Path | None
    desktop_path: Path | None
    launcher_issue: str | None = None


def _data_root() -> Path:
    home = Path.home()
    base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    if not base.is_absolute():
        base = home / ".local/share"
    return base / "hackersghost-ai-gui"


def _check_root(root: Path) -> Path:
    if not root.is_absolute():
        raise UpdateError("The GUI update folder must be an absolute path.")
    releases = root / "releases"
    if root.is_symlink() or releases.is_symlink():
        raise UpdateError("A GUI update directory is a symbolic link. Installation stopped.")
    try:
        releases.mkdir(parents=True, exist_ok=True, mode=0o700)
        if hasattr(os, "getuid") and (root.stat().st_uid != os.getuid() or releases.stat().st_uid != os.getuid()):
            raise UpdateError("GUI update folders must belong to your Linux user.")
        root.chmod(0o700)
        releases.chmod(0o700)
    except OSError:
        raise UpdateError("Cannot create a private GUI update directory.") from None
    return releases


def _unpack(package: bytes, target: Path, release: Release) -> None:
    # validate_package rejects traversal, symlinks, devices, duplicate casefolded
    # paths, oversized content and missing application entry points.
    validate_package(package, release)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        prefix = f"HackersGhost-AI-{release.version}/"
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            relative = entry.filename.removeprefix(prefix)
            output = target.joinpath(*relative.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as handle:
                handle.write(archive.read(entry))
            output.chmod(0o600)


def _preflight(folder: Path, python: Path, version: str) -> None:
    if not python.is_file() or not os.access(python, os.X_OK):
        raise UpdateError("The GUI Python environment is unavailable. The old version was kept.")
    script = (
        "import sys; sys.path.insert(0,sys.argv[1]); "
        "from hackersghost_ai import __version__; "
        "from hackersghost_ai.gui.app import build_window; "
        "assert __version__ == sys.argv[2]"
    )
    environment = {
        key: value for key, value in os.environ.items()
        if key not in ("OPENAI_API_KEY", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")
        and not key.startswith("HACKERSGHOST_") and not key.endswith("_API_KEY")
    }
    try:
        result = subprocess.run(
            [str(python), "-I", "-c", script, str(folder), version],
            env=environment, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise UpdateError("The new GUI did not pass its startup check. The old version was kept.") from None
    if result.returncode != 0:
        # Never surface subprocess output: it may contain local diagnostics.
        raise UpdateError(
            "The new GUI is incompatible with this Python environment or failed its startup check. "
            "The old version was kept."
        )


def _write_previous(root: Path, project: Path, python: Path) -> None:
    state = root / "previous-gui.json"
    if state.is_symlink():
        raise UpdateError("The previous-version record is not safe to replace.")
    body = json.dumps({"project": str(project.resolve(strict=True)), "python": str(python.resolve(strict=True))})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".hg-state-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, state)
    except OSError:
        raise UpdateError("Could not save the GUI rollback information; installation stopped.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_archive(
    package: bytes, release: Release, *, desktop_dir: Path | None = None,
    root: Path | None = None, python_executable: Path | None = None,
    active_project: Path | None = None,
) -> InstallResult:
    """Stage and install an already signed-and-hashed GUI release, with explicit consent."""
    if sys.platform != "linux":
        raise UpdateError("One-click GUI installation is supported on Linux only.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise UpdateError("Run HackersGhost AI as your Linux user, not with sudo.")
    # Verify again before writing anything: this is still only publisher-trusted code.
    validate_package(package, release)
    python = Path(python_executable or sys.executable).absolute()
    original = Path(active_project or Path(__file__).resolve().parents[2]).resolve()
    if not (original / "hackersghost_ai/gui/app.py").is_file():
        raise UpdateError("The currently running GUI installation cannot be located.")
    base = root or _data_root()
    releases = _check_root(base)
    destination = releases / f"HackersGhost-AI-{release.version}"
    if destination.exists() or destination.is_symlink():
        raise UpdateError("This GUI version already has a managed installation. It was not overwritten.")

    stage = Path(tempfile.mkdtemp(prefix=".hg-stage-", dir=releases))
    try:
        _unpack(package, stage, release)
        _preflight(stage, python, release.version)
        os.rename(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    # The previous app folder is never deleted. Record how to recover its launcher.
    try:
        _write_previous(base, original, python)
    except UpdateError:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    try:
        launcher: LauncherResult = install_launchers(
            desktop_dir=desktop_dir, replace_existing=True,
            project_dir=destination, python_executable=python,
        )
    except (LauncherError, OSError):
        # The staged release is kept because a desktop shortcut may have been
        # updated before a second shortcut failed. Never delete its target.
        return InstallResult(
            release.version, destination, None, None,
            "The GUI release was installed, but one or more shortcuts could not be updated. "
            "The older application folder is still available.",
        )
    return InstallResult(release.version, destination, launcher.menu_path, launcher.desktop_path)


def restore_previous(*, desktop_dir: Path | None = None, root: Path | None = None) -> LauncherResult:
    """Retarget managed desktop shortcuts to the last application folder."""
    base = root or _data_root()
    state = base / "previous-gui.json"
    if state.is_symlink() or not state.is_file() or state.stat().st_size > 4096:
        raise UpdateError("No safe previous GUI installation record was found.")
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        project = Path(data["project"])
        python = Path(data["python"])
        if not project.is_absolute() or not python.is_absolute():
            raise ValueError()
        if not (project / "hackersghost_ai/gui/app.py").is_file():
            raise ValueError()
        return install_launchers(
            desktop_dir=desktop_dir, replace_existing=True,
            project_dir=project, python_executable=python,
        )
    except (ValueError, KeyError, TypeError, OSError, LauncherError):
        raise UpdateError("The previous GUI cannot be restored. No application files were deleted.") from None
