"""Small in-memory bearer-token authentication for the local/demo API.

Production deployments should replace this with an identity provider or an
authenticated reverse proxy. Tokens are never written to MongoDB or logs.
"""

import os
import secrets
import time
from secrets import compare_digest

from fastapi import HTTPException, Request

_tokens = {}
TOKEN_TTL_SECONDS = 8 * 60 * 60


def login(username, password):
    configured_user = os.getenv("ADMIN_USERNAME", "admin")
    configured_password = os.getenv("ADMIN_PASSWORD")
    if not configured_password:
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured. Set ADMIN_PASSWORD.",
        )
    if not compare_digest(username or "", configured_user):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not compare_digest(password or "", configured_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return token


def logout(token):
    if token:
        _tokens.pop(token, None)


def _clean_expired():
    now = time.time()
    for token, expires_at in list(_tokens.items()):
        if expires_at <= now:
            _tokens.pop(token, None)


def require_bearer(request):
    _clean_expired()
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    if token not in _tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
