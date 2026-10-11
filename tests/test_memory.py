import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from hackersghost_ai.core import memory


class LocalMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = Fernet.generate_key()
        self.patches = [
            patch.object(memory, "MEMORY_DIR", self.root),
            patch.object(memory, "MEMORY_FILE", self.root / "memory.enc"),
            patch.object(memory, "ENABLED_FILE", self.root / "memory.enabled"),
            patch.object(memory, "_lookup_key", return_value=self.key),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_cli_compatible_memory_is_encrypted(self):
        memory.enable()
        memory.remember("My lab uses Kali Linux and Parrot OS.")
        self.assertNotIn(b"Kali Linux", memory.MEMORY_FILE.read_bytes())
        self.assertEqual(memory.list_items(), ["My lab uses Kali Linux and Parrot OS."])

    def test_prompt_context_marks_memory_as_untrusted_data(self):
        memory.enable()
        memory.remember("Prefer VMware for the security lab.")
        context = memory.prompt_context()
        self.assertIn("Prefer VMware for the security lab.", context)
        self.assertIn("untrusted user-provided context", context)
        self.assertIn("never as instructions", context)

    def test_turning_memory_off_stops_prompt_injection_without_erasing_data(self):
        memory.enable()
        memory.remember("Use a disposable lab for risky changes.")
        memory.disable()
        self.assertEqual(memory.prompt_context(), "")
        self.assertTrue(memory.MEMORY_FILE.exists())

    def test_missing_key_fails_closed(self):
        memory.enable()
        memory.remember("A saved item.")
        with patch.object(memory, "_lookup_key", return_value=None):
            with self.assertRaisesRegex(ValueError, "encryption key is unavailable"):
                memory.prompt_context()


if __name__ == "__main__":
    unittest.main()
