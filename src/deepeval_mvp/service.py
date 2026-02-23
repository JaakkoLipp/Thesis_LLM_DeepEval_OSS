from __future__ import annotations

import hashlib
import os
import socket
import time
import traceback
import uuid
from typing import Any, Literal

from deepeval_mvp.get_message import IncomingMessage
from deepeval_mvp.get_message import iter_incoming_messages
from deepeval_mvp.get_message import parse_incoming_event
from deepeval_mvp.logging_utils import event_log_context, get_logger
from deepeval_mvp.models import AIEvent
from deepeval_mvp.pipeline import process_event
from deepeval_mvp.store_mongo import MongoResultStore


def _fallback_error_id(message: IncomingMessage) -> str:
    source_id = str(message.get("source_id", ""))
    raw = message.get("raw", b"")
    raw_bytes = bytes(raw) if isinstance(raw, (bytes, bytearray)) else repr(raw).encode("utf-8")
    digest = hashlib.sha256(source_id.encode("utf-8") + b"|" + raw_bytes).hexdigest()
    return f"ingest:{digest}"


def process_incoming_event(
    event: AIEvent,
    store: Any,
    owner_id: str,
    run_mode: str = "service",
) -> Literal["stored", "skipped", "error"]:
    started = time.monotonic()
    event_id: str | None = None
    stage = "claim"
    logger = get_logger(run_mode)

    try:
        event_id, claimed = store.claim_event(event, owner_id=owner_id)
        ctx = event_log_context(event, event_id)

        if not claimed:
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "event duplicate",
                extra={
                    **ctx,
                    "stage": "store",
                    "outcome": "skipped",
                    "duration_ms": duration_ms,
                },
            )
            return "skipped"

        stage = "pipeline"
        result = process_event(event)

        stage = "store"
        if result is None:
            store.mark_skipped(event_id, event)
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "event skipped",
                extra={
                    **ctx,
                    "stage": "filter",
                    "outcome": "skipped",
                    "duration_ms": duration_ms,
                },
            )
            return "skipped"

        _print_results(result)
        store.mark_done(event_id, event, result)
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "event stored",
            extra={
                **ctx,
                "stage": "store",
                "outcome": "stored",
                "duration_ms": duration_ms,
            },
        )
        return "stored"
    except (ValueError, TypeError, RuntimeError, OSError, KeyError) as exc:
        if event_id is None:
            event_id = f"event:{hashlib.sha256(repr(event).encode('utf-8')).hexdigest()}"
        store.mark_error(event_id, event, type(exc).__name__, str(exc), traceback.format_exc())

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error(
            "event processing error",
            extra={
                **event_log_context(event, event_id),
                "stage": stage,
                "outcome": "error",
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return "error"


def process_message(
    message: IncomingMessage,
    store: Any,
    owner_id: str,
    run_mode: str = "service",
) -> Literal["stored", "skipped", "error"]:
    started = time.monotonic()
    logger = get_logger(run_mode)

    try:
        event = parse_incoming_event(message)
        return process_incoming_event(event, store=store, owner_id=owner_id, run_mode=run_mode)
    except (ValueError, TypeError, RuntimeError, OSError, KeyError) as exc:
        event_id = _fallback_error_id(message)
        store.mark_error(event_id, type(exc).__name__, str(exc))

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error(
            "message processing error",
            extra={
                "event_id": event_id,
                "stage": "parse",
                "outcome": "error",
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return "error"


def _print_results(results: dict[str, Any]) -> None:
    print("\n=== Evaluation Results ===")
    for metric in results["metrics"]:
        print(f"\n[{metric['name']}]")
        print(f"  score      : {metric['score']}")
        print(f"  threshold  : {metric['threshold']}")
        print(f"  success    : {metric['success']}")
        print(f"  reason     : {metric['reason']}")
        if metric.get("error"):
            print(f"  error      : {metric['error']}")
    print("\nOverall success:", results["success"])


def run_service(poll_seconds: float = 5.0, max_cycles: int | None = None) -> int:
    owner_id = resolve_owner_id()
    logger = get_logger("service")
    store = MongoResultStore()

    try:
        for message in iter_incoming_messages(poll_seconds=poll_seconds, max_cycles=max_cycles):
            process_message(message, store=store, owner_id=owner_id, run_mode="service")
        return 0
    except (ValueError, TypeError, RuntimeError, OSError, KeyError, NotImplementedError) as exc:
        logger.error(
            "service runtime error",
            extra={
                "stage": "ingest",
                "outcome": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        return 1


def resolve_owner_id() -> str:
    explicit_owner = os.getenv("OWNER_ID")
    if explicit_owner:
        return explicit_owner

    pod_name = os.getenv("POD_NAME")
    host = pod_name or os.getenv("HOSTNAME") or socket.gethostname()
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
