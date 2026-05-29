"""Core ORM models for Edgekit MVP.

User
  - id, email, clerk_id, tier (Free/Trader/Pro), created_at
SavedStrategy
  - id, user_id, strategy_id, name, params (JSON), tps (JSON), notes
BacktestRun
  - id, user_id, strategy_id, params_snapshot (JSON), metrics (JSON), created_at
WaitlistEntry
  - id, email, role, created_at
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, DateTime, JSON, ForeignKey,
    Enum as SAEnum, Text,
)
from sqlalchemy.orm import relationship
from .session import Base


class Tier(str, Enum):
    FREE   = "free"
    TRADER = "trader"
    PRO    = "pro"


class User(Base):
    __tablename__ = "users"
    id           = Column(Integer, primary_key=True)
    email        = Column(String(255), unique=True, nullable=False, index=True)
    clerk_id     = Column(String(64), unique=True, index=True, nullable=True)
    tier         = Column(SAEnum(Tier), default=Tier.FREE, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    strategies   = relationship("SavedStrategy", back_populates="user", cascade="all,delete")
    runs         = relationship("BacktestRun",   back_populates="user", cascade="all,delete")


class SavedStrategy(Base):
    __tablename__ = "saved_strategies"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False)
    name        = Column(String(128), nullable=False)
    params      = Column(JSON, default=dict, nullable=False)
    tps         = Column(JSON, default=list, nullable=False)
    notes       = Column(Text, default="", nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow,
                         onupdate=datetime.utcnow, nullable=False)

    user        = relationship("User", back_populates="strategies")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id     = Column(String(64), nullable=False, index=True)
    params_snapshot = Column(JSON, default=dict, nullable=False)
    metrics         = Column(JSON, default=dict, nullable=False)
    symbol          = Column(String(32), default="")
    timeframe       = Column(String(16), default="")
    bars            = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user            = relationship("User", back_populates="runs")


class ForwardTest(Base):
    """A paper/forward test: a strategy tracked on fresh bars going forward from
    `started_at`, refreshed periodically so out-of-sample results accumulate."""
    __tablename__ = "forward_tests"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name        = Column(String(160), default="", nullable=False)
    symbol      = Column(String(32), default="XAUUSD", nullable=False)
    timeframe   = Column(String(16), default="M15", nullable=False)
    graph       = Column(JSON, default=dict, nullable=False)   # the v2 graph
    mgmt        = Column(JSON, default=dict, nullable=False)    # trade-management settings
    baseline    = Column(JSON, default=dict, nullable=False)    # backtest metrics at start (for compare)
    started_at  = Column(DateTime, nullable=False)             # data-time the forward window begins
    status      = Column(String(16), default="active", nullable=False)  # active | stopped
    latest      = Column(JSON, default=dict, nullable=False)    # {metrics, trades, equity, bars_seen, last_run}
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LiveTrade(Base):
    """Append-only ledger for Grade-3 (demo-execution) forward tests. Each row is
    a real order event with the ACTUAL fill — written once, never updated, so the
    record can't drift and can be trusted/verified."""
    __tablename__ = "live_trades"
    id              = Column(Integer, primary_key=True)
    forward_test_id = Column(Integer, index=True, nullable=False)
    ts              = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action          = Column(String(8),  default="open")    # open | close
    symbol          = Column(String(32), default="")
    side            = Column(String(8),  default="")         # buy | sell
    volume          = Column(Float,   default=0.0)
    requested_price = Column(Float,   default=0.0)
    fill_price      = Column(Float,   default=0.0)
    slippage        = Column(Float,   default=0.0)
    spread          = Column(Float,   default=0.0)
    sl              = Column(Float,   default=0.0)
    tp              = Column(Float,   default=0.0)
    ticket          = Column(BigInteger, default=0)
    profit          = Column(Float,   default=0.0)           # realized, on close
    comment         = Column(String(64), default="")


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id          = Column(Integer, primary_key=True)
    email       = Column(String(255), unique=True, nullable=False, index=True)
    role        = Column(String(64), default="")
    referrer    = Column(String(255), default="")
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
