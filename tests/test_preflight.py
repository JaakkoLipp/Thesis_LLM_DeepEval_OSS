"""Tests for run_preflight."""
from __future__ import annotations

import importlib
import logging

from deepeval_mvp import preflight


def _make_logger() -> tuple[logging.Logger, list[logging.LogRecord]]:
    """Return a logger and the list it appends records to."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(f"test_preflight_{id(records)}")
    logger.addHandler(_Capture())
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger, records


def _noop_db_ping(uri: str) -> None:
    """Simulates a successful database ping."""
    pass


def _set_valid_env(monkeypatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB", "test_db")
    monkeypatch.setenv("JUDGE_MODEL", "llama3")
    monkeypatch.delenv("ENABLE_PROMPT_ALIGNMENT", raising=False)


def test_preflight_fails_when_required_env_missing(monkeypatch):
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_DB", raising=False)
    monkeypatch.delenv("MONGODB_DB", raising=False)
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    monkeypatch.delenv("ENABLE_PROMPT_ALIGNMENT", raising=False)

    # Stub out deepeval check so only env check triggers failure
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    logger, records = _make_logger()
    result = preflight.run_preflight(logger, db_ping=_noop_db_ping)

    assert result is False
    error_msgs = [r.getMessage() for r in records if r.levelno == logging.ERROR]
    assert any("missing required env" in m for m in error_msgs)


def test_preflight_fails_when_prompt_alignment_enabled_without_instructions(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("ENABLE_PROMPT_ALIGNMENT", "1")
    monkeypatch.delenv("PROMPT_INSTRUCTIONS", raising=False)

    # Stub out deepeval so only the PA check fires
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    logger, records = _make_logger()
    result = preflight.run_preflight(logger, db_ping=_noop_db_ping)

    assert result is False
    error_msgs = [r.getMessage() for r in records if r.levelno == logging.ERROR]
    assert any("PROMPT_INSTRUCTIONS" in m for m in error_msgs)


def test_preflight_passes_when_prompt_alignment_disabled(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("ENABLE_PROMPT_ALIGNMENT", "0")

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    logger, _records = _make_logger()
    result = preflight.run_preflight(logger, db_ping=_noop_db_ping)

    assert result is True


def test_preflight_passes_when_prompt_alignment_enabled_with_instructions(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("ENABLE_PROMPT_ALIGNMENT", "1")
    monkeypatch.setenv("PROMPT_INSTRUCTIONS", "Be concise,Be accurate")

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())

    logger, _records = _make_logger()
    result = preflight.run_preflight(logger, db_ping=_noop_db_ping)

    assert result is True


def test_preflight_fails_when_deepeval_missing(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    logger, records = _make_logger()
    result = preflight.run_preflight(logger, db_ping=_noop_db_ping)

    assert result is False
    error_msgs = [r.getMessage() for r in records if r.levelno == logging.ERROR]
    assert any("deepeval" in m for m in error_msgs)
