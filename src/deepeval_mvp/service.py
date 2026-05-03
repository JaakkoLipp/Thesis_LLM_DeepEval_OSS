from __future__ import annotations

import hashlib
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from typing import Any, Literal

from deepeval_mvp.env_utils import env_bool
from deepeval_mvp.filtering import should_evaluate
from deepeval_mvp.logging_utils import event_log_context, get_logger
from deepeval_mvp.message_protocol import IncomingMessage, MessageSource
from deepeval_mvp.models import AIEvent
from deepeval_mvp.pipeline import process_event
from deepeval_mvp.store_protocol import ResultStore

# ── Graceful-shutdown flag ────────────────────────────────────────────────────
# Set by both SIGTERM and SIGINT handlers; checked between messages in the loop.
_stop_requested = threading.Event()


def _install_signal_handlers() -> tuple[Any, Any]:
    """Install SIGTERM and SIGINT handlers that request graceful shutdown.

    Both signals set the same flag so the in-flight message finishes before
    the process exits.  Returns ``(prev_sigterm, prev_sigint)`` for later
    restoration — important for tests that call run_service multiple times.
    """
    def _handler(signum: int, frame: Any) -> None:
        _stop_requested.set()
        # Re-raise as KeyboardInterrupt so long-running API calls (e.g.
        # OpenAI client retry loops) are interrupted immediately instead
        # of blocking until all retries are exhausted.
        raise KeyboardInterrupt

    prev_sigterm = signal.signal(signal.SIGTERM, _handler)
    prev_sigint = signal.signal(signal.SIGINT, _handler)
    return prev_sigterm, prev_sigint


def _restore_signal_handlers(prev_sigterm: Any, prev_sigint: Any) -> None:
    signal.signal(signal.SIGTERM, prev_sigterm)
    signal.signal(signal.SIGINT, prev_sigint)


def _fallback_error_id(message: IncomingMessage) -> str:
    source_id = str(message.get("source_id", ""))
    raw = message.get("raw", b"")
    raw_bytes = bytes(raw) if isinstance(raw, (bytes, bytearray)) else repr(raw).encode("utf-8")
    digest = hashlib.sha256(source_id.encode("utf-8") + b"|" + raw_bytes).hexdigest()
    return f"ingest:{digest}"


def process_incoming_event(
    event: AIEvent,
    store: ResultStore,
    owner_id: str,
    run_mode: str = "service",
    store_only_fails: bool = False,
) -> Literal["stored", "skipped", "error"]:
    """Process a single parsed event through filter → claim → evaluate → store."""
    started = time.monotonic()
    event_id: str | None = None
    stage = "claim"
    logger = get_logger(run_mode)

    try:
        # ── Filter ────────────────────────────────────────────────────────────
        # Checked here, before any DB interaction.  pipeline.process_event is a
        # pure evaluator and does NOT re-check; this is the single source of truth.
        if not should_evaluate(event.system, event.event_type):
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "event skipped",
                extra={
                    **event_log_context(event, None),
                    "stage": "filter",
                    "outcome": "skipped",
                    "duration_ms": duration_ms,
                },
            )
            return "skipped"

        # ── Claim (idempotency guard) ─────────────────────────────────────────
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

        # ── Evaluate ──────────────────────────────────────────────────────────
        stage = "pipeline"
        result = process_event(event)

        # ── STORE_ONLY_FAILS gate ─────────────────────────────────────────────
        # When enabled, only failed evaluations are persisted for review.
        # Successful results release the claim so no document remains in the DB.
        # The flag is read once at run_service startup, not per-event.
        stage = "store"
        if store_only_fails and result.get("success"):
            store.release_claim(event_id)
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "event skipped (store_only_fails)",
                extra={
                    **ctx,
                    "stage": "store",
                    "outcome": "skipped",
                    "duration_ms": duration_ms,
                },
            )
            return "skipped"

        # ── Persist ───────────────────────────────────────────────────────────
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

    except Exception as exc:
        # Release the DB claim so no dangling record remains; errors are
        # only written to logs/errors.log and printed to the terminal.
        if event_id is not None:
            store.release_claim(event_id)
        else:
            event_id = f"event:{hashlib.sha256(repr(event).encode('utf-8')).hexdigest()}"
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
    store: ResultStore,
    owner_id: str,
    run_mode: str = "service",
    store_only_fails: bool = False,
    *,
    message_source: MessageSource | None = None,
) -> Literal["stored", "skipped", "error"]:
    """Parse a raw IncomingMessage then hand off to process_incoming_event."""
    started = time.monotonic()
    logger = get_logger(run_mode)

    try:
        if message_source is not None:
            event = message_source.parse_event(message)
        else:
            from deepeval_mvp.get_message import parse_incoming_event
            event = parse_incoming_event(message)
        return process_incoming_event(
            event,
            store=store,
            owner_id=owner_id,
            run_mode=run_mode,
            store_only_fails=store_only_fails,
        )
    except Exception as exc:
        event_id = _fallback_error_id(message)
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


