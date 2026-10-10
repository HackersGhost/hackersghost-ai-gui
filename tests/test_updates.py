import base64
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch
import warnings
import zipfile

from scripts.sign_gui_release import signed_manifest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hackersghost_ai.core.update_service import (
    DOWNLOAD_BASE, FEED, MANIFEST_LIMIT, PACKAGE_LIMIT, PRODUCT, NoRedirect,
    UpdateError, UpdateService, validate_package, verify_manifest, version_tuple,
)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public_key = self.key.public_key().public_bytes_raw().hex()
        self.service = UpdateService("0.1.3", public_key=self.public_key)
        self.package = self.make_package()
        self.info = {
            "schema": 1, "product": PRODUCT, "version": "0.1.4",
            "url": DOWNLOAD_BASE + "HackersGhost-AI-0.1.4.zip",
            "sha256": hashlib.sha256(self.package).hexdigest(), "expires": int(time.time()) + 3600,
        }

    def make_package(self, extra=None):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("hackersghost_ai/gui/app.py", "hackersghost_ai/gui/main_window.py",
                         "hackersghost_ai/__init__.py", "hackersghost_ai/__main__.py",
                         "scripts/run_gui.sh", "requirements.txt", "pyproject.toml"):
                archive.writestr("HackersGhost-AI-0.1.4/" + name, "test fixture; never executed")
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(*extra)
        return buffer.getvalue()

    def envelope(self, info=None):
        payload = json.dumps(self.info if info is None else info).encode()
        return json.dumps({"payload": base64.b64encode(payload).decode(),
                           "signature": base64.b64encode(self.key.sign(payload)).decode()}).encode()

    def release(self, package=None):
        info = dict(self.info)
        if package is not None:
            info["sha256"] = hashlib.sha256(package).hexdigest()
        return verify_manifest(self.envelope(info), self.public_key)

    def test_check_and_verified_download_without_execution(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(self.service, "_fetch", side_effect=[self.envelope(), self.package]) as fetch, \
             patch("subprocess.run", side_effect=AssertionError("No execution allowed")):
            status = self.service.check()
            self.assertEqual(status.latest_version, "0.1.4")
            destination = Path(folder) / "chosen file.zip"
            self.assertEqual(self.service.download_release(status.release, destination), destination)
            self.assertEqual(destination.read_bytes(), self.package)
            self.assertEqual(list(Path(folder).iterdir()), [destination])
            self.assertEqual(fetch.call_args_list[0].args, (FEED, MANIFEST_LIMIT))
            self.assertEqual(fetch.call_args_list[1].args, (self.info["url"], PACKAGE_LIMIT))

    def test_equal_or_older_versions_are_not_updates(self):
        for version in ("0.1.3", "0.1.2"):
            info = dict(self.info, version=version, url=DOWNLOAD_BASE + f"HackersGhost-AI-{version}.zip")
            with patch.object(self.service, "_fetch", return_value=self.envelope(info)):
                self.assertIsNone(self.service.check().release)
                with self.assertRaises(UpdateError):
                    self.service.download_release(verify_manifest(self.envelope(info), self.public_key), "unused.zip")
        self.assertGreater(version_tuple("0.1.10"), version_tuple("0.1.9"))

    def test_wrong_signature_malformed_and_oversized_manifest(self):
        invalid = [b"not json", b"[]", b"null", b"{}", b"x" * (MANIFEST_LIMIT + 1)]
        envelope = json.loads(self.envelope())
        envelope["payload"] = base64.b64encode(b"changed").decode()
        invalid.append(json.dumps(envelope).encode())
        envelope["signature"] = "!"
        invalid.append(json.dumps(envelope).encode())
        for data in invalid:
            with self.subTest(data=data[:40]), self.assertRaises(UpdateError):
                verify_manifest(data, self.public_key)
        other_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
        with self.assertRaises(UpdateError):
            verify_manifest(self.envelope(), other_key)

    def test_product_date_digest_schema_and_url_restrictions(self):
        changes = [
            {"product": "hackersghost-ai-cli"}, {"schema": True}, {"schema": 2},
            {"expires": int(time.time()) - 1}, {"expires": int(time.time()) + 32 * 86400},
            {"expires": True}, {"sha256": "not a digest"}, {"version": "../0.1.4"},
            {"version": "00.1.4"}, {"version": 14}, {"version": "0.1.4-beta"},
        ]
        for url in ("http://hackersghost.com/", "https://evil.invalid/update.zip",
                    DOWNLOAD_BASE + "../hackersghost-ai/latest.json", self.info["url"] + "?redirect=1",
                    "https://user:password@hackersghost.com/", self.info["url"] + "#fragment"):
            changes.append({"url": url})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(UpdateError):
                verify_manifest(self.envelope(dict(self.info, **change)), self.public_key)

    def test_checksum_failure_and_save_failure_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "existing.zip"
            destination.write_bytes(b"original")
            with patch.object(self.service, "_fetch", return_value=b"tampered"), self.assertRaises(UpdateError):
                self.service.download_release(self.release(), destination)
            self.assertEqual(destination.read_bytes(), b"original")
            with patch.object(self.service, "_fetch", return_value=self.package), \
                 patch("os.replace", side_effect=PermissionError), self.assertRaises(UpdateError):
                self.service.download_release(self.release(), destination)
            self.assertEqual(destination.read_bytes(), b"original")
            self.assertEqual(list(Path(folder).iterdir()), [destination])

    def test_download_rechecks_signature_metadata_and_expiry(self):
        release = self.release()
        with patch.object(self.service, "_fetch") as fetch:
            with self.assertRaises(UpdateError):
                self.service.download_release(replace(release, version="0.1.5"), "unused.zip")
            with patch("time.time", return_value=release.expires + 1), self.assertRaises(UpdateError):
                self.service.download_release(release, "unused.zip")
            fetch.assert_not_called()
        with patch.object(self.service, "_fetch", return_value=self.package), \
             patch("time.time", side_effect=[self.info["expires"] - 1, self.info["expires"] + 1]), \
             self.assertRaises(UpdateError):
            self.service.download_release(release, "unused.zip")

    def test_archive_traversal_symlinks_duplicates_size_and_cli_are_rejected(self):
        for name in ("../escape.py", "/absolute.py", "HackersGhost-AI-0.1.4/../escape.py",
                     "HackersGhost-AI-0.1.4/scripts/../../escape.py", "HackersGhost-AI-0.1.4\\evil.py",
                     "HackersGhost-AI-0.1.4/scripts/run_gui.sh", "HackersGhost-AI-0.1.4/secret.key"):
            package = self.make_package((name, "test"))
            with self.subTest(name=name), self.assertRaises(UpdateError):
                validate_package(package, self.release(package))
        link = zipfile.ZipInfo("HackersGhost-AI-0.1.4/scripts/link.py")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for package in (b"not zip", self.make_package((link, "/outside")),
                        self.make_package(("HackersGhost-AI-0.1.4/scripts/huge.py", "x" * PACKAGE_LIMIT))):
            with self.assertRaises(UpdateError):
                validate_package(package, self.release(package))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("HackersGhost-AI-0.1.4/hackersghost_ai/cli.py", "test")
        with self.assertRaisesRegex(UpdateError, "complete GUI"):
            validate_package(buffer.getvalue(), self.release(buffer.getvalue()))

    def test_http_errors_limits_and_redirects_are_safe(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))
        for code in (302, 404, 500):
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError(FEED, code, "secret", {}, io.BytesIO(b"secret"))
            with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(UpdateError) as error:
                self.service.check()
            self.assertNotIn("secret", str(error.exception))
            if code == 404:
                self.assertIn("not published", str(error.exception))
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, FEED)
            self.assertNotIn("Authorization", request.headers)
        for data in (b"x" * (MANIFEST_LIMIT + 1),):
            opener = Mock()
            opener.open.return_value = io.BytesIO(data)
            with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(UpdateError):
                self.service.check()
        opener.open.side_effect = urllib.error.URLError("private diagnostic")
        with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(UpdateError) as error:
            self.service.check()
        self.assertNotIn("private diagnostic", str(error.exception))

    def test_publisher_helper_matches_key_and_validates_package(self):
        with patch("scripts.sign_gui_release.PUBLIC_KEY", self.public_key):
            result = signed_manifest(self.package, "0.1.4", self.key)
            self.assertEqual(verify_manifest(result, self.public_key).version, "0.1.4")
            for package, days in ((b"invalid package", 30), (self.package, 31), (self.package, 0)):
                with self.assertRaises((ValueError, UpdateError)):
                    signed_manifest(package, "0.1.4", self.key, days)
            with self.assertRaisesRegex(ValueError, "does not match"):
                signed_manifest(self.package, "0.1.4", Ed25519PrivateKey.generate())


if __name__ == "__main__":
    unittest.main()
