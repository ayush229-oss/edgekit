"""QA check for FINDING-5: backtest quota must fail CLOSED.

Exercises enforce_backtest_quota across the quota-source matrix, monkeypatching
the Supabase layer so no network is required. Previously a Supabase count error
silently set used=0 (fail OPEN); it must now raise 503 (fail CLOSED).
"""
from types import SimpleNamespace

from fastapi import HTTPException
import backend.api.supa as supa
from backend.api import limits
from backend.db import Tier

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(("[PASS] " if cond else "[FAIL] ") + name + (f" -- {detail}" if detail else ""))


def user(tier=Tier.FREE, clerk_id="user_123"):
    return SimpleNamespace(tier=tier, clerk_id=clerk_id, id=1)


def call(u):
    """Return ('ok', None) or ('http', status_code)."""
    try:
        limits.enforce_backtest_quota(user=u, db=None)
        return ("ok", None)
    except HTTPException as e:
        return ("http", e.status_code)


def set_supa(enabled, count_fn):
    supa.enabled = lambda: enabled
    supa.count = count_fn


def main():
    # 1) Unlimited tier -> always ok, supa never consulted
    set_supa(True, lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
    check("1 PRO tier unlimited -> ok", call(user(Tier.PRO)) == ("ok", None))

    # 2) Supabase disabled (local dev) -> not enforced
    set_supa(False, lambda *a, **k: 999)
    check("2 supa disabled -> ok (dev)", call(user()) == ("ok", None))

    # 3) Enabled but no clerk_id (header/anon) -> not enforced
    set_supa(True, lambda *a, **k: 999)
    check("3 no clerk_id -> ok", call(user(clerk_id=None)) == ("ok", None))

    # 4) Enabled + under cap -> ok
    set_supa(True, lambda *a, **k: 3)
    check("4 under cap -> ok", call(user()) == ("ok", None))

    # 5) Enabled + at/over cap -> 429
    set_supa(True, lambda *a, **k: 10)
    check("5 at cap -> 429", call(user()) == ("http", 429))

    # 6) Enabled + counter ERRORS -> 503 (THE FIX; was fail-open -> ok before)
    def boom(*a, **k):
        raise RuntimeError("supabase unreachable")
    set_supa(True, boom)
    check("6 count error -> 503 (fail CLOSED)", call(user()) == ("http", 503))

    ok = all(results)
    print(f"\nQUOTA FAIL-CLOSED CHECK: {'PASS' if ok else 'FAIL'} ({sum(results)}/{len(results)})")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
