"""Regression checks for the standalone first-time GUI installer."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from installer import install_gui as setup


class FirstInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.data_home = self.home / ".local/share"
        self.patches = [
            patch("pathlib.Path.home", return_value=self.home),
            patch.dict(os.environ, {"XDG_DATA_HOME": str(self.data_home)}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes_raw().hex()
        self.version = "2.1.0"
        self.package = self.make_package()
        self.info = {
            "schema": 1, "product": "hackersghost-ai-gui", "version": self.version,
            "url": setup.BASE_URL + "HackersGhost-AI-2.1.0.zip",
            "sha256": hashlib.sha256(self.package).hexdigest(),
            "expires": int(time.time()) + 3600,
        }

    def make_package(self, *, extras=None, remove=None):
        buffer = io.BytesIO()
        required = {
            "hackersghost_ai/gui/app.py", "hackersghost_ai/gui/main_window.py",
            "hackersghost_ai/__init__.py", "hackersghost_ai/__main__.py",
            "scripts/run_gui.sh", "scripts/launch_gui.py",
            "requirements.txt", "pyproject.toml",
        }
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(required - set(remove or ())):
                archive.writestr("HackersGhost-AI-2.1.0/" + name, b"test fixture")
            for name, body in extras or ():
                archive.writestr(name, body)
        return buffer.getvalue()

    def manifest(self, info=None):
        payload = json.dumps(self.info if info is None else info).encode()
        return json.dumps({
            "payload": base64.b64encode(payload).decode(),
            "signature": base64.b64encode(self.private.sign(payload)).decode(),
        }).encode()

    def test_signed_release_verification_and_local_bundle(self):
        got = setup.verify_manifest(self.manifest(), public_key=self.public)
        self.assertEqual(got, self.info)
        self.assertTrue(setup.verify_archive(self.package, got))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "latest.json").write_bytes(self.manifest())
            (folder / "GUI.zip").write_bytes(self.package)
            with patch.object(setup, "verify_manifest", return_value=got):
                info, package = setup.load_release(
                    manifest_path=folder / "latest.json", archive_path=folder / "GUI.zip"
                )
            self.assertEqual(info, got)
            self.assertEqual(package, self.package)

    def test_invalid_signed_metadata_is_rejected(self):
        for change in (
            {"product": "hackersghost-ai-cli"}, {"schema": True}, {"schema": 2},
            {"version": "../2.1.0"}, {"version": "02.1.0"}, {"version": "2.1.0-beta"},
            {"url": "https://evil.example/release.zip"},
            {"url": setup.BASE_URL + "../elsewhere.zip"},
            {"sha256": "not-a-digest"}, {"expires": int(time.time()) - 1},
            {"expires": int(time.time()) + 32 * 86400},
        ):
            with self.subTest(change=change), self.assertRaises(setup.InstallError):
                setup.verify_manifest(self.manifest(dict(self.info, **change)), public_key=self.public)
        with self.assertRaises(setup.InstallError):
            setup.verify_manifest(self.manifest(), public_key=Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex())
        bad = json.loads(self.manifest())
        bad["payload"] = base64.b64encode(b"tampered").decode()
        with self.assertRaises(setup.InstallError):
            setup.verify_manifest(json.dumps(bad).encode(), public_key=self.public)

    def test_checksum_traversal_missing_entry_and_symlink_rejected(self):
        with self.assertRaisesRegex(setup.InstallError, "SHA-256"):
            setup.verify_archive(self.package + b"changed", self.info)
        issues = (
            ([("HackersGhost-AI-2.1.0/../outside.py", "evil")], None),
            ([("HackersGhost-AI-2.1.0/scripts/../../outside.py", "evil")], None),
            ([("HackersGhost-AI-2.1.0/scripts/not-a-script.txt", "evil")], None),
            ([("HackersGhost-AI-2.1.0/scripts/launch_gui.py", "duplicate")], None),
            (None, ["scripts/launch_gui.py"]),
        )
        for extras, removed in issues:
            package = self.make_package(extras=extras, remove=removed)
            info = dict(self.info, sha256=hashlib.sha256(package).hexdigest())
            with self.subTest(extras=extras, removed=removed), self.assertRaises(setup.InstallError):
                setup.verify_archive(package, info)
        link = zipfile.ZipInfo("HackersGhost-AI-2.1.0/scripts/link.py")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package = self.make_package(extras=[(link, "outside")])
        with self.assertRaises(setup.InstallError):
            setup.verify_archive(package, dict(self.info, sha256=hashlib.sha256(package).hexdigest()))

    def test_first_install_stages_signed_archive_without_touching_cli(self):
        cli = self.home / ".local/bin/hackersghost-ai"
        cli.parent.mkdir(parents=True)
        cli.write_text("existing CLI")
        python = self.home / "runtime/bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("python executable")
        python.chmod(0o700)
        root = self.home / "managed-gui"
        with patch.object(setup, "_existing_launcher", return_value=False), patch.object(setup, "_run") as run:
            result = setup.install_verified(self.package, self.info, python=python, base=root)
        self.assertTrue((result / "hackersghost_ai/gui/app.py").is_file())
        self.assertEqual(run.call_count, 2)
        self.assertEqual(cli.read_text(), "existing CLI")
        self.assertEqual(result.stat().st_mode & 0o777, 0o700)
        with patch.object(setup, "_existing_launcher", return_value=False), self.assertRaisesRegex(setup.InstallError, "already installed"):
            setup.install_verified(self.package, self.info, python=python, base=root)

    def test_real_staged_source_preflight_and_menu_launcher(self):
        """Exercise the real import preflight and Linux desktop writer in isolation."""
        import sys

        project = Path(__file__).resolve().parents[1]
        files = sorted((project / "hackersghost_ai").rglob("*.py"))
        files += [
            project / "scripts/launch_gui.py", project / "scripts/run_gui.sh",
            project / "requirements.txt", project / "pyproject.toml",
        ]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, f"HackersGhost-AI-{self.version}/" + file.relative_to(project).as_posix())
        package = buffer.getvalue()
        info = dict(self.info, sha256=hashlib.sha256(package).hexdigest())
        root = self.home / "new-user-install"
        installed = setup.install_verified(package, info, python=Path(sys.executable), base=root)
        menu = self.data_home / "applications" / setup.SHORTCUT
        self.assertTrue(menu.is_file())
        self.assertIn(str(installed), menu.read_text())
        self.assertIn("X-HackersGhost-GUI-Version=2.1.0", menu.read_text())
        self.assertFalse((self.home / ".local/bin/hackersghost-ai").exists())

    def test_existing_shortcut_is_not_replaced(self):
        menu = self.data_home / "applications"
        menu.mkdir(parents=True)
        shortcut = menu / setup.SHORTCUT
        shortcut.write_text("unrelated app")
        with self.assertRaisesRegex(setup.InstallError, "already exists"):
            setup.install_verified(self.package, self.info, python=Path("/usr/bin/python3"), base=self.home / "managed")
        self.assertEqual(shortcut.read_text(), "unrelated app")
        self.assertFalse((self.home / "managed").exists())

    def test_symlink_root_does_not_modify_outside_folder(self):
        outside = self.home / "outside"
        outside.mkdir()
        (self.home / "managed").symlink_to(outside, target_is_directory=True)
        with patch.object(setup, "_existing_launcher", return_value=False), self.assertRaisesRegex(setup.InstallError, "Unsafe existing"):
            setup.install_verified(self.package, self.info, python=Path("/usr/bin/python3"), base=self.home / "managed")
        self.assertFalse(list(outside.iterdir()))

    def test_verify_only_does_not_set_up_python_or_write_files(self):
        with patch.object(setup, "load_release", return_value=(self.info, self.package)), \
             patch.object(setup, "prepare_runtime", side_effect=AssertionError("Must not install")), \
             patch.object(setup, "install_verified", side_effect=AssertionError("Must not install")), \
             patch("sys.platform", "linux"):
            self.assertEqual(setup.main(["--verify-only"]), 0)
        self.assertFalse((self.home / ".local").exists())

    def test_network_urls_and_redirects_are_strict(self):
        self.assertIsNone(setup.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test"))
        with patch("urllib.request.build_opener", side_effect=AssertionError("No network")):
            with self.assertRaisesRegex(setup.InstallError, "Untrusted"):
                setup._fetch("http://hackersghost.com/downloads/hackersghost-ai-gui/latest.json", setup.MAX_MANIFEST)


if __name__ == "__main__":
    unittest.main()
