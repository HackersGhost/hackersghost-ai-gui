from dataclasses import dataclass

from hackersghost_ai import __version__


@dataclass(frozen=True)
class AppInfo:
    name: str = "HackersGhost AI"
    version: str = __version__
    channel: str = "stable"

    @property
    def display_version(self) -> str:
        return f"{self.name} v{self.version} ({self.channel})"
