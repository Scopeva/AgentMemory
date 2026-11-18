"""Shared admission control for privileged HTTP routes."""

from __future__ import annotations

import os
from secrets import compare_digest

from fastapi import Header, HTTPException, Request, status


def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> None:
    """Require the configured admin token; privileged routes fail closed."""
    config = request.app.state.config
    expected = os.environ.get(config.security.admin_token_env)
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "admin token is not configured",
        )
    if x_admin_token is None or not compare_digest(x_admin_token, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid admin token")