def _format_results(results: dict[str, Any]) -> str:
    """Format evaluation results as a human-readable string."""
    lines = ["=== Evaluation Results ==="]
    for metric in results["metrics"]:
        lines.append(f"\n[{metric['name']}]")
        lines.append(f"  score      : {metric['score']}")
        lines.append(f"  threshold  : {metric['threshold']}")
        lines.append(f"  success    : {metric['success']}")
        lines.append(f"  reason     : {metric['reason']}")
        if metric.get("error"):
            lines.append(f"  error      : {metric['error']}")
    lines.append(f"\nOverall success: {results['success']}")
    return "\n".join(lines)


def _print_results(results: dict[str, Any]) -> None:
    """Log human-readable evaluation results.

    Gated by ``PRINT_EVAL_RESULTS`` (default ``1``).  Set to ``0`` in
    container/production environments where structured logs and MongoDB storage
    are sufficient and stdout noise is undesirable.
    """
    if not env_bool("PRINT_EVAL_RESULTS", True):
        return
    logger = get_logger("eval_results")
    logger.info("\n%s", _format_results(results))


def _default_store() -> ResultStore:
    """Lazy import of the MVP's concrete store.

    When ``OUTPUT_TO_FILE`` is truthy the :class:`FileResultStore` is used
    instead of MongoDB, writing evaluation results to files in the directory
    specified by ``OUTPUT_DIR`` (default ``output/``).
    ``OUTPUT_FILE_FORMAT`` controls text (default) vs JSON output.

    The production fork should replace this with its CosmosDB store factory
    and pass a ``ResultStore``-conforming instance to ``run_service(store=...)``.
    """
    if env_bool("OUTPUT_TO_FILE", False):
        from deepeval_mvp.store_file import FileResultStore
        return FileResultStore()
    from deepeval_mvp.store_mongo import MongoResultStore
    return MongoResultStore()


def _default_message_source() -> MessageSource:
    """Lazy import of the MVP's fixture-based message source.

    The production fork should replace this with its Kafka adapter
    and pass a ``MessageSource``-conforming instance to ``run_service(message_source=...)``.
    """
    from deepeval_mvp.get_message import FixtureMessageSource
    return FixtureMessageSource()


def run_service(
    poll_seconds: float = 5.0,
    max_cycles: int | None = None,
    *,
    store: ResultStore | None = None,
    message_source: MessageSource | None = None,
) -> int:
    """Main service loop.

    Accepts optional ``store`` and ``message_source`` for dependency injection.
    When omitted, uses the MVP defaults (``MongoResultStore`` and
    ``FixtureMessageSource``).  The production fork can supply its Kafka and
    CosmosDB implementations without modifying this module.

    Reads ``STORE_ONLY_FAILS`` once at startup (not per-event) and passes it
    down the call stack.  Installs a SIGTERM handler for graceful shutdown so
    the in-flight message finishes before the process exits.
    """
    _stop_requested.clear()
    prev_sigterm, prev_sigint = _install_signal_handlers()

    owner_id = resolve_owner_id()
    logger = get_logger("service")
    if store is None:
        store = _default_store()
    if message_source is None:
        message_source = _default_message_source()
    store_only_fails = env_bool("STORE_ONLY_FAILS", False)

    try:
        for message in message_source.iter_messages(poll_seconds=poll_seconds, max_cycles=max_cycles):
            if _stop_requested.is_set():
                logger.info(
                    "shutdown requested",
                    extra={"stage": "service", "outcome": "stopped"},
                )
                break
            process_message(
                message,
                store=store,
                owner_id=owner_id,
                run_mode="service",
                store_only_fails=store_only_fails,
                message_source=message_source,
            )
        return 0
    except KeyboardInterrupt:
        logger.info(
            "shutdown requested",
            extra={"stage": "service", "outcome": "stopped"},
        )
        return 0
    except Exception as exc:
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
    finally:
        _restore_signal_handlers(prev_sigterm, prev_sigint)


def resolve_owner_id() -> str:
    explicit_owner = os.getenv("OWNER_ID")
    if explicit_owner:
        return explicit_owner

    pod_name = os.getenv("POD_NAME")
    host = pod_name or os.getenv("HOSTNAME") or socket.gethostname()
    return f"{host}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


