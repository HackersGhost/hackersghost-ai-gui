"""Read the same Secret Service entry as HackersGhost AI CLI 0.2.5."""

from dataclasses import dataclass, field
import os
import shutil
import subprocess

from hackersghost_ai.core.errors import ChatError


ATTRIBUTES = ("application", "hackersghost-ai", "credential", "openai-api-key")


@dataclass(frozen=True)
class Credential:
    value: str = field(repr=False)
    source: str


def load_credential(session_key: str = "") -> Credential:
    if session_key.strip():
        return _validated(session_key.strip(), "session key")
    environment_key = os.getenv("OPENAI_API_KEY", "").strip()
    if environment_key:
        return _validated(environment_key, "environment")
    executable = shutil.which("secret-tool")
    if executable:
        try:
            result = subprocess.run(
                [executable, "lookup", *ATTRIBUTES],
                input="", text=True, capture_output=True, timeout=60, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ChatError("The Linux keyring is unavailable. Unlock it or enter a session key.") from None
        if result.returncode == 0 and result.stdout.strip():
            return _validated(result.stdout.strip(), "Linux keyring")
    raise ChatError("No API key found. Enter a session key or save one with the CLI.")


def _validated(value: str, source: str) -> Credential:
    if any(character.isspace() or ord(character) < 33 or ord(character) > 126 for character in value):
        raise ChatError("The API key contains invalid characters. Check the selected key.")
    return Credential(value, source)
