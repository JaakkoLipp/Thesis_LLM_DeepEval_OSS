# Logging and Error Handling

This document describes the production-grade logging and error-handling behavior for DeepEval_MVP.

## Overview

The service emits structured logs (key=value format) and persists processing status and errors to the result store. Logging is configured at runtime startup in main.py, and the same schema is used across service, integration, and demo-style flows.

## Log Format

Logs use a key=value format intended for easy parsing.

Example:

```
2026-02-13 12:00:00,123 level=INFO msg="event stored" run_mode=service event_id=kafka:topic:1:42 system=enterprise-rag-chatbot event_type=ai-event session_id=abc time_stamp=2026-02-13T12:00:00Z topic=topic partition=1 offset=42 stage=store outcome=stored duration_ms=231
```

### Standard Fields

- run_mode: startup or service
- event_id: computed event identifier (kafka topic/partition/offset when available)
- system, event_type, session_id, time_stamp: from event metadata
- topic, partition, offset: Kafka envelope fields when present
- stage: ingest, parse, pipeline, filter, store, or preflight
- outcome: stored, skipped, or error
- duration_ms: elapsed time for the event processing step
- error_type, error_message: populated on error

## Configuration

- LOG_LEVEL: logging level (default: INFO). Options: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- PRINT_EVAL_RESULTS: log human-readable metric results after each evaluation (default: true).
  Output goes through `get_logger("eval_results")`, not `print()`.
  Set false in container/production environments where structured logs and database storage are sufficient.
- EVAL_RETRIES: how many times to retry a failing metric call, with exponential back-off (default: 0).
  Back-off formula: EVAL_RETRY_BACKOFF_MS × 2^attempt milliseconds.
- EVAL_RETRY_BACKOFF_MS: initial retry back-off in milliseconds (default: 200).
- ERROR_TRACEBACK_MAX_CHARS: max length for persisted traceback strings (default: 2000).
- ERROR_LOG_DIR: directory for rotating file log output (default: logs). Set to empty string to disable file logging entirely.
- ERROR_LOG_MAX_BYTES: max bytes per log file before rotation (default: 5242880 = 5 MB).
- ERROR_LOG_BACKUP_COUNT: number of rotated backup log files to retain (default: 5).

## Startup Preflight

At startup, the service performs a preflight check and exits non-zero on failure:

- Loads .env from repo root.
- Validates required environment variables: MONGO_URI/MONGODB_URI, MONGO_DB/MONGODB_DB, JUDGE_MODEL.
- Checks ENABLE_PROMPT_ALIGNMENT + PROMPT_INSTRUCTIONS coherence: if ENABLE_PROMPT_ALIGNMENT=1 but PROMPT_INSTRUCTIONS is empty, preflight fails before any evaluation runs.
- Verifies deepeval is installed.
- Verifies MongoDB connectivity via ping (injectable `db_ping` callable — defaults to
  pymongo MongoClient ping; production fork passes CosmosDB health check).
  This is the only database ping in the service lifecycle — the store does not ping at construction.

Preflight results are logged with stage=preflight and outcome=stored or error.

## Error Handling and Persistence

### Service Loop

In service mode, each incoming message is processed in isolated error boundaries so one bad message does not crash the loop. Errors are logged with context and processing continues.

All errors are caught with `except Exception`, which includes:
- ValueError, TypeError, RuntimeError for configuration or data errors
- tenacity.RetryError from deepeval when LLM retry exhaustion occurs

Error split:

- message-level parse failure: logged and persisted with deterministic ingest fallback ID (sha256 of source_id + raw bytes)
- event-level processing failure: logged with event context and persisted as event error

### MongoDB Status Fields

Each event is persisted to the same collection with status tracking:

- status: processing, done, skipped, or error
- claimed_at: set when processing begins
- stored_at: set on completion, skip, or error
- error: {type, message}

A processing marker is written by claim_event before evaluation. After evaluation, the record is updated to done or skipped. On exceptions, the record is updated to error.

### Idempotency and Restart Safety

The event ID is computed by:

1) kafka:topic:partition:offset when usable, else
2) a payload-derived hash

This allows claim-first deduplication and skipping already-processed events across restarts.

## Demo vs Service Behavior

- Service prints metric summaries for evaluated events and logs structured status for all outcomes.
- Integration and system-style runs share the same logging schema.
