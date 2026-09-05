"""
Tests for enforce_anon_compute_quota (backend/api/limits.py).

The /graph/v2 compute routes -- backtest, sweep, chart-preview, walk-forward,
monte-carlo -- are deliberately open so a visitor can try the builder before
signing up. Unmetered, that lets anyone monopolise a single-instance backend;
one sweep is roughly 25 seconds of engine time.

Two properties matter and are easy to regress:
  1. A caller presenting *any* credential must pass straight through, because
     signed-in users are already metered by enforce_backtest_quota. Double
     metering would silently halve a paying user's allowance.
  2. Anonymous callers are counted per client IP, so one visitor exhausting
     the allowance must not lock everyone else out.
"""

import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.api import limits


class _Client:
    def __init__(self, host):
        self.host = host


class _Req:
    """Minimal stand-in for fastapi.Request — the guard only reads .client.host."""
    def __init__(self, host):
        self.client = _Client(host) if host else None


@pytest.fixture(autouse=True)
def isolated_counter(tmp_path, monkeypatch):
    """Point the counter at a temp file so tests never touch real usage data."""
    monkeypatch.setattr(limits, "_COMPUTE_FILE", Path(tmp_path) / "compute_usage.json")
    monkeypatch.setattr(limits, "_COMPUTE_LOCK", threading.Lock())


def _call(host="1.2.3.4", cap=3, **kw):
    return limits.enforce_anon_compute_quota(_Req(host), cap=cap, **kw)


def test_anonymous_caller_is_capped():
    for _ in range(3):
        _call()
    with pytest.raises(HTTPException) as e:
        _call()
    assert e.value.status_code == 429


def test_cap_is_per_ip_not_global():
    """One noisy visitor must not lock out everybody else."""
    for _ in range(3):
        _call(host="1.1.1.1")
    with pytest.raises(HTTPException):
        _call(host="1.1.1.1")

    _call(host="2.2.2.2")   # a different visitor is unaffected


@pytest.mark.parametrize("creds", [
    {"authorization": "Bearer some.jwt.token"},
    {"x_dev_user": "trader@example.com"},
])
def test_authenticated_callers_are_never_metered_here(creds):
    """Signed-in users are metered by their plan quota, not this guard."""
    for _ in range(50):          # far beyond the cap
        _call(cap=3, **creds)


def test_blank_credentials_still_count_as_anonymous():
    """An empty header must not be mistaken for proof of identity."""
    for _ in range(3):
        _call(authorization="   ", x_dev_user="")
    with pytest.raises(HTTPException):
        _call(authorization="   ", x_dev_user="")


def test_missing_client_does_not_crash():
    """Some ASGI setups leave request.client as None; degrade, don't 500."""
    _call(host=None)


def test_unwritable_counter_fails_open(monkeypatch):
    """A broken disk must not take the API down with it.

    Note _save_usage creates parent directories, so a merely missing path is
    not enough to simulate this -- the write itself has to fail.
    """
    def boom(*a, **kw):
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "write_text", boom)
    for _ in range(10):
        _call(cap=1)   # never raises: the counter simply cannot persist
