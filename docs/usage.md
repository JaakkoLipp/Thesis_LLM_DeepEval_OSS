# Running and Configuration

## Service mode

Start the service:

- uv run python -m deepeval_mvp.main
- uv run poe service

Optional CLI arguments:

- --poll-seconds FLOAT (default 5.0)
- --max-cycles INT (default None; useful for local/demo bounded runs)

Example bounded run:

- uv run python -m deepeval_mvp.main --poll-seconds 1.0 --max-cycles 1

## How runtime input is selected

Input mode is selected by environment variable MESSAGE_SOURCE:

- fixture: implemented, reads mock Kafka-style fixture messages from MESSAGE_FIXTURE_DIR
- kafka: contract exists; adapter implementation pending (production fork)

The service layer depends on the `MessageSource` protocol, not on a concrete module.
The MVP ships `FixtureMessageSource`; the production fork supplies a `KafkaMessageSource`.

Defaults:

- MESSAGE_SOURCE=fixture
- MESSAGE_FIXTURE_DIR=tests/fixtures

## Detailed runtime behavior

At startup, main.py does the following in order:

1. Load .env from repo root
2. Configure logging
3. Run preflight checks (exit non-zero on any failure)
4. Start service loop

Preflight checks:

- Required env vars present (MONGO_URI/MONGODB_URI, MONGO_DB/MONGODB_DB, JUDGE_MODEL)
- ENABLE_PROMPT_ALIGNMENT=1 implies PROMPT_INSTRUCTIONS is non-empty
- deepeval package importable
- Database reachable via injectable `db_ping` callable (defaults to pymongo ping;
  production fork passes its CosmosDB health check)

During service execution, per message:

1. service.run_service checks SIGTERM flag and exits cleanly if set
2. service.run_service asks MessageSource.iter_messages for the next message
3. service.process_message calls MessageSource.parse_event
4. service.process_incoming_event applies filtering (should_evaluate) — before any DB interaction
5. If filter passes, claims event ownership via ResultStore.claim_event (idempotency guard)
6. pipeline.process_event runs eval_function and returns evaluation dict
7. STORE_ONLY_FAILS gate: if enabled and evaluation passed, ResultStore.release_claim removes document
8. Otherwise store writes done/skipped/error status via ResultStore

## Environment variables

### Input selection

- MESSAGE_SOURCE: fixture or kafka (default: fixture)
- MESSAGE_FIXTURE_DIR: path to fixture directory when MESSAGE_SOURCE=fixture (default: tests/fixtures)

### Judge model

- JUDGE_MODEL: Ollama model name, e.g. gemma3:4b (required)
- LOCAL_MODEL_BASE_URL: base URL for the Ollama API, e.g. http://localhost:11434/ (optional; omit for default Ollama localhost)
- JUDGE_TEMPERATURE: LLM sampling temperature (default: 0.0)
- JUDGE_SYSTEM_PROMPT: inline system-level instruction injected before every judge LLM call (optional).
  Useful for suppressing markdown code fences, enforcing output format, or adding domain constraints.
  Example: `Respond with raw JSON only. Do not use markdown formatting or code blocks.`
- JUDGE_SYSTEM_PROMPT_FILE: path to a plain-text file containing the system prompt (optional).
  Takes priority over JUDGE_SYSTEM_PROMPT. Use for multi-line instructions.
  When neither is set, no system message is sent (default Ollama behaviour).

### Evaluation metrics

- ENABLED_METRICS: comma-separated list of metrics to run (default: faithfulness,answer_relevancy,contextual_relevancy,completeness,informativeness)
  Available: faithfulness, answer_relevancy, contextual_relevancy, completeness, informativeness
- THRESHOLD_FAITHFULNESS: pass/fail threshold 0–1 (default: 0.7)
- THRESHOLD_ANSWER_RELEVANCY: (default: 0.7)
- THRESHOLD_CONTEXTUAL_RELEVANCY: (default: 0.7)
- THRESHOLD_COMPLETENESS: (default: 0.7)
- THRESHOLD_INFORMATIVENESS: (default: 0.7)
- INCLUDE_REASON_FAITHFULNESS: include LLM reason text in result (default: true)
- INCLUDE_REASON_ANSWER_RELEVANCY: (default: true)
- INCLUDE_REASON_CONTEXTUAL_RELEVANCY: (default: true)
- MAX_CONTEXT_CHARS: max characters of context passed to LLMTestCase (default: 4000)
- METRIC_ASYNC_MODE: pass async_mode to deepeval metrics (default: false)
  Set false to make deepeval call the LLM judge synchronously. Set true only if all metrics
  are run inside an existing asyncio event loop. Incorrect use causes asyncio timeout cascades.

