# Features

Comprehensive feature reference for DeepEval_MVP — a service that evaluates LLM
output quality using configurable metrics, backed by the
[DeepEval](https://github.com/confident-ai/deepeval) framework and local Ollama
judge models.

---

## Table of Contents

- [LLM Output Evaluation](#llm-output-evaluation)
- [Evaluation Metrics](#evaluation-metrics)
- [Judge LLM Integration](#judge-llm-integration)
- [Event Filtering](#event-filtering)
- [Claim-First Idempotent Processing](#claim-first-idempotent-processing)
- [Protocol-Driven Architecture](#protocol-driven-architecture)
- [Multiple Storage Backends](#multiple-storage-backends)
- [Pluggable Message Ingestion](#pluggable-message-ingestion)
- [Graceful Shutdown](#graceful-shutdown)
- [Preflight Validation](#preflight-validation)
- [Structured Logging](#structured-logging)
- [Rotating Error Log Files](#rotating-error-log-files)
- [Metric Retry with Exponential Back-off](#metric-retry-with-exponential-back-off)
- [Store-Only-Fails Mode](#store-only-fails-mode)
- [Live Streaming Judge Output](#live-streaming-judge-output)
- [Judge System Prompt Injection](#judge-system-prompt-injection)
- [Response Sanitisation](#response-sanitisation)
- [Context Truncation](#context-truncation)
- [Configurable Worker Identity](#configurable-worker-identity)
- [Evaluation Versioning](#evaluation-versioning)
- [File-Based Output (No Database)](#file-based-output-no-database)
- [Docker Support](#docker-support)
- [Comprehensive Test Suite](#comprehensive-test-suite)
- [Task Runner Aliases](#task-runner-aliases)
- [Typed Environment Helpers](#typed-environment-helpers)
- [Static Analysis and Linting](#static-analysis-and-linting)

---

## LLM Output Evaluation

The core purpose of the service: given a user input, retrieval context, and LLM
output, run a battery of quality metrics to produce a structured pass/fail
evaluation result.

- Each incoming event is converted to a DeepEval `LLMTestCase` and measured
  against every enabled metric.
- Results include per-metric score, threshold, pass/fail, and optional
  human-readable reason text.
- An overall `success` flag is `True` only when every metric passes its
  configured threshold.

## Evaluation Metrics

Six evaluation metrics are available, individually toggleable via the
`ENABLED_METRICS` environment variable.  Each metric has its own configurable
threshold (0–1).

| Metric | Type | Default Threshold | What It Measures |
|---|---|---|---|
| **Faithfulness** | DeepEval built-in | 0.7 | Whether the output is grounded in the provided retrieval context |
| **Answer Relevancy** | DeepEval built-in | 0.7 | Whether the answer directly addresses the user's question |
| **Contextual Relevancy** | DeepEval built-in | 0.7 | Whether the retrieved context is relevant to the question |
| **Completeness** | GEval (custom) | 0.7 | Whether the output addresses all explicit requirements from the input |
| **Informativeness** | GEval (custom) | 0.7 | Whether the output provides specific, useful information rather than vague filler |
| **Prompt Alignment** | DeepEval built-in | 0.7 | Whether the output follows a set of explicit prompt instructions (opt-in via `ENABLE_PROMPT_ALIGNMENT`) |

### Key behaviours

- Metrics are built fresh per evaluation — `measure()` mutates instance state,
  so metrics are never reused across events.
- Async mode is explicitly controlled (`METRIC_ASYNC_MODE`, default `false`) to
  prevent deepeval from spawning asyncio internals that cause timeout cascades
  on synchronous workers.
- `PromptAlignmentMetric` has its own separate `PROMPT_ALIGNMENT_ASYNC_MODE` flag.
- Each metric's `include_reason` flag is independently configurable.

## Judge LLM Integration

The evaluation judge is a local Ollama model.

- **Configurable model**: set via `JUDGE_MODEL` (e.g. `gemma3:4b`).
- **Temperature control**: `JUDGE_TEMPERATURE` (default `0.0`).
- **Custom base URL**: `LOCAL_MODEL_BASE_URL` for non-default Ollama endpoints.
- **Cached judge instance**: the judge model is constructed once and reused
  across events via `@lru_cache(maxsize=1)` — safe because it is stateless.
- **Dynamic class construction**: the `SanitizingJudge` class is built at
  runtime via `_build_sanitizing_model_class()`, mixing in DeepEval's
  `OllamaModel` without importing `deepeval` at module load time.  This keeps
  the module importable in lightweight environments where `deepeval` is not
  installed.

## Event Filtering

Events are filtered **before** any database interaction or expensive LLM calls.

- **System filter**: `ALLOWED_SYSTEMS` — comma-separated list of system names
  to evaluate (default: `enterprise-rag-chatbot,test-system`).
- **Event type filter**: `ALLOWED_EVENT_TYPES` — comma-separated list of event
  types (default: `ai-event`).
- Events not matching both lists are logged as `filter-skipped` and never
  claimed in the store.
- Filters are lazy — they read the environment at call time, so they can be
  reconfigured between calls without a restart.
- Filtering is the service layer's responsibility and is the **single source of
  truth**; the pipeline layer never re-checks.

## Claim-First Idempotent Processing

Duplicate and concurrent processing of the same event is prevented by an
atomic claim mechanism.

1. A deterministic `event_id` is computed for each event:
   - `kafka:<topic>:<partition>:<offset>` when Kafka metadata is available.
   - SHA-256 payload hash otherwise.
2. `ResultStore.claim_event` performs an atomic upsert (`$setOnInsert` in
   MongoDB) with `status=processing`.
3. If the claim succeeds, this worker owns the event and proceeds to evaluation.
4. If the claim fails (already claimed), the event is logged as a duplicate and
   skipped — no expensive LLM evaluation is performed.
5. On parse failure before an `AIEvent` is available, a fallback ingest ID
   (`ingest:<sha256>`) is derived from the raw message bytes so errors are
   still persisted and deduplicated.

## Protocol-Driven Architecture

The service layer depends on **Python Protocol interfaces**, not concrete
implementations.  This enables swapping I/O boundaries without modifying
business logic.

| Boundary | Protocol | Methods |
|---|---|---|
| **Input** | `MessageSource` | `iter_messages()`, `parse_event()` |
| **Storage** | `ResultStore` | `claim_event()`, `release_claim()`, `mark_done()`, `mark_error()` |

- `service.py` and `pipeline.py` import only the protocols.
- MVP implementations (`FixtureMessageSource`, `MongoResultStore`) are
  injected via constructor defaults.
- Production forks supply alternative implementations (e.g. Kafka, CosmosDB)
  through dependency injection in `run_service(store=..., message_source=...)`.
- The preflight database ping is also injectable (`db_ping` callable).

## Multiple Storage Backends

Three storage backends are available out of the box:

### MongoDB (`MongoResultStore`)

The default persistence layer, backed by `pymongo`.

- Atomic claim via `$setOnInsert` upsert.
- Configurable collection name (`MONGO_COLLECTION`).
- Payload truncation (`STORE_FULL_CONTEXT`, `CONTEXT_STORE_MAX_CHARS`).
- Optional index creation at construction (`MONGO_ENSURE_INDEXES`).
- Supports both `MONGO_URI`/`MONGO_DB` and `MONGODB_URI`/`MONGODB_DB` env var
  naming conventions.

### File-based output (`FileResultStore`)

For local development, demos, or CI runs where a database is unnecessary.

- Activated by `OUTPUT_TO_FILE=1`.
- Writes one human-readable `.txt` file per event in `OUTPUT_DIR` (default
  `output/`).
- Duplicate detection via file existence on disk.
- Implements the full `ResultStore` protocol — fully transparent to the rest
  of the pipeline.

### Custom backends

Any class implementing the `ResultStore` protocol can be passed to
`run_service(store=...)`.  The architecture guide includes a full
`CosmosDBResultStore` example.

## Pluggable Message Ingestion

### Fixture files (MVP)

`FixtureMessageSource` reads mock Kafka-style messages from `.txt` fixture
files in a configurable directory (`MESSAGE_FIXTURE_DIR`, default
`tests/fixtures`).

### Kafka (production fork boundary)

The `MessageSource` protocol and `IncomingMessage` TypedDict are designed for
Kafka-envelope messages.  A production fork supplies a `KafkaMessageSource`
class — no changes to service, pipeline, or evaluation code required.

### Custom sources

Any class implementing `iter_messages()` and `parse_event()` satisfies the
`MessageSource` protocol and can be injected via
`run_service(message_source=...)`.

## Graceful Shutdown

The service installs SIGTERM and SIGINT handlers via `threading.Event`.

- On signal receipt, the `_stop_requested` flag is set.
- The service loop checks the flag **between** messages, allowing any in-flight
  evaluation to complete before exiting.
- Signal handlers are restored after `run_service()` returns — important for
  tests that call the function multiple times.

## Preflight Validation

Before the service loop starts, a comprehensive preflight check runs:

1. **Required environment variables**: `MONGO_URI`/`MONGODB_URI`,
   `MONGO_DB`/`MONGODB_DB`, `JUDGE_MODEL`.
2. **Configuration coherence**: `ENABLE_PROMPT_ALIGNMENT=1` requires
   `PROMPT_INSTRUCTIONS` to be non-empty.
3. **Dependency availability**: verifies `deepeval` is importable.
4. **Database connectivity**: pings the database via an injectable `db_ping`
   callable (defaults to `pymongo` ping; production fork passes its own health
   check).

On any failure, the service exits with a non-zero code before starting the
loop.

## Structured Logging

All log output uses a structured key=value format for machine parseability.

```
2026-02-13 12:00:00,123 level=INFO msg="event stored" run_mode=service event_id=kafka:topic:1:42 ...
```

### Standard log fields

`run_mode`, `event_id`, `system`, `event_type`, `session_id`, `time_stamp`,
`topic`, `partition`, `offset`, `stage`, `outcome`, `duration_ms`,
`error_type`, `error_message`.

### Stage-aware logging

Each processing step is tagged with a `stage` field (`ingest`, `parse`,
`filter`, `pipeline`, `store`, `preflight`) for targeted log analysis.

### Human-readable evaluation results

When `PRINT_EVAL_RESULTS=true` (default), a formatted metric summary is logged
via `get_logger("eval_results")` after each evaluation.  Set to `false` in
production to rely on structured logs and database records only.

## Rotating Error Log Files

Error-level log entries are written to rotating log files in addition to
stderr.

- **Directory**: `ERROR_LOG_DIR` (default `logs`; set empty to disable).
- **Max file size**: `ERROR_LOG_MAX_BYTES` (default 5 MB).
- **Backup count**: `ERROR_LOG_BACKUP_COUNT` (default 5 rotated files).
- Uses the same `KeyValueFormatter` as console output.

## Metric Retry with Exponential Back-off

Individual metric evaluations can be retried on failure.

- `EVAL_RETRIES`: number of retry attempts per metric (default `0` — no retry).
- `EVAL_RETRY_BACKOFF_MS`: initial back-off in milliseconds (default `200`);
  doubles with each subsequent attempt.
- Back-off formula: `EVAL_RETRY_BACKOFF_MS × 2^attempt` ms.
- After all retries are exhausted, the original exception propagates and is
  persisted as an error record.

## Store-Only-Fails Mode

When `STORE_ONLY_FAILS=true`, only **failed** evaluations are persisted.

- Successful evaluations release their claim (`release_claim` deletes the
  document), so only failures remain in the database for review.
- The flag is read once at service startup — not per-event — for consistent
  behaviour within a run.
- Useful for high-volume environments where only anomalies need investigation.

## Live Streaming Judge Output

When `STREAM_EVAL_OUTPUT=true`, LLM judge tokens are streamed to stderr in
real time.

- Provides live visibility into what the judge model is producing.
- Automatically enabled by the `poe demo` task.
- Streaming uses the Ollama chat API in streaming mode.

## Judge System Prompt Injection

An optional system-level instruction can be injected before every judge LLM
call.

- **Inline**: `JUDGE_SYSTEM_PROMPT` — a single-line instruction in `.env`.
- **File-based**: `JUDGE_SYSTEM_PROMPT_FILE` — path to a plain-text file
  (takes priority over inline).
- Use cases: suppress markdown code fences, enforce JSON-only output format,
  add domain constraints.
- When neither is set, no system message is sent (default Ollama behaviour).
- The `a_generate` async path warns loudly if a system prompt is configured
  but cannot be injected.

## Response Sanitisation

The `_SanitizingOllamaModel` cleans raw LLM responses before Pydantic JSON
validation:

- Strips markdown code fences (`` ```json ... ``` ``).
- Replaces Unicode non-breaking spaces (U+00A0) with regular spaces.
- Applied defensively regardless of whether a system prompt discourages fence
  usage — model compliance is not guaranteed.

## Context Truncation

Retrieval context is truncated to prevent excessively large prompts:

- `MAX_CONTEXT_CHARS`: max characters passed to `LLMTestCase` (default `4000`).
- `CONTEXT_STORE_MAX_CHARS`: max context characters stored in the database when
  `STORE_FULL_CONTEXT=false` (default `4000`).
- `STORE_FULL_CONTEXT`: when `true`, stores the complete context string.

## Configurable Worker Identity

Each worker generates a unique owner ID used in claim records for
concurrency tracking.

- **Explicit**: `OWNER_ID` environment variable.
- **Auto-derived** (when `OWNER_ID` is not set):
  `<hostname>:<pid>:<8-hex-chars>`.
- **Kubernetes-aware**: when `POD_NAME` is set, it replaces hostname in the
  derived identity.

## Evaluation Versioning

Every evaluation result includes an `eval_version` field.

- Set via `EVAL_VERSION` environment variable.
- Stamped in every result dict and persisted to the store.
- Enables tracking which version of the evaluation configuration produced
  each result.

## File-Based Output (No Database)

For scenarios where MongoDB is unavailable or unnecessary:

```bash
OUTPUT_TO_FILE=1        # enable file-based output
OUTPUT_DIR=output       # optional, defaults to <repo_root>/output
```

- Each processed event produces a human-readable `.txt` file.
- Files are named after the event ID (sanitised for filesystem safety).
- The `output/` directory is git-ignored by default.
- Fully implements the `ResultStore` protocol — transparent to all other code.

## Docker Support

The project includes a `Dockerfile` for containerised deployment.

```bash
docker build -t deepeval-mvp:latest .
docker run --rm --env-file .env deepeval-mvp:latest
```

## Comprehensive Test Suite

Tests are split into three tiers:

| Tier | Marker | External Dependencies | Command |
|---|---|---|---|
| **Unit** | *(default)* | None | `uv run poe test` |
| **Integration** | `@pytest.mark.integration` | None (mocked eval) | `uv run poe test-integration` |
| **System** | `@pytest.mark.system` | Real Ollama judge backend | `uv run poe test-system` |

### Coverage

- 15+ test modules covering every source module.
- Shared `conftest.py` with `FakeMongoResultStore` (in-memory fake with
  `ImportError` fallback).
- Coverage reporting via `uv run poe test-cov`.

### What is tested

- Environment variable parsing (parametrized edge cases)
- Preflight validation (missing vars, coherence, connectivity)
- Event filtering logic
- Evaluation function contract (mocked judge and metrics)
- Pipeline delegation
- Full service flow including SIGTERM, `STORE_ONLY_FAILS`, duplicate handling
- MongoDB store idempotency, payload truncation, status transitions
- Fixture message iteration and parsing
- CLI argument parsing and dotenv loading
- `_SanitizingOllamaModel` generate/a_generate, system prompt injection, streaming
- Metric retry behaviour and exponential back-off timing
- Owner ID resolution (hostname, POD_NAME, explicit)
- Deterministic event ID computation
- Structured logging format and context helpers
- Evaluation result formatting

## Task Runner Aliases

[Poe the Poet](https://poethepoet.naber.io/) task aliases for common
operations:

| Command | Purpose |
|---|---|
| `uv run poe service` | Start the service |
| `uv run poe test` | Unit tests (fast, no external calls) |
| `uv run poe test-v` | Unit tests verbose with stdout |
| `uv run poe test-cov` | Unit tests with coverage report |
| `uv run poe test-integration` | Integration dry-run tests |
| `uv run poe test-system` | System tests against real judge backend |
| `uv run poe test-all` | All tests including system |
| `uv run poe demo-dry` | Dry-run demo with stubbed pipeline |
| `uv run poe demo` | Live demo with real judge (streaming enabled) |
| `uv run poe lint` | Run ruff linter |
| `uv run poe lint-fix` | Auto-fix ruff lint issues |

## Typed Environment Helpers

The `env_utils` module provides a single source of truth for typed environment
variable access:

- `env_bool(name, default)` — consistent truthy-string handling (`"1"`,
  `"true"`, `"yes"`, `"y"`, `"on"`).
- `env_float(name, default)` — float parsing with default.
- `env_int(name, default)` — integer parsing with default.
- `env_csv(name, default)` — comma-separated list parsing.

All modules import from `env_utils` — no copy-pasted env parsing anywhere in
the codebase.

## Static Analysis and Linting

- **Ruff**: linter and formatter targeting Python 3.12, with rules for
  pycodestyle, pyflakes, isort, pyupgrade, flake8-bugbear, flake8-simplify, and
  ruff-specific checks.
- **mypy**: strict type checking with `disallow_untyped_defs`,
  `warn_return_any`, `warn_unused_configs`.
- **py.typed marker**: the package ships a `py.typed` file for PEP 561
  compliance, enabling downstream type checking.
