"""Per-launch API token and Origin checking (SR-2)."""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def new_token() -> str:
    return secrets.token_urlsafe(32)


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Reject mismatched Origin; require the bearer token on everything under /api/."""

    def __init__(self, app, token: str, allowed_origins: frozenset[str]):
        super().__init__(app)
        self._token = token
        self._origins = allowed_origins

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and origin not in self._origins:
            return error_response(403, "origin_not_allowed", "Request origin is not allowed.")
        if request.url.path.startswith("/api/"):
            header = request.headers.get("authorization", "")
            supplied = header[7:] if header.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), self._token.encode()):
                return error_response(401, "unauthorized", "Missing or invalid session token.")
        return await call_next(request)
