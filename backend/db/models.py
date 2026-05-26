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
    Column, Integer, String, DateTime, JSON, ForeignKey, Enum as SAEnum, Text,
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


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id          = Column(Integer, primary_key=True)
    email       = Column(String(255), unique=True, nullable=False, index=True)
    role        = Column(String(64), default="")
    referrer    = Column(String(255), default="")
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
