# Architecture

This project is designed around a single processing contract:

incoming message → AIEvent → filter → claim → evaluate → persist

The important constraint is **boundary isolation**:

- get_message.py owns input-source handling and parsing (MVP: fixture files)
- store_mongo.py owns result persistence (MVP: MongoDB)
- service.py and pipeline.py **depend only on protocols** (`MessageSource`, `ResultStore`), not on concrete implementations

The production fork replaces the I/O boundaries (Kafka input, CosmosDB output)
by supplying different protocol implementations — **no service-layer code changes required**.

Related artifacts:

- [Flowcharts](./flowcharts.md)
- [UML Design Artifacts](./uml.md)

## Layered design

### 0) Configuration helpers

Module: src/deepeval_mvp/env_utils.py

Responsibilities:

- Single source of truth for reading typed values from environment variables
- Provides env_bool, env_float, env_int, env_csv
- Consistent truthy-string handling across all modules ("1", "true", "yes", "y", "on")
- All other modules import from here; no copy-pasted env parsing anywhere else

### 1) Ingestion boundary (protocol + MVP implementation)

Protocol: src/deepeval_mvp/message_protocol.py

Defines the `MessageSource` protocol and the canonical `IncomingMessage` TypedDict.
Any class that implements `iter_messages()` and `parse_event()` satisfies this contract.

MVP implementation: src/deepeval_mvp/get_message.py

Provides `FixtureMessageSource` (reads fixture `.txt` files) and the underlying
free-function API (`iter_incoming_messages`, `parse_incoming_event`).

Responsibilities:

- Enumerate incoming messages through iter_messages(...)
- Convert raw bytes/envelopes to AIEvent using parse_event(...)
- Keep source-specific logic inside this module

Current source modes:

- MESSAGE_SOURCE=fixture (implemented via FixtureMessageSource)
- MESSAGE_SOURCE=kafka (placeholder boundary present — production fork implements KafkaMessageSource)

Production fork: Replace with a `KafkaMessageSource` class that satisfies the
`MessageSource` protocol and pass it to `run_service(message_source=...)`.

### 2) Orchestration layer

Module: src/deepeval_mvp/service.py

Responsibilities:

- Pull messages from `MessageSource.iter_messages` (protocol, not concrete)
- Parse each message to AIEvent via `MessageSource.parse_event`
- Apply filtering (should_evaluate) as the single authority — before any DB interaction
- Perform idempotent claim via `ResultStore.claim_event` (protocol, not concrete)
- Run pipeline evaluation and write status transitions
- Apply STORE_ONLY_FAILS gate after evaluation (read once at startup, not per-event)
- Handle and persist all parse/pipeline/store errors via broad `except Exception`
- Install SIGTERM/SIGINT handlers (threading.Event) for graceful in-flight finish before exit
- Accept `store` and `message_source` via dependency injection in `run_service()`
- Falls back to `_default_store()` (MongoResultStore) and `_default_message_source()` (FixtureMessageSource) when not injected
- Logs evaluation results via `_format_results` (structured logging, not print())

Not responsible for:

- Fixture paths
- Kafka consumer details
- Database driver specifics (pymongo, CosmosDB SDK, etc.)
- Metric internals
- Re-running the filter (filtering is not in the pipeline layer)

### 3) Business pipeline

Module: src/deepeval_mvp/pipeline.py

Responsibilities:

- Run evaluation via eval_function(...)
- Return evaluation result dict

This layer is a pure evaluator. Filtering is handled upstream by the service layer
before process_event is called. process_event never returns None.

### 4) Filtering

Module: src/deepeval_mvp/filtering.py

Responsibilities:

- Expose allowed_systems() and allowed_event_types() as lazy functions (read env at call time)
- Expose should_evaluate(system, event_type) as the single filter predicate
- No module-level constants; reconfigurable between calls without restart

### 5) Evaluation engine

Module: src/deepeval_mvp/eval.py

Responsibilities:

- `_SanitizingOllamaModel` is a module-level class (not a nested closure) that handles
  system prompt injection, streaming, and JSON fence cleaning for the judge LLM
- Config is passed via `__init__` (base_url, temperature, system_prompt, stream flag)
- `a_generate` warns when a system prompt would be silently dropped (async path)
- Cache the judge (OllamaModel) via @lru_cache(maxsize=1) — safe because the judge is
  stateless; reusing it across events avoids repeated model init overhead
- Build fresh metric instances per evaluation call — metrics are stateful after measure()
  and must not be reused across events
- Execute the configured subset of DeepEval metrics (controlled by ENABLED_METRICS)
- Run each metric through _run_metric with optional exponential back-off retry
  (EVAL_RETRIES, EVAL_RETRY_BACKOFF_MS)
- Pass async_mode to all metrics explicitly (METRIC_ASYNC_MODE, default false) to prevent
  deepeval from invoking asyncio internally, which causes timeout cascades on sync workers
