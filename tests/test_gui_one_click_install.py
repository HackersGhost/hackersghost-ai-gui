"""One-click GUI updater: per-user staging, launcher switch and recovery."""
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from hackersghost_ai.core.update_service import Release, UpdateError
from hackersghost_ai.core.update_installer import install_archive, restore_previous


class GuiInstallerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.project = self.home / "Original-GUI"
        (self.project / "hackersghost_ai/gui").mkdir(parents=True)
        (self.project / "hackersghost_ai/gui/app.py").write_text("original")
        self.python = self.project / ".venv/bin/python"
        self.python.parent.mkdir(parents=True)
        self.python.write_text("test executable")
        self.python.chmod(0o700)
        self.root = self.home / "managed"
        self.desktop = self.home / "Desktop"
        self.cli = self.home / ".local/bin/hackersghost-ai"
        self.cli.parent.mkdir(parents=True)
        self.cli.write_text("existing working CLI")
        self.patchers = [
            patch("pathlib.Path.home", return_value=self.home),
            patch("sys.platform", "linux"),
            patch("os.geteuid", return_value=1000, create=True),
            patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / "xdg")}),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def package(self, version="2.1.0"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in (
                "hackersghost_ai/gui/app.py",
                "hackersghost_ai/gui/main_window.py",
                "hackersghost_ai/__init__.py",
                "hackersghost_ai/__main__.py",
                "scripts/run_gui.sh", "requirements.txt", "pyproject.toml",
            ):
                archive.writestr(f"HackersGhost-AI-{version}/{name}", "test fixture")
        return buffer.getvalue()

    def args(self):
        return dict(
            root=self.root, active_project=self.project,
            python_executable=self.python, desktop_dir=self.desktop,
        )

    def release(self, package, version="2.1.0"):
        return Release(version, hashlib.sha256(package).hexdigest(), 9999999999, b"")

    def test_installs_new_release_without_replacing_running_app_or_cli(self):
        package = self.package()
        with patch("hackersghost_ai.core.update_installer._preflight") as preflight:
            result = install_archive(package, self.release(package), **self.args())
        preflight.assert_called_once()
        self.assertTrue((result.folder / "hackersghost_ai/gui/app.py").is_file())
        self.assertEqual((self.project / "hackersghost_ai/gui/app.py").read_text(), "original")
        self.assertEqual(self.cli.read_text(), "existing working CLI")
        self.assertIsNone(result.launcher_issue)
        self.assertEqual(result.desktop_path, self.desktop / "hackersghost-ai-gui.desktop")
        self.assertIn(str(result.folder), result.menu_path.read_text())
        self.assertEqual((self.root / "previous-gui.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(UpdateError, "already has"):
            install_archive(package, self.release(package), **self.args())

    def test_restore_previous_launcher_without_deleting_new_release(self):
        package = self.package()
        with patch("hackersghost_ai.core.update_installer._preflight"):
            result = install_archive(package, self.release(package), **self.args())
        restored = restore_previous(root=self.root, desktop_dir=self.desktop)
        self.assertIn(str(self.project), restored.menu_path.read_text())
        self.assertTrue(result.folder.exists())
        self.assertEqual(self.cli.read_text(), "existing working CLI")

    def test_hash_mismatch_never_changes_shortcut_or_release_folder(self):
        package = self.package()
        bogus = Release("2.1.0", "0" * 64, 9999999999, b"")
        with self.assertRaisesRegex(UpdateError, "checksum"):
            install_archive(package, bogus, **self.args())
        self.assertFalse(self.root.exists())
        self.assertFalse(self.desktop.exists())

    def test_preflight_failure_leaves_no_installed_release(self):
        package = self.package()
        with patch("hackersghost_ai.core.update_installer._preflight",
                   side_effect=UpdateError("startup failed")), self.assertRaisesRegex(UpdateError, "startup"):
            install_archive(package, self.release(package), **self.args())
        self.assertFalse((self.root / "releases/HackersGhost-AI-2.1.0").exists())
        self.assertEqual(list((self.root / "releases").iterdir()), [])
        self.assertEqual(self.cli.read_text(), "existing working CLI")

    def test_does_not_overwrite_unrelated_desktop_shortcuts(self):
        package = self.package()
        self.desktop.mkdir()
        shortcut = self.desktop / "hackersghost-ai-gui.desktop"
        shortcut.write_text("[Desktop Entry]\nType=Application\nExec=unrelated-app\n")
        with patch("hackersghost_ai.core.update_installer._preflight"):
            result = install_archive(package, self.release(package), **self.args())
        self.assertIsNotNone(result.launcher_issue)
        self.assertEqual(shortcut.read_text(), "[Desktop Entry]\nType=Application\nExec=unrelated-app\n")
        self.assertTrue(result.folder.is_dir())

    def test_rejects_symlink_update_directory(self):
        target = self.home / "other"
        target.mkdir()
        self.root.symlink_to(target, target_is_directory=True)
        package = self.package()
        with self.assertRaisesRegex(UpdateError, "symbolic link"):
            install_archive(package, self.release(package), **self.args())
        self.assertFalse(list(target.iterdir()))

    def test_missing_rollback_record_is_safe(self):
        with self.assertRaisesRegex(UpdateError, "No safe previous"):
            restore_previous(root=self.root, desktop_dir=self.desktop)


if __name__ == "__main__":
    unittest.main()