### Optional PromptAlignment metric (6th metric)

- ENABLE_PROMPT_ALIGNMENT: enable the PromptAlignmentMetric (default: false)
- PROMPT_INSTRUCTIONS: comma-separated instruction strings (required if ENABLE_PROMPT_ALIGNMENT=1)
- PROMPT_ALIGNMENT_THRESHOLD: (default: 0.7)
- PROMPT_ALIGNMENT_STRICT_MODE: (default: false)
- PROMPT_ALIGNMENT_INCLUDE_REASON: (default: true)
- PROMPT_ALIGNMENT_ASYNC_MODE: separate async_mode flag for this metric (default: false)
- PROMPT_ALIGNMENT_VERBOSE_MODE: (default: false)

### Filtering

- ALLOWED_SYSTEMS: comma-separated system names that should be evaluated (default: enterprise-rag-chatbot,test-system)
- ALLOWED_EVENT_TYPES: comma-separated event types (default: ai-event)
  Events not matching both lists are logged as filter-skipped and never claimed in the store.

### Storage

- MONGO_URI / MONGODB_URI: MongoDB connection string (required)
- MONGO_DB / MONGODB_DB: database name (required)
- MONGO_COLLECTION / MONGODB_COLLECTION: collection name (default: evaluation_results)
- STORE_FULL_CONTEXT: store full context string in payload (default: false)
- CONTEXT_STORE_MAX_CHARS: max context chars stored when STORE_FULL_CONTEXT=false (default: 4000)
- STORE_ONLY_FAILS: when true, delete the document for events that pass evaluation
  and only retain failures (default: false). Read once at service startup, not per-event.
- MONGO_ENSURE_INDEXES: when true, MongoResultStore creates indexes at construction (default: true).
  Set false in environments where index management is handled externally.
- EVAL_VERSION: version label stored in evaluation records (optional)

### Worker identity

- OWNER_ID: explicit owner ID for claim records (optional; auto-derived when not set)
  Auto-derived format: <hostname>:<pid>:<8-hex-chars>
  In Kubernetes: POD_NAME is used instead of hostname when set.
- POD_NAME: Kubernetes pod name (optional; used in owner ID derivation)

### Retry and timeout

- EVAL_RETRIES: number of retries per metric on failure, with exponential back-off (default: 0)
- EVAL_RETRY_BACKOFF_MS: initial back-off in milliseconds; doubles each retry (default: 200)
- DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE: deepeval internal — timeout per LLM call attempt
- DEEPEVAL_MAX_RETRIES: deepeval internal — number of LLM call retries inside deepeval

### Logging and error handling

- LOG_LEVEL: logging level (default: INFO). Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
- PRINT_EVAL_RESULTS: log human-readable metric results after each evaluation (default: true).
  Output goes through the logging system (`get_logger("eval_results")`), not `print()`.
  Set false in container/production environments where structured logs are sufficient.
- ERROR_TRACEBACK_MAX_CHARS: max characters for persisted traceback strings (default: 2000)
- ERROR_LOG_DIR: directory for rotating error log files (default: logs; set empty to disable)
- ERROR_LOG_MAX_BYTES: max size per log file before rotation (default: 5242880 = 5 MB)
- ERROR_LOG_BACKUP_COUNT: number of rotated log files to keep (default: 5)

## Common task aliases

- uv run poe service          — start the service
- uv run poe test             — unit tests (fast, no external calls)
- uv run poe test-v           — unit tests verbose with stdout
- uv run poe test-cov         — unit tests with coverage report
- uv run poe test-integration — integration dry-run tests (mocked eval)
- uv run poe test-system      — system tests against real judge backend
- uv run poe test-all         — all tests including system
- uv run poe demo-dry         — dry-run demo with stubbed pipeline
- uv run poe demo             — live demo run with real judge
- uv run poe lint             — run ruff linter and mypy type checks
- uv run poe lint-fix         — auto-fix ruff lint issues
