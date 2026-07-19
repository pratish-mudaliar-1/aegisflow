"""
AegisFlow :: auth.py
====================
Backend Control Plane — Authentication & Session Ownership

Implements:
  - X-API-Key header authentication (FastAPI Dependency)
  - Per-session owner token generation and constant-time validation
  - HITL session hijack prevention via X-Session-Token

Usage in endpoints:
  @app.post("/api/v1/workflow/run")
  async def run(payload, _key: str = Depends(require_api_key)):
      ...

  @app.post("/api/v1/workflow/resume")
  async def resume(payload, _key: str = Depends(require_api_key),
                   x_session_token: str = Header(default="")):
      ...
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger("aegisflow.auth")


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

def _get_configured_api_key() -> Optional[str]:
    """Return the server-configured API key, or None if not set."""
    key = os.getenv("AEGISFLOW_API_KEY", "").strip()
    return key if key else None


async def require_api_key(x_api_key: str = Header(default="")) -> str:
    """
    FastAPI Dependency: enforces X-API-Key authentication on every request.

    The caller must supply a matching ``X-API-Key`` header.

    Raises:
        503 Service Unavailable — if AEGISFLOW_API_KEY is not configured.
        401 Unauthorized        — if the header is missing or incorrect.
    """
    configured = _get_configured_api_key()

    if configured is None:
        logger.critical(
            "AEGISFLOW_API_KEY is not set — all API requests are being rejected. "
            "Set this environment variable to enable authenticated access."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "AUTH_NOT_CONFIGURED",
                "message": (
                    "Server API key is not configured. "
                    "Set AEGISFLOW_API_KEY in the server environment and restart."
                ),
            },
        )

    # Use secrets.compare_digest to prevent timing-based side-channel attacks
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), configured.encode()):
        logger.warning("Rejected request: missing or invalid X-API-Key header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "INVALID_API_KEY",
                "message": "Missing or invalid X-API-Key header. Access denied.",
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key


# ---------------------------------------------------------------------------
# Session Owner Token
# ---------------------------------------------------------------------------

def generate_owner_token() -> str:
    """
    Generate a cryptographically secure 32-byte URL-safe session owner token.

    This token is issued to the session creator at /run time and returned in
    the ``X-Session-Token`` response header. It must be supplied on all
    subsequent /resume and /status calls to prevent HITL session hijacking.
    """
    return secrets.token_urlsafe(32)


def validate_session_token(
    session_record: Optional[dict],
    provided_token: str,
    session_id: str,
) -> None:
    """
    Validate the X-Session-Token for a given session.

    Args:
        session_record:  The session dict from app.state.active_sessions.
        provided_token:  The token supplied by the caller in X-Session-Token.
        session_id:      The session_id being accessed (for error messages).

    Raises:
        404 Not Found  — if session_record is None (no such session).
        403 Forbidden  — if the token does not match the owner token.
    """
    if session_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SESSION_NOT_FOUND",
                "message": (
                    f"No active session found for session_id='{session_id}'. "
                    "The session may have expired or the ID is incorrect."
                ),
                "session_id": session_id,
            },
        )

    expected_token: str = session_record.get("owner_token", "")
    if (
        not provided_token
        or not expected_token
        or not secrets.compare_digest(
            provided_token.encode(), expected_token.encode()
        )
    ):
        logger.warning(
            "Invalid X-Session-Token for session_id=%s. "
            "Possible HITL session hijack attempt. Request rejected.",
            session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "INVALID_SESSION_TOKEN",
                "message": (
                    "The X-Session-Token does not match the token issued when "
                    "this session was created. You are not authorized to interact "
                    "with this session."
                ),
                "session_id": session_id,
            },
        )
