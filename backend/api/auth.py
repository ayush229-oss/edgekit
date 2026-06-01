"""
Auth + tier gating.

MVP flow:
  - Frontend uses Clerk; passes `Authorization: Bearer <clerk_jwt>` to backend
  - Backend validates Clerk JWT signature against Clerk's JWKS (RS256)
  - On first request, ensure-or-create a User row keyed by clerk_id

For local dev without a Clerk account:
  - Set EDGEKIT_DEV_AUTH=1 in the environment, then:
  - Header `X-Dev-User: someone@example.com`  → auto-create/fetch a Free user
  - Header `X-Dev-User: someone@example.com:pro` → also sets tier
"""
from __future__ import annotations
import os
import time
import threading
from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.db import get_db, User, Tier


DEV_MODE = os.environ.get("EDGEKIT_DEV_AUTH", "0") == "1"

# Clerk JWKS — fetched once and cached; refreshed automatically by PyJWKClient
_CLERK_JWKS_URL = "https://mint-chipmunk-78.clerk.accounts.dev/.well-known/jwks.json"
_jwks_client: Optional[PyJWKClient] = None
_jwks_lock = threading.Lock()


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        with _jwks_lock:
            if _jwks_client is None:
                _jwks_client = PyJWKClient(_CLERK_JWKS_URL, cache_keys=True)
    return _jwks_client


def _verify_clerk_jwt(token: str) -> dict:
    """Verify a Clerk-issued RS256 JWT and return its claims."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_exp": True},
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired — please sign in again")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    except Exception as e:
        raise HTTPException(401, f"Auth error: {e}")


def _ensure_user(db: Session, email: str, tier: Tier = Tier.FREE,
                 clerk_id: Optional[str] = None) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if clerk_id and not user.clerk_id:
            user.clerk_id = clerk_id
            db.commit()
        return user
    user = User(email=email, tier=tier, clerk_id=clerk_id)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def current_user(
    db:            Session          = Depends(get_db),
    x_dev_user:    Optional[str]   = Header(default=None),
    authorization: Optional[str]   = Header(default=None),
) -> User:
    """Resolve the calling user from a verified Clerk JWT (prod) or dev header (dev)."""

    # ─── Dev-mode shortcut ───────────────────────────────────────────────────
    if DEV_MODE and x_dev_user:
        parts = x_dev_user.split(":", 1)
        email = parts[0]
        tier  = Tier(parts[1]) if len(parts) > 1 else Tier.FREE
        return _ensure_user(db, email=email, tier=tier)

    # ─── Production: verified Clerk JWT ─────────────────────────────────────
    if authorization and authorization.lower().startswith("bearer "):
        token  = authorization.split(" ", 1)[1]
        claims = _verify_clerk_jwt(token)

        email    = claims.get("email") or claims.get("primary_email")
        clerk_id = claims.get("sub")

        if not email:
            raise HTTPException(401, "JWT missing email claim")

        return _ensure_user(db, email=email, clerk_id=clerk_id)

    raise HTTPException(
        401,
        "Not authenticated. Send `Authorization: Bearer <clerk_jwt>` "
        "or set EDGEKIT_DEV_AUTH=1 and use `X-Dev-User: email@example.com`.",
    )


def require_tier(min_tier: Tier):
    """Dependency factory: 403s if user is below the required tier."""
    order = {Tier.FREE: 0, Tier.TRADER: 1, Tier.PRO: 2}
    def _dep(user: User = Depends(current_user)) -> User:
        if order[user.tier] < order[min_tier]:
            raise HTTPException(
                403,
                f"Requires {min_tier.value} tier (you are {user.tier.value})",
            )
        return user
    return _dep
