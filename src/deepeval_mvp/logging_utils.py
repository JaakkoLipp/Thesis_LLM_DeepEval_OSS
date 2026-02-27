from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Guards against calling configure_logging() more than once in the same
# process (e.g. tests that import main, or libraries with their own root
# handler already attached at import time).
_logging_configured: bool = False

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
        result = f"{base} {' '.join(extras)}" if extras else base
        # Append traceback when exc_info=True was passed to the log call.
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            result = result + "\n" + record.exc_text
        return result


def _format_value(value: Any) -> str:
    text = str(value)
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()

    # Only add a StreamHandler if nothing is already writing to stderr/stdout
    # (avoids duplicate lines when a framework like uvicorn already owns it).
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(KeyValueFormatter())
        root.addHandler(handler)

    root.setLevel(level)

    error_log_dir = os.getenv("ERROR_LOG_DIR", "logs")
    if error_log_dir:
        log_path = Path(error_log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        max_bytes = int(os.getenv("ERROR_LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB
        backup_count = int(os.getenv("ERROR_LOG_BACKUP_COUNT", "5"))
        file_handler = RotatingFileHandler(
            log_path / "errors.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.ERROR)
        file_handler.setFormatter(KeyValueFormatter())
        root.addHandler(file_handler)


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
