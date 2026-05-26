"""
Lemon Squeezy billing integration.

We use Lemon Squeezy as a Merchant-of-Record — they handle global VAT/tax,
chargeback risk, and currency conversion. We just:
  1. Generate a checkout URL for a tier
  2. Receive webhook events when a subscription is created/updated/cancelled
  3. Update user.tier accordingly

Env vars expected (set later, before going live):
  LEMON_SQUEEZY_API_KEY       — server-side key
  LEMON_SQUEEZY_STORE_ID
  LEMON_SQUEEZY_VARIANT_TRADER_INR
  LEMON_SQUEEZY_VARIANT_TRADER_USD
  LEMON_SQUEEZY_VARIANT_PRO_INR
  LEMON_SQUEEZY_VARIANT_PRO_USD
  LEMON_SQUEEZY_WEBHOOK_SECRET
"""
from __future__ import annotations
import os, hmac, hashlib, json
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from backend.db import get_db, User, Tier
from backend.api.auth import current_user

router = APIRouter(prefix="/billing", tags=["billing"])

API_KEY        = os.environ.get("LEMON_SQUEEZY_API_KEY", "")
STORE_ID       = os.environ.get("LEMON_SQUEEZY_STORE_ID", "")
WEBHOOK_SECRET = os.environ.get("LEMON_SQUEEZY_WEBHOOK_SECRET", "")

VARIANTS = {
    ("trader", "INR"): os.environ.get("LEMON_SQUEEZY_VARIANT_TRADER_INR", ""),
    ("trader", "USD"): os.environ.get("LEMON_SQUEEZY_VARIANT_TRADER_USD", ""),
    ("pro",    "INR"): os.environ.get("LEMON_SQUEEZY_VARIANT_PRO_INR",    ""),
    ("pro",    "USD"): os.environ.get("LEMON_SQUEEZY_VARIANT_PRO_USD",    ""),
}


@router.post("/checkout")
def create_checkout(
    tier:     Literal["trader", "pro"],
    currency: Literal["INR", "USD"] = "USD",
    user:     User    = Depends(current_user),
):
    """Return a Lemon Squeezy checkout URL for the requested tier+currency.
    For MVP — when LS keys aren't set yet — returns a stub URL.
    """
    variant = VARIANTS.get((tier, currency))
    if not API_KEY or not variant:
        # Pre-launch stub — frontend can still show the flow
        return {"url": f"https://edgekit.app/checkout-stub?tier={tier}&cur={currency}",
                "stub": True}

    # Real Lemon Squeezy call
    import requests
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email":  user.email,
                    "custom": {"user_id": str(user.id), "tier": tier},
                },
            },
            "relationships": {
                "store":   {"data": {"type": "stores",          "id": STORE_ID}},
                "variant": {"data": {"type": "variants",        "id": variant}},
            },
        }
    }
    r = requests.post(
        "https://api.lemonsqueezy.com/v1/checkouts",
        headers={"Accept": "application/vnd.api+json",
                 "Content-Type": "application/vnd.api+json",
                 "Authorization": f"Bearer {API_KEY}"},
        json=payload, timeout=15,
    )
    if not r.ok:
        raise HTTPException(502, f"Lemon Squeezy: {r.status_code} {r.text[:200]}")
    return {"url": r.json()["data"]["attributes"]["url"], "stub": False}


def _verify_webhook(raw: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        return True   # MVP: allow unsigned in dev
    digest = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


@router.post("/webhook")
async def webhook(
    request:           Request,
    x_signature:       Optional[str] = Header(default=None),
    db:                Session       = Depends(get_db),
):
    raw = await request.body()
    if not _verify_webhook(raw, x_signature or ""):
        raise HTTPException(401, "Invalid signature")
    evt = json.loads(raw or b"{}")
    meta = evt.get("meta", {})
    event_name  = meta.get("event_name")
    custom_data = (evt.get("data", {})
                      .get("attributes", {})
                      .get("first_subscription_item", {})
                      .get("custom_data") or {})
    user_id_str = (meta.get("custom_data", {}) or custom_data).get("user_id")
    tier_str    = (meta.get("custom_data", {}) or custom_data).get("tier")

    if user_id_str and tier_str:
        user = db.query(User).filter(User.id == int(user_id_str)).first()
        if user:
            if event_name in ("subscription_created", "subscription_resumed", "subscription_updated"):
                user.tier = Tier(tier_str)
            elif event_name in ("subscription_cancelled", "subscription_expired"):
                user.tier = Tier.FREE
            db.commit()
    return {"ok": True, "event": event_name}
