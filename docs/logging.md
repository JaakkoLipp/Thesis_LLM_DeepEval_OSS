# Logging and Error Handling

This document describes the production-grade logging and error-handling behavior for DeepEval_MVP.

## Overview

The service emits structured logs (key=value format) and persists processing status and errors to MongoDB. Logging is configured once at startup in [src/deepeval_mvp/main.py](../src/deepeval_mvp/main.py), and service mode shares the same log schema as demo-related test flows.

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
- stage: parse, filter, evaluate, store, or preflight
- outcome: stored, skipped, or error
- duration_ms: elapsed time for the event processing step
- error_type, error_message: populated on error

## Configuration

- LOG_LEVEL: logging level (default: INFO). Options: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- EVAL_RETRIES: number of retries for evaluation failures (default: 0). Any non-negative integer.
- EVAL_RETRY_BACKOFF_MS: backoff per retry (default: 200). Any integer milliseconds (e.g., 100, 500, 1000).
- ERROR_TRACEBACK_MAX_CHARS: max length for persisted traceback (default: 2000). Any positive integer.

## Startup Preflight

At startup, the service performs a preflight check and exits non-zero on failure:

- Loads .env from repo root explicitly.
- Validates required environment variables: MONGO_URI, MONGO_DB, JUDGE_MODEL.
- Verifies MongoDB connectivity via ping.
- Verifies deepeval is installed.

Preflight results are logged with stage=preflight and outcome=stored or error.

## Error Handling and Persistence

### Service Loop

In service mode, each fixture file is processed in an isolated try/except block so a single bad input cannot crash the loop. Errors are logged with full context and the loop continues.

### MongoDB Status Fields

Each event is persisted to the same collection with status tracking:

- status: processing, done, skipped, or error
- claimed_at: set when processing begins
- stored_at: set on completion or skip
- error: {type, message}

A processing marker is written before evaluation. After evaluation, the record is updated to done or skipped. On exceptions, the record is updated to error.

### Idempotency and Restart Safety

The event ID is computed by:

1) kafka:topic:partition:offset when usable, else
2) a payload-derived hash

This allows claim-first deduplication and skipping already-processed events across restarts.

## Demo vs Service Behavior

- Demo-style test flows still print evaluation results to stdout, and also emit structured logs.
- Service mode logs summaries while retaining concise progress prints.
