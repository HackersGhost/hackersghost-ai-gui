import importlib.util
import os
from pathlib import Path, PurePosixPath
import shlex
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from hackersghost_ai.core.desktop_launcher import (
    FILENAME, LauncherError, LauncherReplacementRequired, desktop_entry, install_launchers,
)


class DesktopLauncherTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        self.project = self.home / "Projects" / "GUI with spaces"
        (self.project / "scripts").mkdir(parents=True)
        (self.project / "scripts/launch_gui.py").write_text("# test", encoding="utf-8")
        (self.project / "hackersghost_ai/gui").mkdir(parents=True)
        (self.project / "hackersghost_ai/gui/app.py").write_text("# test", encoding="utf-8")
        self.python = self.project / ".venv/bin/python"
        self.python.parent.mkdir(parents=True)
        self.python.write_text("test interpreter; never executed", encoding="utf-8")
        self.python.chmod(0o700)
        self.desktop = self.home / "Bureaublad"
        self.arguments = {"desktop_dir": self.desktop, "project_dir": self.project, "python_executable": self.python}
        for context in (patch("sys.platform", "linux"), patch("os.geteuid", return_value=1000, create=True),
                        patch("pathlib.Path.home", return_value=self.home), patch.dict("os.environ", {}, clear=True)):
            context.start()
            self.addCleanup(context.stop)

    def test_installs_menu_and_localized_desktop_without_touching_cli(self):
        cli = self.home / ".local/bin/hackersghost-ai"
        cli.parent.mkdir(parents=True)
        cli.write_text("existing CLI", encoding="utf-8")
        with patch("subprocess.run", side_effect=AssertionError("No subprocess expected")):
            result = install_launchers(**self.arguments)
        self.assertEqual(result.menu_path, self.home / ".local/share/applications" / FILENAME)
        self.assertEqual(result.desktop_path, self.desktop / FILENAME)
        text = result.menu_path.read_text(encoding="utf-8")
        self.assertEqual(text, result.desktop_path.read_text(encoding="utf-8"))
        self.assertIn("Terminal=false", text)
        self.assertIn(' -I "', text)
        self.assertNotIn("pip install", text)
        self.assertNotIn("OPENAI_API_KEY", text)
        self.assertEqual(cli.read_text(encoding="utf-8"), "existing CLI")
        self.assertFalse(list(self.home.rglob(".hg-launcher-*")))
        if os.name != "nt":
            self.assertEqual(result.desktop_path.stat().st_mode & 0o777, 0o700)

    def test_exec_quotes_spaces_and_special_characters_without_shell(self):
        project = PurePosixPath('/home/test/GUI $cash `tick` "quote" \\percent%f')
        python = project / ".venv/bin/python"
        entry = desktop_entry(project, python)
        command = next(line[5:] for line in entry.splitlines() if line.startswith("Exec="))
        string_decoded = command.replace("\\\\", "\\")
        arguments = [value.replace("\\$", "$").replace("\\`", "`").replace("%%", "%")
                     for value in shlex.split(string_decoded)]
        self.assertEqual(arguments, [str(python), "-I", str(project / "scripts/launch_gui.py")])
        self.assertIn("%%f", command)
        self.assertNotIn("sh -c", entry)

    def test_missing_installation_and_control_characters_are_rejected(self):
        with self.assertRaises(LauncherError):
            install_launchers(**dict(self.arguments, python_executable=self.home / "missing"))
        (self.project / "scripts/launch_gui.py").unlink()
        with self.assertRaises(LauncherError):
            install_launchers(**self.arguments)
        for root, python in ((PurePosixPath("relative"), PurePosixPath("/python")),
                             (PurePosixPath("/home/test\ninjection"), PurePosixPath("/python")),
                             (PurePosixPath("/project"), PurePosixPath("/path=invalid/python"))):
            with self.assertRaises(LauncherError):
                desktop_entry(root, python)

    def test_xdg_data_directory_and_disabled_desktop(self):
        data = self.home / "custom data"
        with patch.dict("os.environ", {"XDG_DATA_HOME": str(data)}):
            result = install_launchers(**dict(self.arguments, desktop_dir=self.home))
        self.assertEqual(result.menu_path, data / "applications" / FILENAME)
        self.assertIsNone(result.desktop_path)
        self.assertFalse((self.home / FILENAME).exists())
        with patch.dict("os.environ", {"XDG_DATA_HOME": "relative-data"}):
            result = install_launchers(**dict(self.arguments, desktop_dir=None))
        self.assertEqual(result.menu_path, self.home / ".local/share/applications" / FILENAME)

    def test_repeated_installation_is_idempotent(self):
        result = install_launchers(**self.arguments)
        original = result.menu_path.read_bytes()
        with patch("os.link", side_effect=AssertionError("Unnecessary write")), \
             patch("os.replace", side_effect=AssertionError("Unnecessary replacement")):
            self.assertEqual(install_launchers(**self.arguments), result)
        self.assertEqual(result.menu_path.read_bytes(), original)

    def test_existing_shortcuts_need_approval_before_retargeting(self):
        first = install_launchers(**self.arguments)
        original = first.menu_path.read_bytes()
        next_python = self.project / ".venv/bin/other-python"
        next_python.write_bytes(b"new test interpreter")
        next_python.chmod(0o700)
        arguments = dict(self.arguments, python_executable=next_python)
        with self.assertRaises(LauncherReplacementRequired):
            install_launchers(**arguments)
        self.assertEqual(first.menu_path.read_bytes(), original)
        updated = install_launchers(**arguments, replace_existing=True)
        self.assertNotEqual(updated.menu_path.read_bytes(), original)
        self.assertEqual(updated.menu_path.read_bytes(), updated.desktop_path.read_bytes())

    def test_unrelated_shortcuts_are_preserved_even_with_replace_enabled(self):
        self.desktop.mkdir()
        target = self.desktop / FILENAME
        original = "[Desktop Entry]\nType=Application\nExec=another-program\n"
        target.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(LauncherError, "unrelated"):
            install_launchers(**self.arguments, replace_existing=True)
        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertFalse((self.home / ".local/share/applications" / FILENAME).exists())

    def test_symlink_shortcuts_are_not_followed_or_replaced(self):
        self.desktop.mkdir()
        other = self.home / "unrelated-file"
        other.write_text("do not change", encoding="utf-8")
        link = self.desktop / FILENAME
        try:
            link.symlink_to(other)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this test host")
        with self.assertRaisesRegex(LauncherError, "symbolic link"):
            install_launchers(**self.arguments, replace_existing=True)
        self.assertEqual(other.read_text(encoding="utf-8"), "do not change")

    def test_root_and_other_platforms_cannot_install(self):
        with patch("sys.platform", "win32"), self.assertRaisesRegex(LauncherError, "Linux only"):
            install_launchers(**self.arguments)
        with patch("os.geteuid", return_value=0), self.assertRaisesRegex(LauncherError, "regular user"):
            install_launchers(**self.arguments)
        self.assertFalse((self.home / ".local").exists())

    def test_symlink_guard_runs_before_any_writes(self):
        with patch("pathlib.Path.is_symlink", return_value=True), \
             patch("os.link", side_effect=AssertionError("Must not write")), \
             self.assertRaisesRegex(LauncherError, "symbolic link"):
            install_launchers(**self.arguments, replace_existing=True)

    def test_new_file_appearing_during_installation_is_not_overwritten(self):
        original_link = os.link

        def raced_link(source, target):
            Path(target).write_bytes(b"unrelated concurrent file")
            return original_link(source, target)

        with patch("os.link", side_effect=raced_link), self.assertRaises(LauncherError):
            install_launchers(**self.arguments)
        menu = self.home / ".local/share/applications" / FILENAME
        self.assertEqual(menu.read_bytes(), b"unrelated concurrent file")
        self.assertFalse((self.desktop / FILENAME).exists())
        self.assertFalse(list(self.home.rglob(".hg-launcher-*")))

    def test_write_failure_is_reported_and_partial_install_can_be_retried(self):
        original_link = os.link

        def fail_desktop(source, target):
            if Path(target).parent == self.desktop:
                raise PermissionError("private diagnostic")
            return original_link(source, target)

        with patch("os.link", side_effect=fail_desktop), self.assertRaises(LauncherError) as failure:
            install_launchers(**self.arguments)
        self.assertIn("Some shortcuts were installed", str(failure.exception))
        self.assertNotIn("private diagnostic", str(failure.exception))
        self.assertFalse(list(self.home.rglob(".hg-launcher-*")))
        result = install_launchers(**self.arguments)
        self.assertTrue(result.menu_path.is_file())
        self.assertTrue(result.desktop_path.is_file())

    def test_entrypoint_starts_from_any_directory_without_network_or_installer(self):
        source = Path(__file__).resolve().parents[1] / "scripts/launch_gui.py"
        spec = importlib.util.spec_from_file_location("hg_test_entry", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        previous_dir = Path.cwd()
        previous_sys_path = sys.path[:]
        gui = types.ModuleType("hackersghost_ai.gui.app")
        calls = []
        gui.main = lambda: calls.append(Path.cwd()) or 0
        try:
            os.chdir(self.home)
            with patch.dict("sys.modules", {"hackersghost_ai.gui.app": gui}), \
                 patch("subprocess.run", side_effect=AssertionError("No dependency installation")):
                self.assertEqual(module.main(), 0)
            self.assertEqual(calls, [source.parent.parent])
        finally:
            os.chdir(previous_dir)
            sys.path[:] = previous_sys_path


if __name__ == "__main__":
    unittest.main()
