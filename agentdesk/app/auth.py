from __future__ import annotations

from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials
from fastapi import Header, HTTPException, status

from app.config import get_settings

_INGEST_ROLES = {"owner", "ops"}


@dataclass(frozen=True)
class Caller:
    tenant_id: str
    role: str
    uid: str


def _ensure_firebase_app() -> None:
    if not firebase_admin._apps:
        # ADC on Cloud Run; GOOGLE_APPLICATION_CREDENTIALS locally.
        firebase_admin.initialize_app(credentials.ApplicationDefault())


def resolve_caller(
    authorization: str | None = Header(default=None),
    x_debug_tenant: str | None = Header(default=None),
    x_debug_role: str | None = Header(default=None),
) -> Caller:
    """FastAPI dependency. Returns the authenticated Caller or raises 401/403."""
    s = get_settings()

    # Local-dev escape hatch ONLY. Disabled in Cloud Run (AUTH_DEBUG=0).
    if s.auth_debug:
        if not x_debug_tenant or not x_debug_role:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "debug headers required")
        if x_debug_role not in _INGEST_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "role not permitted")
        return Caller(tenant_id=x_debug_tenant, role=x_debug_role, uid="debug")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]

    _ensure_firebase_app()
    try:
        decoded = fb_auth.verify_id_token(token)
        print("*decode***********", decoded)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    # Tenant + role are custom claims set at tenant/user provisioning (UC-01).
    tenant_id = decoded.get("tenant_id")
    role = decoded.get("role")
    if not tenant_id or not role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token missing tenant/role claims")
    if role not in _INGEST_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "role not permitted to ingest")

    return Caller(tenant_id=tenant_id, role=role, uid=decoded.get("uid", ""))