- PromptAlignmentMetric uses a separate PROMPT_ALIGNMENT_ASYNC_MODE flag
- Raise RuntimeError eagerly if ENABLE_PROMPT_ALIGNMENT=1 but PROMPT_INSTRUCTIONS is empty
- Inject an optional system prompt into every judge LLM call before deepeval's user prompt
  (JUDGE_SYSTEM_PROMPT for an inline string, JUDGE_SYSTEM_PROMPT_FILE for a plain-text file).
  Useful for suppressing markdown code fences, enforcing output format, or adding domain
  constraints. _clean still strips fences defensively regardless of whether a prompt is set.
  _call_ollama is the unified Ollama client method used when streaming or a system prompt is
  configured; otherwise super().generate() is called unchanged (zero behavioural difference).
- Stream LLM tokens to stderr in real time (STREAM_EVAL_OUTPUT, default false) for live demo
  visibility. Enabled automatically by the `poe demo` task.
- Stamps `eval_version` (from EVAL_VERSION env var) in every evaluation result dict

### 6) Persistence (protocol + MVP implementation)

Protocol: src/deepeval_mvp/store_protocol.py

Defines the `ResultStore` protocol with methods: `claim_event`, `release_claim`,
`mark_done`, `mark_error`.  Any class implementing these satisfies the contract.

MVP implementation: src/deepeval_mvp/store_mongo.py

Provides `MongoResultStore` backed by pymongo.

Responsibilities:

- Compute deterministic event IDs (kafka:topic:partition:offset when usable, payload hash otherwise)
- Claim events atomically via $setOnInsert upsert
- Store done/skipped/error status with `eval_version` stamp
- Persist payload and evaluation details
- Payload config (STORE_FULL_CONTEXT, CONTEXT_STORE_MAX_CHARS) read once at construction
- Index creation guarded by MONGO_ENSURE_INDEXES env var
- No ping at construction — preflight.py is the sole authoritative ping
- release_claim deletes the document for STORE_ONLY_FAILS successful-pass events

Production fork: Replace with a `CosmosDBResultStore` class that satisfies the
`ResultStore` protocol and pass it to `run_service(store=...)`.

### 7) Startup and lifecycle

Module: src/deepeval_mvp/main.py

Responsibilities:

- Parse CLI args (--poll-seconds, --max-cycles)
- Load .env from repo root
- Configure logging
- Run preflight checks (exit non-zero on failure)
- Start service loop

Module: src/deepeval_mvp/preflight.py

Responsibilities:

- Validate required env vars (MONGO_URI, MONGO_DB, JUDGE_MODEL)
- Check ENABLE_PROMPT_ALIGNMENT + PROMPT_INSTRUCTIONS coherence
- Verify deepeval is installed
- Perform the single authoritative database ping via an injectable `db_ping` callable
  (defaults to pymongo MongoClient ping; production fork passes CosmosDB health check)

## Data contracts

### IncomingMessage

Defined in message_protocol.py. Produced by MessageSource and consumed by service:

- raw: bytes (required)
- kafka: dict (optional envelope overrides)
- source_id: str (optional source identifier for diagnostics/fallback IDs)

### AIEvent

Core internal event model (models.py):

- system
- event_type
- user_input
- context
- output
- raw_meta (includes non-business metadata, including kafka envelope when available)

## Error and idempotency model

- Parse failure before AIEvent creation: service writes mark_error using deterministic fallback ingest ID (sha256 of source_id + raw bytes)
- Claim-first flow prevents duplicate expensive evaluation
- STORE_ONLY_FAILS: successful evaluations release the claim (delete the document) so only failures remain in the database
- Stage-aware logging separates parse, filter, pipeline, and store failures
- All errors caught with `except Exception` — includes tenacity.RetryError from deepeval retry exhaustion

## Production fork: what to replace

The system is designed so only the I/O boundaries need replacing:

| Component | MVP | Production fork | Contract |
|---|---|---|---|
| Message source | `FixtureMessageSource` (fixture files) | `KafkaMessageSource` (Kafka consumer) | `MessageSource` protocol |
| Result store | `MongoResultStore` (pymongo/MongoDB) | `CosmosDBResultStore` (CosmosDB SDK) | `ResultStore` protocol |
| Preflight ping | `_default_db_ping` (pymongo ping) | Custom `db_ping` callable | `Callable[[str], None]` |

**Nothing else changes.** service.py, pipeline.py, eval.py, filtering.py, models.py,
env_utils.py, logging_utils.py, and main.py remain untouched.

### Dependency injection entry points

```python
# Production fork main.py example:
from your_kafka_adapter import KafkaMessageSource
from your_cosmos_store import CosmosDBResultStore

source = KafkaMessageSource(broker="...", topic="...")
store = CosmosDBResultStore(connection_string="...")

run_service(
    poll_seconds=5.0,
    store=store,
    message_source=source,
)
```

Preflight:
```python
from your_cosmos_store import cosmos_health_check

run_preflight(logger, db_ping=cosmos_health_check)
```
