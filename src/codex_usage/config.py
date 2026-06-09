from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
CONFIG_DIR = CONFIG_HOME / "codex-usage"
AUTH_FILE = CONFIG_DIR / "auth.json"
LEGACY_AUTH_FILE = CONFIG_HOME / "chatgpt-usage" / "auth.json"

OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OAUTH_AUTH_URL = "https://auth.openai.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"
OAUTH_SCOPE = "openid profile email offline_access"

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

CODEX_AUTH_PATHS = [
    Path(os.environ["CODEX_HOME"]) / "auth.json" if os.environ.get("CODEX_HOME") else None,
    Path.home() / ".config" / "codex" / "auth.json",
    Path.home() / ".codex" / "auth.json",
]
CODEX_AUTH_PATHS = [p for p in CODEX_AUTH_PATHS if p is not None]

REFRESH_INTERVAL_SECONDS = 8 * 24 * 3600
POLL_INTERVAL_SECONDS = 60


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    id_token: str | None = None
    account_id: str | None = None
    email: str | None = None
    last_refresh: datetime | None = None

    def needs_refresh(self) -> bool:
        if not self.refresh_token:
            return False
        if self.last_refresh is None:
            return True
        age = datetime.now(timezone.utc) - self.last_refresh
        return age.total_seconds() > REFRESH_INTERVAL_SECONDS

    def to_dict(self) -> dict:
        return {
            "tokens": {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "id_token": self.id_token,
                "account_id": self.account_id,
            },
            "email": self.email,
            "last_refresh": (
                self.last_refresh.isoformat() if self.last_refresh else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> AuthTokens:
        tokens = data.get("tokens") or data
        last_refresh = data.get("last_refresh")
        parsed_refresh: datetime | None = None
        if last_refresh:
            parsed_refresh = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
            if parsed_refresh.tzinfo is None:
                parsed_refresh = parsed_refresh.replace(tzinfo=timezone.utc)

        return cls(
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            id_token=tokens.get("id_token"),
            account_id=tokens.get("account_id"),
            email=data.get("email"),
            last_refresh=parsed_refresh,
        )


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_auth(tokens: AuthTokens) -> None:
    ensure_config_dir()
    AUTH_FILE.write_text(json.dumps(tokens.to_dict(), indent=2), encoding="utf-8")
    AUTH_FILE.chmod(0o600)


def load_auth() -> AuthTokens | None:
    for path in [AUTH_FILE, LEGACY_AUTH_FILE, *CODEX_AUTH_PATHS]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("OPENAI_API_KEY"):
                continue
            tokens = data.get("tokens") or data
            if tokens.get("access_token"):
                return AuthTokens.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return None
