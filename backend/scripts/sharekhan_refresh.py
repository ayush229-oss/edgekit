"""
Refresh the Sharekhan access token.

Sharekhan's access tokens expire ~10-11 hours after issuance and there is no
refresh-token flow — re-authenticating means redoing the browser login dance.
Run this whenever backend/.sharekhan_session.json is missing or expired:

    python backend/scripts/sharekhan_refresh.py

It prints a login URL, waits for you to paste back the redirected URL (or just
the request_token), exchanges it for an access token, and saves it alongside
its expiry to backend/.sharekhan_session.json (git-ignored, same as .env).
data_loader.py reads that file; if it's missing/expired it silently falls
back to Yahoo Finance rather than failing the request.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
dotenv.load_dotenv(_BACKEND_DIR / ".env", override=False)

SESSION_FILE = _BACKEND_DIR / ".sharekhan_session.json"


def _extract_request_token(raw: str) -> str:
    raw = raw.strip()
    if "request_token=" in raw:
        qs = parse_qs(urlparse(raw).query)
        if "request_token" in qs:
            return qs["request_token"][0]
    return raw


def main() -> None:
    api_key = os.environ.get("SHAREKHAN_API_KEY", "").strip()
    secret_key = os.environ.get("SHAREKHAN_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        print("SHAREKHAN_API_KEY / SHAREKHAN_SECRET_KEY not set in backend/.env")
        sys.exit(1)

    from SharekhanApi.sharekhanConnect import SharekhanConnect

    login = SharekhanConnect(api_key)
    print("1) Open this URL, log in with your Sharekhan account:\n")
    print(f"   {login.login_url()}\n")
    print("2) After redirect, copy the FULL URL from your browser's address bar")
    print("   (it contains ?request_token=...) and paste it below.\n")

    raw = input("Redirected URL (or just the request_token): ").strip()
    request_token = _extract_request_token(raw)

    session = login.generate_session_without_versionId(request_token, secret_key)
    resp = login.get_access_token(api_key, session, 12345)

    if resp.get("status") != 200:
        print("FAILED:", resp)
        sys.exit(1)

    data = resp["data"]
    access_token = data["token"]

    # Token is a JWT — decode the payload (no signature check needed, we just
    # issued it) to get the real expiry instead of guessing a TTL.
    import base64
    payload_b64 = access_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    expires_at = payload["exp"]

    SESSION_FILE.write_text(json.dumps({
        "access_token": access_token,
        "expires_at":   expires_at,
        "customer_id":  data.get("customerId"),
        "full_name":    data.get("fullName"),
    }, indent=2))

    ttl_hours = (expires_at - time.time()) / 3600
    print(f"\nSaved to {SESSION_FILE}")
    print(f"Logged in as: {data.get('fullName')} (customer {data.get('customerId')})")
    print(f"Valid for ~{ttl_hours:.1f} more hours.")


if __name__ == "__main__":
    main()
