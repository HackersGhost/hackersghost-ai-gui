from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from hackersghost_ai.core.attachments import FILE_LIMIT, TextAttachment, read_attachment
from hackersghost_ai.core.chat_service import ChatService
from hackersghost_ai.core.credentials import Credential
from hackersghost_ai.core.errors import ChatError


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "example.log"

    def test_snapshot_does_not_reread_or_reveal_parent_path(self):
        self.path.write_bytes(b"fictional log\r\nsecond line")
        attachment = read_attachment(self.path)
        self.path.write_bytes(b"different content")
        self.assertEqual(attachment.name, "example.log")
        self.assertEqual(attachment.text, "fictional log\r\nsecond line")
        self.assertNotIn("fictional log", repr(attachment))

    def test_limits_binary_encoding_empty_and_missing(self):
        for data in (b"", b"binary\x00data", b"\xff", b"\x1b[31m", b"x" * (FILE_LIMIT + 1)):
            self.path.write_bytes(data)
            with self.subTest(data=data[:10]), self.assertRaises(ChatError):
                read_attachment(self.path)
        self.path.write_bytes(b"x" * FILE_LIMIT)
        self.assertEqual(read_attachment(self.path).size, FILE_LIMIT)
        with self.assertRaises(ChatError):
            read_attachment(self.path.parent)
        with self.assertRaises(ChatError):
            read_attachment(self.path.with_name("missing.log"))

    def test_non_regular_file_is_rejected_before_read(self):
        self.path.write_text("test", encoding="utf-8")
        with patch("hackersghost_ai.core.attachments.stat.S_ISREG", return_value=False):
            with self.assertRaisesRegex(ChatError, "regular"):
                read_attachment(self.path)

    def test_consent_required_and_snapshot_retained_in_followups(self):
        backend = Mock()
        backend.ask.return_value = "Answer"
        loader = Mock(return_value=Credential("fake", "test"))
        service = ChatService("openai", "test-model", backend, loader)
        attachment = TextAttachment("example.log", "fictional contents")
        with self.assertRaisesRegex(ChatError, "confirm"):
            service.send("Analyze", attachment=attachment)
        loader.assert_not_called()
        backend.ask.assert_not_called()
        service.send("Analyze", attachment=attachment, attachment_confirmed=True)
        service.send("Follow-up")
        sent = backend.ask.call_args.args[2]
        self.assertIn('"name": "example.log"', sent[0]["content"])
        self.assertIn("fictional contents", sent[0]["content"])
        self.assertEqual(sent[2]["content"], "Follow-up")
        service.clear()
        self.assertEqual(service.history, [])
        service.backend_mode = "offline"
        with self.assertRaisesRegex(ChatError, "requires OpenAI"):
            service.send("Analyze", attachment=attachment, attachment_confirmed=True)


if __name__ == "__main__":
    unittest.main()
