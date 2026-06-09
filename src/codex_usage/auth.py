from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import (
    OAUTH_AUTH_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
    OAUTH_TOKEN_URL,
    AuthTokens,
    save_auth,
)


class OAuthError(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def extract_account_id(access_token: str, id_token: str | None) -> str | None:
    for token in (id_token, access_token):
        if not token:
            continue
        claims = decode_jwt_payload(token)
        for key in (
            "chatgpt_account_id",
            "account_id",
            "https://api.openai.com/auth",
        ):
            value = claims.get(key)
            if isinstance(value, dict):
                value = value.get("chatgpt_account_id") or value.get("account_id")
            if isinstance(value, str) and value:
                return value
    return None


def extract_email(access_token: str, id_token: str | None) -> str | None:
    for token in (id_token, access_token):
        if not token:
            continue
        claims = decode_jwt_payload(token)
        email = claims.get("email")
        if isinstance(email, str) and email:
            return email
    return None


def build_auth_url(state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "scope": OAUTH_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    return f"{OAUTH_AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str, code_verifier: str) -> AuthTokens:
    response = httpx.post(
        OAUTH_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": OAUTH_CLIENT_ID,
            "code": code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise OAuthError(f"Token exchange failed: {response.text}")

    data = response.json()
    access_token = data["access_token"]
    id_token = data.get("id_token")
    return AuthTokens(
        access_token=access_token,
        refresh_token=data.get("refresh_token", ""),
        id_token=id_token,
        account_id=extract_account_id(access_token, id_token),
        email=extract_email(access_token, id_token),
        last_refresh=datetime.now(timezone.utc),
    )


def refresh_tokens(tokens: AuthTokens) -> AuthTokens:
    if not tokens.refresh_token:
        return tokens

    response = httpx.post(
        OAUTH_TOKEN_URL,
        json={
            "client_id": OAUTH_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "scope": OAUTH_SCOPE,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise OAuthError(f"Token refresh failed: {response.text}")

    data = response.json()
    access_token = data.get("access_token", tokens.access_token)
    id_token = data.get("id_token", tokens.id_token)
    return AuthTokens(
        access_token=access_token,
        refresh_token=data.get("refresh_token", tokens.refresh_token),
        id_token=id_token,
        account_id=tokens.account_id or extract_account_id(access_token, id_token),
        email=tokens.email or extract_email(access_token, id_token),
        last_refresh=datetime.now(timezone.utc),
    )


def _run_callback_server(
    expected_state: str,
    result: dict,
    done: threading.Event,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in ("/auth/callback", "/success", "/error"):
                self.send_error(404)
                return

            if parsed.path == "/auth/callback":
                params = parse_qs(parsed.query)
                state = params.get("state", [""])[0]
                code = params.get("code", [""])[0]
                error = params.get("error", [""])[0]

                if error:
                    result["error"] = error
                    self._respond(
                        400,
                        "<h1>Login failed</h1><p>You can close this tab.</p>",
                    )
                elif state != expected_state:
                    result["error"] = "State mismatch"
                    self._respond(
                        400,
                        "<h1>State mismatch</h1><p>Please try again.</p>",
                    )
                else:
                    result["code"] = code
                    self._respond(
                        200,
                        "<h1>Login successful</h1><p>You can close this tab.</p>",
                    )
                done.set()
                return

            self.send_error(404)

        def _respond(self, status: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = HTTPServer(("127.0.0.1", 1455), Handler)
    server.timeout = 1
    while not done.is_set():
        server.handle_request()
    server.server_close()


def login() -> AuthTokens:
    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    auth_url = build_auth_url(state, code_challenge)

    result: dict[str, str] = {}
    done = threading.Event()
    server_thread = threading.Thread(
        target=_run_callback_server,
        args=(state, result, done),
        daemon=True,
    )
    server_thread.start()

    print("Opening browser for Codex login...")
    print(f"If the browser does not open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    if not done.wait(timeout=300):
        raise OAuthError("Login timed out after 5 minutes")

    if result.get("error"):
        raise OAuthError(result["error"])

    code = result.get("code")
    if not code:
        raise OAuthError("No authorization code received")

    tokens = exchange_code(code, code_verifier)
    save_auth(tokens)
    print(f"Logged in as {tokens.email or 'unknown'}")
    return tokens


def login_cli() -> None:
    try:
        login()
    except OAuthError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    login_cli()
