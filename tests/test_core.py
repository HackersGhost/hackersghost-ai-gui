import io
import json
import subprocess
import unittest
import urllib.error
from unittest.mock import Mock, patch

from hackersghost_ai.core.chat_service import ChatService, HISTORY_LIMIT, MESSAGE_LIMIT
from hackersghost_ai.core.credentials import ATTRIBUTES, Credential, load_credential
from hackersghost_ai.core.errors import ChatError
from hackersghost_ai.core.openai_backend import NoRedirect, OpenAIBackend, RESPONSE_LIMIT


class CredentialTests(unittest.TestCase):
    def test_existing_cli_entry_and_environment_precedence(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("shutil.which", return_value="/usr/bin/secret-tool"), \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "demo-key\n", "")) as run:
            credential = load_credential()
            self.assertEqual(credential.value, "demo-key")
            self.assertEqual(credential.source, "Linux keyring")
            self.assertEqual(run.call_args.args[0], ["/usr/bin/secret-tool", "lookup", *ATTRIBUTES])
            self.assertNotIn("demo-key", repr(credential))
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-demo"}, clear=True), \
             patch("subprocess.run") as run:
            self.assertEqual(load_credential().source, "environment")
            self.assertEqual(load_credential("session-demo").value, "session-demo")
            run.assert_not_called()

    def test_unavailable_keyring_and_timeout_are_sanitized(self):
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(ChatError, "No API key"):
                load_credential()
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value="secret-tool"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("secret-tool", 60, output="secret-value")):
            with self.assertRaises(ChatError) as error:
                load_credential()
            self.assertNotIn("secret-value", str(error.exception))

    def test_header_control_characters_are_rejected(self):
        with self.assertRaises(ChatError):
            load_credential("demo\r\nHeader: value")


class BackendTests(unittest.TestCase):
    def payload(self, text="Example answer"):
        return {"status": "completed", "output": [
            {"type": "reasoning"},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ]}

    def test_request_contract_and_text_only_response(self):
        response = io.BytesIO(json.dumps(self.payload()).encode())
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            result = OpenAIBackend().ask("fake-key", "test-model", [{"role": "user", "content": "Hello"}])
        self.assertEqual(result, "Example answer")
        request = opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(request.get_method(), "POST")
        self.assertFalse(body["store"])
        self.assertNotIn("tools", body)
        self.assertNotIn("previous_response_id", body)
        self.assertEqual(body["input"][0]["content"], "Hello")
        self.assertEqual(body["model"], "test-model")
        self.assertIn("Reply in the user's language", body["instructions"])

    def test_http_failure_does_not_expose_response_or_credential(self):
        for code in (302, 400, 401, 403, 404, 429, 500):
            with self.subTest(code=code):
                error = urllib.error.HTTPError("https://api.openai.com/v1/responses", code, "fake-key", {}, io.BytesIO(b"fake-key"))
                opener = Mock()
                opener.open.side_effect = error
                with patch("urllib.request.build_opener", return_value=opener):
                    with self.assertRaises(ChatError) as caught:
                        OpenAIBackend().ask("fake-key", "model", [])
                self.assertNotIn("fake-key", str(caught.exception))

    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_refusal_incomplete_malformed_and_non_text_results(self):
        self.assertEqual(OpenAIBackend._text({"status": "completed", "output": [
            {"type": "message", "content": [{"type": "refusal", "refusal": "Unable to help."}]},
        ]}), "Unable to help.")
        for result in ([], {}, {"status": "incomplete"}, {"status": "completed", "output": [
            {"type": "function_call", "name": "shell", "arguments": "ignored"},
        ]}):
            with self.subTest(result=result), self.assertRaises(ChatError):
                OpenAIBackend._text(result)

    def test_invalid_json_and_large_response(self):
        for payload in (b"not json", b"x" * (RESPONSE_LIMIT + 1)):
            opener = Mock()
            opener.open.return_value = io.BytesIO(payload)
            with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(ChatError):
                OpenAIBackend().ask("fake-key", "model", [])


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.backend = Mock()
        self.backend.ask.return_value = "First answer"
        self.loader = Mock(return_value=Credential("fake-key", "test"))
        self.service = ChatService("openai", "test-model", self.backend, self.loader)

    def test_followups_failed_turns_and_new_chat(self):
        self.service.send("First question")
        self.backend.ask.side_effect = ChatError("Timed out")
        with self.assertRaises(ChatError):
            self.service.send("Failed question")
        self.assertEqual(len(self.service.history), 2)
        self.backend.ask.side_effect = None
        self.service.send("Follow-up")
        sent = self.backend.ask.call_args.args[2]
        self.assertEqual([x["content"] for x in sent], ["First question", "First answer", "Follow-up"])
        self.service.clear()
        self.service.send("Fresh question")
        self.assertEqual(self.backend.ask.call_args.args[2], [{"role": "user", "content": "Fresh question"}])

    def test_offline_mode_never_looks_up_credentials_or_sends_requests(self):
        self.service.backend_mode = "offline"
        self.assertIn("Offline demo", self.service.send("Hello").text)
        self.loader.assert_not_called()
        self.backend.ask.assert_not_called()

    def test_invalid_input_stops_before_credentials_and_network(self):
        for prompt in (" ", "x" * (MESSAGE_LIMIT + 1)):
            with self.assertRaises(ChatError):
                self.service.send(prompt)
        self.service.model = " "
        with self.assertRaises(ChatError):
            self.service.send("Question")
        self.service.model = "test-model"
        self.service.history = [{"role": "user", "content": "x" * HISTORY_LIMIT}]
        with self.assertRaises(ChatError):
            self.service.send("Question")
        self.loader.assert_not_called()
        self.backend.ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
