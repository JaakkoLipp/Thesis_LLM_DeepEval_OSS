from __future__ import annotations

import logging
import os
from typing import Any

_LOG_FIELDS = [
    "run_mode",
    "event_id",
    "system",
    "event_type",
    "session_id",
    "time_stamp",
    "topic",
    "partition",
    "offset",
    "stage",
    "outcome",
    "duration_ms",
    "error_type",
    "error_message",
]


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = _format_value(record.getMessage())
        base = f"{self.formatTime(record)} level={record.levelname} msg={msg}"
        extras = []
        for key in _LOG_FIELDS:
            if hasattr(record, key):
                value = getattr(record, key)
                if value is None:
                    continue
                extras.append(f"{key}={_format_value(value)}")
        if extras:
            return f"{base} {' '.join(extras)}"
        return base


def _format_value(value: Any) -> str:
    text = str(value)
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(KeyValueFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(run_mode: str) -> logging.LoggerAdapter:
    base = logging.getLogger("deepeval_mvp")
    return logging.LoggerAdapter(base, {"run_mode": run_mode})


def event_log_context(event: Any, event_id: str | None = None) -> dict[str, Any]:
    meta = getattr(event, "raw_meta", {}) or {}
    kafka = meta.get("kafka") or {}
    return {
        "event_id": event_id,
        "system": getattr(event, "system", ""),
        "event_type": getattr(event, "event_type", ""),
        "session_id": meta.get("session_id", ""),
        "time_stamp": meta.get("time_stamp", ""),
        "topic": kafka.get("topic"),
        "partition": kafka.get("partition"),
        "offset": kafka.get("offset"),
    }
