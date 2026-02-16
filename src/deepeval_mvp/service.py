from __future__ import annotations

import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from deepeval_mvp.get_message import get_event
from deepeval_mvp.logging_utils import event_log_context, get_logger
from deepeval_mvp.pipeline import process_event
from deepeval_mvp.store_mongo import MongoResultStore


def process_fixture_file(
    fixture_path: Path,
    store: Any,
    owner_id: str,
    run_mode: str = "service",
) -> Literal["stored", "skipped", "error"]:
    started = time.monotonic()
    event_id: str | None = None
    logger = get_logger(run_mode)
    event = None

    try:
        event = get_event(str(fixture_path))
        event_id, claimed = store.claim_event(event, owner_id=owner_id)
        ctx = event_log_context(event, event_id)
        if not claimed:
            current_owner = store.get_owner(event_id)
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
            print(
                f"[{run_mode}] duplicate {fixture_path.name} already claimed as {event_id} by {current_owner}"
            )
            return "skipped"

        result = process_event(event)

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
            print(f"[{run_mode}] skipped {fixture_path.name}")
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
        print(f"[{run_mode}] stored {fixture_path.name} as {event_id} in {duration_ms}ms")
        return "stored"
    except Exception as exc:
        if event_id is not None:
            store.mark_error(event_id, type(exc).__name__, str(exc))
        duration_ms = int((time.monotonic() - started) * 1000)
        ctx = event_log_context(event, event_id) if event is not None else {"event_id": event_id}
        logger.error(
            "event processing error",
            extra={
                **ctx,
                "stage": "parse" if event is None else "evaluate",
                "outcome": "error",
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
            exc_info=True,
        )
        print(
            f"[{run_mode}] error {fixture_path.name} ({type(exc).__name__}) after {duration_ms}ms: {exc}"
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


def run_service(fixtures_dir: Path, poll_seconds: float = 5.0, max_cycles: int | None = None) -> int:
    """
    Temporary service mode: poll a directory for new fixture files and process them once.
    This simulates a consumer loop until Kafka integration exists.
    """
    owner_id = resolve_owner_id()
    logger = get_logger("service")
    seen: set[str] = set()
    store = MongoResultStore()
    cycles = 0

    while True:
        if not fixtures_dir.exists():
            logger.error(
                "fixtures dir not found",
                extra={
                    "stage": "parse",
                    "outcome": "error",
                    "error_message": str(fixtures_dir),
                },
            )
            print(f"[service] fixtures dir not found: {fixtures_dir}")
            return 1

        for f in sorted(fixtures_dir.glob("*.txt")):
            key = str(f.resolve())
            if key in seen:
                continue

            seen.add(key)
            process_fixture_file(f, store, owner_id=owner_id, run_mode="service")

        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            return 0

        time.sleep(max(poll_seconds, 0.0))


def resolve_owner_id() -> str:
    explicit_owner = os.getenv("OWNER_ID")
    if explicit_owner:
        return explicit_owner

    pod_name = os.getenv("POD_NAME")
    host = pod_name or os.getenv("HOSTNAME") or socket.gethostname()
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
