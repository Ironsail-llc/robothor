"""Bridge dependency injection — shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request


def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request state (set by TenantMiddleware).

    Falls back to 'robothor-primary' if not set.
    """
    return getattr(request.state, "tenant_id", "robothor-primary")
