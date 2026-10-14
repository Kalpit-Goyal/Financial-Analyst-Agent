import os

os.environ.setdefault("GROQ_API_KEY", "dummy_key_for_testing")

import pytest

from monitor import config as cfg
from monitor import db


@pytest.fixture
def database(tmp_path, monkeypatch):
    """A fresh SQLite database per test."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    db.reset_engine()
    db.init_db()
    yield db
    db.reset_engine()


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(cfg, "LLM_RETRY_SLEEP", 0)
