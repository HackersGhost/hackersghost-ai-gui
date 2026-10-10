from dataclasses import dataclass, field
import os


@dataclass
class AppSettings:
    backend_mode: str = "openai"
    model: str = field(default_factory=lambda: os.getenv("HACKERSGHOST_MODEL", "gpt-6-luna"))
