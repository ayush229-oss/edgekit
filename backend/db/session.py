"""SQLAlchemy session + engine. Defaults to local SQLite for dev."""
from __future__ import annotations
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).resolve().parent.parent.parent / 'edgekit_dev.db'}",
)

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Safe to call repeatedly."""
    from . import models  # noqa
    Base.metadata.create_all(bind=engine)
