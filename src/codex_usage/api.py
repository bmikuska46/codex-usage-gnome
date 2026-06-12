from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .auth import OAuthError, refresh_tokens
from .config import USAGE_URL, AuthTokens, load_auth, save_auth


@dataclass
class UsageWindow:
    used_percent: int
    remaining_percent: int
    limit_window_seconds: int
    reset_after_seconds: int
    reset_at: int

    @property
    def reset_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.reset_at, tz=timezone.utc).astimezone()


@dataclass
class UsageData:
    plan_type: str
    email: str | None
    primary: UsageWindow | None
    secondary: UsageWindow | None
    limit_reached: bool
    error: str | None = None
    authenticated: bool = False

    def to_variant(self) -> dict:
        return {
            "plan_type": self.plan_type,
            "email": self.email or "",
            "limit_reached": self.limit_reached,
            "error": self.error or "",
            "authenticated": self.authenticated,
            "primary": self._window_variant(self.primary),
            "secondary": self._window_variant(self.secondary),
        }

    @staticmethod
    def _window_variant(window: UsageWindow | None) -> dict:
        if window is None:
            return {}
        return {
            "used_percent": window.used_percent,
            "remaining_percent": window.remaining_percent,
            "limit_window_seconds": window.limit_window_seconds,
            "reset_after_seconds": window.reset_after_seconds,
            "reset_at": window.reset_at,
            "reset_label": _format_reset(window.reset_after_seconds, window.reset_at),
        }


def _format_reset(reset_after_seconds: int, reset_at: int) -> str:
    if reset_after_seconds <= 0:
        return "now"
    hours, remainder = divmod(reset_after_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours >= 24:
        days = hours // 24
        hours = hours % 24
        return f"in {days}d {hours}h"
    if hours > 0:
        return f"in {hours}h {minutes}m"
    if reset_after_seconds < 300:
        if minutes > 0:
            return f"in {minutes} min {seconds} secs"
        return f"in {seconds} secs"
    return f"in {minutes}m"


def _parse_window(data: dict | None) -> UsageWindow | None:
    if not data:
        return None
    used = int(data.get("used_percent", 0))
    return UsageWindow(
        used_percent=used,
        remaining_percent=max(0, 100 - used),
        limit_window_seconds=int(data.get("limit_window_seconds", 0)),
        reset_after_seconds=int(data.get("reset_after_seconds", 0)),
        reset_at=int(data.get("reset_at", 0)),
    )


def _fetch_usage(tokens: AuthTokens) -> UsageData:
    headers = {
        "Authorization": f"Bearer {tokens.access_token}",
        "Accept": "application/json",
        "User-Agent": "codex-usage/1.0",
    }
    if tokens.account_id:
        headers["ChatGPT-Account-Id"] = tokens.account_id

    response = httpx.get(USAGE_URL, headers=headers, timeout=30)
    if response.status_code in (401, 403):
        raise OAuthError("Unauthorized")
    response.raise_for_status()

    payload = response.json()
    rate_limit = payload.get("rate_limit") or {}
    return UsageData(
        plan_type=str(payload.get("plan_type", "unknown")),
        email=payload.get("email") or tokens.email,
        primary=_parse_window(rate_limit.get("primary_window")),
        secondary=_parse_window(rate_limit.get("secondary_window")),
        limit_reached=bool(rate_limit.get("limit_reached", False)),
        authenticated=True,
    )


def get_usage(force_refresh: bool = False) -> UsageData:
    tokens = load_auth()
    if tokens is None:
        return UsageData(
            plan_type="",
            email=None,
            primary=None,
            secondary=None,
            limit_reached=False,
            error="Not logged in",
        )

    if tokens.needs_refresh() or force_refresh:
        try:
            tokens = refresh_tokens(tokens)
            save_auth(tokens)
        except OAuthError:
            return UsageData(
                plan_type="",
                email=tokens.email,
                primary=None,
                secondary=None,
                limit_reached=False,
                error="Session expired — please log in again",
            )

    try:
        return _fetch_usage(tokens)
    except OAuthError:
        try:
            tokens = refresh_tokens(tokens)
            save_auth(tokens)
            return _fetch_usage(tokens)
        except OAuthError as exc:
            return UsageData(
                plan_type="",
                email=tokens.email,
                primary=None,
                secondary=None,
                limit_reached=False,
                error=str(exc),
            )
        except httpx.HTTPError as exc:
            return UsageData(
                plan_type="",
                email=tokens.email,
                primary=None,
                secondary=None,
                limit_reached=False,
                error=str(exc),
                authenticated=True,
            )
    except httpx.HTTPError as exc:
        return UsageData(
            plan_type="",
            email=tokens.email,
            primary=None,
            secondary=None,
            limit_reached=False,
            error=str(exc),
            authenticated=True,
        )
