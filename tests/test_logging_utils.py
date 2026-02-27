"""Tests for logging_utils.py — KeyValueFormatter and event_log_context."""
from __future__ import annotations

import logging

from deepeval_mvp.logging_utils import KeyValueFormatter, _format_value, event_log_context
from deepeval_mvp.models import AIEvent

# ── _format_value ─────────────────────────────────────────────────────────────

class TestFormatValue:
    def test_simple_value_no_quotes(self):
        assert _format_value("hello") == "hello"

    def test_value_with_spaces_gets_quoted(self):
        assert _format_value("hello world") == '"hello world"'

    def test_numeric_value(self):
        assert _format_value(42) == "42"


# ── KeyValueFormatter ─────────────────────────────────────────────────────────

class TestKeyValueFormatter:
    def test_basic_format(self):
        formatter = KeyValueFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="something happened",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "level=INFO" in output
        assert 'msg="something happened"' in output

    def test_extras_included(self):
        formatter = KeyValueFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="event",
            args=None,
            exc_info=None,
        )
        record.stage = "pipeline"  # type: ignore[attr-defined]
        record.outcome = "stored"  # type: ignore[attr-defined]

        output = formatter.format(record)
        assert "stage=pipeline" in output
        assert "outcome=stored" in output

    def test_none_extras_excluded(self):
        formatter = KeyValueFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="event",
            args=None,
            exc_info=None,
        )
        record.event_id = None  # type: ignore[attr-defined]

        output = formatter.format(record)
        assert "event_id=" not in output


# ── event_log_context ─────────────────────────────────────────────────────────

class TestEventLogContext:
    def test_returns_expected_keys(self):
        event = AIEvent(
            system="test-system",
            event_type="ai-event",
            user_input="q",
            context="c",
            output="o",
            raw_meta={
                "session_id": "s1",
                "time_stamp": "2026-01-01",
                "kafka": {"topic": "t", "partition": 1, "offset": 2},
            },
        )
        ctx = event_log_context(event, "evt-123")

        assert ctx["event_id"] == "evt-123"
        assert ctx["system"] == "test-system"
        assert ctx["event_type"] == "ai-event"
        assert ctx["session_id"] == "s1"
        assert ctx["time_stamp"] == "2026-01-01"
        assert ctx["topic"] == "t"
        assert ctx["partition"] == 1
        assert ctx["offset"] == 2

    def test_missing_kafka(self):
        event = AIEvent(
            system="s", event_type="e",
            user_input="q", context="c", output="o",
            raw_meta={},
        )
        ctx = event_log_context(event)
        assert ctx["event_id"] is None
        assert ctx["topic"] is None
