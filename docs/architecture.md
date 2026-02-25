# Architecture

This project is designed around a single processing contract:

incoming message → AIEvent → filter → claim → evaluate → persist

The important constraint is source isolation:

- get_message.py owns input-source handling and parsing
- service.py and pipeline.py do not care whether data came from fixture files or Kafka

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

### 1) Ingestion boundary

Module: src/deepeval_mvp/get_message.py

Responsibilities:

- Enumerate incoming messages through iter_incoming_messages(...)
- Convert raw bytes/envelopes to AIEvent using parse_incoming_event(...)
- Keep source-specific logic inside this module

Current source modes:

- MESSAGE_SOURCE=fixture (implemented)
- MESSAGE_SOURCE=kafka (placeholder boundary present)

### 2) Orchestration layer

Module: src/deepeval_mvp/service.py

Responsibilities:

- Pull messages from get_message iterator
- Parse each message to AIEvent
- Apply filtering (should_evaluate) as the single authority — before any DB interaction
- Perform idempotent claim in Mongo
- Run pipeline evaluation and write status transitions
- Apply STORE_ONLY_FAILS gate after evaluation (read once at startup, not per-event)
- Handle and persist all parse/pipeline/store errors via broad `except Exception`
- Install SIGTERM handler (threading.Event) for graceful in-flight finish before exit

Not responsible for:

- Fixture paths
- Kafka consumer details
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

### 6) Persistence

Module: src/deepeval_mvp/store_mongo.py

Responsibilities:

- Compute deterministic event IDs (kafka:topic:partition:offset when usable, payload hash otherwise)
- Claim events atomically via $setOnInsert upsert
- Store done/skipped/error status
- Persist payload and evaluation details
- Payload config (STORE_FULL_CONTEXT, CONTEXT_STORE_MAX_CHARS) read once at construction
- No ping at construction — preflight.py is the sole authoritative ping
- release_claim deletes the document for STORE_ONLY_FAILS successful-pass events

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
- Perform the single authoritative MongoDB ping (store_mongo does not ping)

## Data contracts

### IncomingMessage

Produced by get_message iterator and consumed by service:

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
- STORE_ONLY_FAILS: successful evaluations release the claim (delete the document) so only failures remain in MongoDB
- Stage-aware logging separates parse, filter, pipeline, and store failures
- All errors caught with `except Exception` — includes tenacity.RetryError from deepeval retry exhaustion

## Why this supports Kafka swap

Kafka integration only requires implementing the kafka branch in get_message.py so that it yields IncomingMessage with the same contract. service.py, pipeline.py, filtering.py, eval.py, and store_mongo.py remain unchanged.
