"""Per-user Linux desktop entries; no shell commands, downloads or CLI changes."""

import configparser
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import tempfile

from hackersghost_ai import __version__


DESKTOP_ID = "hackersghost-ai-gui"
FILENAME = DESKTOP_ID + ".desktop"
MANAGED_KEY = "X-HackersGhost-GUI-Launcher"
ENTRY_LIMIT = 64 * 1024


class LauncherError(Exception):
    """An installation failure safe to display in the interface."""


class LauncherReplacementRequired(LauncherError):
    """Existing managed shortcuts require explicit replacement approval."""


@dataclass(frozen=True)
class LauncherResult:
    menu_path: Path
    desktop_path: Path | None


def _check_path_text(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise LauncherError("Launcher paths cannot contain control characters.")
    return value


def _string_value(value: str) -> str:
    return _check_path_text(value).replace("\\", "\\\\")


def _exec_argument(value: str) -> str:
    _check_path_text(value)
    quoted = "".join("\\" + char if char in '\\"`$' else "%%" if char == "%" else char for char in value)
    return _string_value('"' + quoted + '"')


def desktop_entry(project_dir: Path, python_executable: Path) -> str:
    if not project_dir.is_absolute() or not python_executable.is_absolute():
        raise LauncherError("The application and Python paths must be absolute.")
    if "=" in str(python_executable):
        raise LauncherError("The Python path contains '='. Move the app to a folder without that character.")
    script = project_dir / "scripts" / "launch_gui.py"
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Name=HackersGhost AI",
        "Comment=AI desktop assistant", "Icon=applications-development",
        "Exec=" + _exec_argument(str(python_executable)) + " -I " + _exec_argument(str(script)),
        "TryExec=" + _string_value(str(python_executable)),
        "Path=" + _string_value(str(project_dir)),
        "Terminal=false", "Categories=Utility;", "StartupNotify=false",
        MANAGED_KEY + "=1", "X-HackersGhost-GUI-Version=" + __version__, "",
    ])


def _existing_entry(path: Path) -> str | None:
    if path.is_symlink():
        raise LauncherError(f"Refusing to replace a symbolic link: {path.name}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > ENTRY_LIMIT:
        raise LauncherError(f"An unrelated file or folder already uses {path.name}.")
    try:
        with path.open("rb") as handle:
            raw = handle.read(ENTRY_LIMIT + 1)
        if len(raw) > ENTRY_LIMIT:
            raise ValueError("oversized entry")
        text = raw.decode("utf-8")
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read_string(text)
        if parser["Desktop Entry"].get(MANAGED_KEY) != "1":
            raise ValueError("not managed")
        return text
    except (configparser.Error, KeyError, ValueError):
        raise LauncherError(f"An unrelated shortcut already uses {path.name}; it was not changed.") from None


def install_launchers(*, desktop_dir: Path | None, replace_existing: bool = False,
                     project_dir: Path | None = None, python_executable: Path | None = None) -> LauncherResult:
    if sys.platform != "linux":
        raise LauncherError("Desktop launcher installation is available on Linux only.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise LauncherError("Run the GUI as your regular user, not with sudo.")
    project = (project_dir or Path(__file__).resolve().parents[2]).resolve()
    python = Path(os.path.abspath(python_executable or sys.executable))
    if not python.is_file() or not os.access(python, os.X_OK):
        raise LauncherError("The current Python environment could not be found.")
    if not (project / "scripts/launch_gui.py").is_file() or not (project / "hackersghost_ai/gui/app.py").is_file():
        raise LauncherError("The GUI source folder is incomplete. Extract the full GUI download first.")
    home = Path.home()
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    if not data_home.is_absolute():
        data_home = home / ".local/share"
    menu_path = data_home / "applications" / FILENAME
    desktop_path = None
    if desktop_dir is not None:
        if not desktop_dir.is_absolute():
            raise LauncherError("The configured desktop folder is not an absolute path.")
        if desktop_dir.resolve() != home.resolve():
            desktop_path = desktop_dir / FILENAME
    result = LauncherResult(menu_path, desktop_path)
    targets = list(dict.fromkeys(p for p in (menu_path, desktop_path) if p is not None))
    content = desktop_entry(project, python)
    written = []
    try:
        previous = {path: _existing_entry(path) for path in targets}
        if not replace_existing and any(old is not None and old != content for old in previous.values()):
            raise LauncherReplacementRequired("HackersGhost AI GUI shortcuts already point to another setup.")
        for path in targets:
            if previous[path] == content:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".hg-launcher-", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(content.encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.chmod(0o700)
                if _existing_entry(path) != previous[path]:
                    raise LauncherError("A shortcut changed during installation. Try again.")
                if previous[path] is None:
                    os.link(temporary, path)
                else:
                    os.replace(temporary, path)
                written.append(path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return result
    except OSError:
        suffix = " Some shortcuts were installed; retry to finish." if written else " No shortcuts were changed."
        raise LauncherError("Could not write the shortcuts. Check folder permissions and free disk space." + suffix) from None
