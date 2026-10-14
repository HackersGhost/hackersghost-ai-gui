import unittest
from unittest.mock import patch

from hackersghost_ai.core.attachments import TextAttachment
from hackersghost_ai.core.chat_service import ChatService
from hackersghost_ai.core.credentials import Credential


class FakeBackend:
    def ask(self, key, model, history):
        return "A firewall rule controls network traffic."


class V2ChatMemoryTests(unittest.TestCase):
    def service(self):
        return ChatService(
            backend_mode="openai",
            model="test-model",
            backend=FakeBackend(),
            credential_loader=lambda session_key: Credential("fake-key", "test"),
        )

    def test_successful_plain_exchange_is_remembered(self):
        service = self.service()
        with patch("hackersghost_ai.core.memory.record_exchange", return_value=True) as remember, \
             patch("hackersghost_ai.core.memory.is_enabled", return_value=True):
            response = service.send("Explain a firewall rule")
            self.assertEqual(response.text, "A firewall rule controls network traffic.")
            remember.assert_called_once_with(
                "Explain a firewall rule",
                "A firewall rule controls network traffic.",
            )

    def test_attachment_contents_are_not_persisted_but_typed_prompt_is_remembered(self):
        service = self.service()
        attachment = TextAttachment("example.log", "fictional log content")
        with patch("hackersghost_ai.core.memory.record_exchange", return_value=True) as remember, \
             patch("hackersghost_ai.core.memory.is_enabled", return_value=True):
            response = service.send(
                "Explain this log",
                attachment=attachment,
                attachment_confirmed=True,
            )
            self.assertEqual(response.text, "A firewall rule controls network traffic.")
            remember.assert_called_once_with(
                "Explain this log",
                "A firewall rule controls network traffic.",
            )
            saved_prompt = remember.call_args.args[0]
            self.assertNotIn("fictional log content", saved_prompt)
            self.assertNotIn("Untrusted file content", saved_prompt)


if __name__ == "__main__":
    unittest.main()
