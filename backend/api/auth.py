"""
Auth + tier gating.

MVP flow:
  - Frontend uses Clerk; passes `Authorization: Bearer <clerk_jwt>` to backend
  - Backend either validates Clerk JWT (prod) OR accepts a dev token (local)
  - On first request, ensure-or-create a User row keyed by clerk_id

For local dev without a Clerk account:
  - Header `X-Dev-User: someone@example.com`  → auto-create/fetch a Free user
  - Header `X-Dev-User: someone@example.com:pro` → also sets tier
"""
from __future__ import annotations
import os
from typing import Optional
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.db import get_db, User, Tier


DEV_MODE = os.environ.get("EDGEKIT_DEV_AUTH", "1") == "1"


def _ensure_user(db: Session, email: str, tier: Tier = Tier.FREE,
                 clerk_id: Optional[str] = None) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if clerk_id and not user.clerk_id:
            user.clerk_id = clerk_id; db.commit()
        return user
    user = User(email=email, tier=tier, clerk_id=clerk_id)
    db.add(user); db.commit(); db.refresh(user)
    return user


def current_user(
    db:           Session     = Depends(get_db),
    x_dev_user:   Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> User:
    """Resolve the calling user.
    Real Clerk JWT validation happens in production. Dev-mode header for local."""
    # ─── Dev-mode shortcut ───────────────────────────────────────────────
    if DEV_MODE and x_dev_user:
        parts = x_dev_user.split(":", 1)
        email = parts[0]
        tier  = Tier(parts[1]) if len(parts) > 1 else Tier.FREE
        return _ensure_user(db, email=email, tier=tier)

    # ─── Production: Clerk JWT (stub — wire jwks verify when deploying) ──
    if authorization and authorization.lower().startswith("bearer "):
        # TODO: verify Clerk JWT signature against their JWKS. For MVP we
        # parse the token claims optimistically and let it fail later if invalid.
        try:
            import base64, json
            token   = authorization.split(" ", 1)[1]
            payload = token.split(".")[1] + "=" * 4
            claims  = json.loads(base64.urlsafe_b64decode(payload))
            email    = claims.get("email") or claims.get("primary_email")
            clerk_id = claims.get("sub")
            if not email:
                raise HTTPException(401, "JWT missing email claim")
            return _ensure_user(db, email=email, clerk_id=clerk_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(401, f"Invalid auth token: {e}")

    raise HTTPException(401, "Not authenticated. "
                             "Send `X-Dev-User: email@example.com` (dev) "
                             "or `Authorization: Bearer <clerk_jwt>` (prod).")


def require_tier(min_tier: Tier):
    """Dependency factory: 403s if user is below the required tier."""
    order = {Tier.FREE: 0, Tier.TRADER: 1, Tier.PRO: 2}
    def _dep(user: User = Depends(current_user)) -> User:
        if order[user.tier] < order[min_tier]:
            raise HTTPException(403, f"Requires {min_tier.value} tier (you are {user.tier.value})")
        return user
    return _dep
