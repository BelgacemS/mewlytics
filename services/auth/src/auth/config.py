import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    private_key_file: Path
    issuer: str
    token_ttl: timedelta

    @classmethod
    def from_env(cls) -> "Settings":
        """Read the settings, failing at startup rather than at the first login."""
        key_file = os.environ.get("AUTH_PRIVATE_KEY_FILE")
        if not key_file:
            raise RuntimeError("AUTH_PRIVATE_KEY_FILE is not set")
        ttl = int(os.environ.get("AUTH_TOKEN_TTL_SECONDS", "3600"))
        if ttl <= 0:
            raise RuntimeError("AUTH_TOKEN_TTL_SECONDS must be positive")
        return cls(
            private_key_file=Path(key_file),
            issuer=os.environ.get("AUTH_ISSUER", "mewlytics-auth"),
            token_ttl=timedelta(seconds=ttl),
        )
