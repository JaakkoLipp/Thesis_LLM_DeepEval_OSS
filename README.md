# DeepEval MVP (Thesis OSS Snapshot)

This repository is an open-source snapshot of an Engineering Master’s thesis project that evaluates LLM outputs from **event-shaped inputs** (e.g., RAG chatbot traces). Internal/production details (Kafka wiring, enterprise schemas, etc.) are intentionally omitted or stubbed.

Core processing contract:

`incoming message → AIEvent → filter → claim (idempotency) → evaluate (DeepEval) → persist (MongoDB)`


## What it does

- **Ingests** messages from a pluggable source (MVP: **fixture files**; Kafka adapter is a stub).
- **Parses** each message into a normalized `AIEvent` containing:
  - `system`, `event_type`
  - `user_input`, `retrieval context`, `model output`
  - optional Kafka envelope metadata (`topic/partition/offset`)
- **Filters** events early using allowlists (`ALLOWED_SYSTEMS`, `ALLOWED_EVENT_TYPES`).
- **Claims** events in the result store before expensive evaluation (**claim-first** semantics).
  - Prevents duplicate work across restarts / multiple instances.
- **Evaluates** eligible events using **DeepEval** metrics with an Ollama-backed judge model.
- **Stores** results + processing status in MongoDB (or other store via protocol).

> Not intended for production. This repo focuses on architecture, logging, error handling, and testability for thesis purposes.


## Quickstart (local)

### 1) Prerequisites

- Python **3.13+**
- `uv` (recommended): https://github.com/astral-sh/uv
- A MongoDB instance (local Docker MongoDB is fine — or use file output mode)
- An Ollama endpoint reachable from where you run this service (local or remote)

### 2) Interactive setup (not tested!)

The setup script installs dependencies, walks you through every config flag,
generates a `.env` file, and runs preflight validation:

```bash
chmod +x setup.sh && ./setup.sh
```

It supports both **MongoDB** and **file-output** storage modes, so you can
start testing without any database infrastructure.

### 3) Manual setup (alternative)

```bash
uv sync
cp sample_.env_file .env   # then edit .env to taste
```

Minimum required variables:

- `JUDGE_MODEL`
- `MONGO_URI` (or `MONGODB_URI`) — not needed if `OUTPUT_TO_FILE=1`
- `MONGO_DB` (or `MONGODB_DB`) — not needed if `OUTPUT_TO_FILE=1`

### 4) Run (fixture mode)

```bash
uv run python -m deepeval_mvp.main
# or:
uv run poe service
```

Optional flags:

```bash
uv run python -m deepeval_mvp.main --poll-seconds 1.0 --max-cycles 1
```


## Docker (minimal)

Build:

```bash
docker build -t deepeval-mvp:latest .
```

Run (reads your `.env`):

```bash
docker run --rm --env-file .env deepeval-mvp:latest
```


## Message sources

Runtime input is selected by `MESSAGE_SOURCE`:

- `fixture` (default): reads `*.txt` files from `MESSAGE_FIXTURE_DIR` (default `tests/fixtures`)
- `kafka`: **not implemented** in OSS snapshot; the protocol exists so a production fork can supply it

Fixtures can be either:
- raw JSON payloads, or
- a KafkaMessage(...) wrapper containing `value=b'''{json}'''` plus optional `topic/partition/offset` fields.

See: `src/deepeval_mvp/get_message.py`


## Result storage

The service writes evaluation results to MongoDB via `MongoResultStore` (`src/deepeval_mvp/store_mongo.py`).

Alternatively, set `OUTPUT_TO_FILE=1` to use `FileResultStore` (`src/deepeval_mvp/store_file.py`),
which writes files to `OUTPUT_DIR` (default `output/`) — useful for local development,
demos, or CI runs where a database is unnecessary.

Output format is controlled by `OUTPUT_FILE_FORMAT`:

- `text` (default): human-readable `.txt` files
- `json`: structured `.json` files

### Idempotency and event IDs

Event IDs are deterministic:

1) Prefer `kafka:{topic}:{partition}:{offset}` when present and usable  
2) Otherwise fall back to a SHA-256 hash derived from payload metadata + (user_input, output)

Events are **claimed** with an upsert (`$setOnInsert`) before evaluation:

- If the document already exists → treated as a duplicate and skipped
- If inserted → evaluation proceeds and the document is marked `done` (or `error`)

This pattern allows safe horizontal scaling in later deployments.

### Collections and schema (high level)

The default collection name is `evaluation_results`. Documents contain:

- `_id`: event id
- `status`: `processing | done | error`
- `owner_id`, timestamps (`claimed_at`, `started_at`, `finished_at`, `last_updated_at`)
- `meta`: system, event_type, session_id, time_stamp, etc.
- `payload`: user_input/output (+ context optionally, see `STORE_FULL_CONTEXT`)
- `evaluation`: per-metric results and overall `success`

See: `docs/architecture.md` and `src/deepeval_mvp/store_mongo.py`


## Evaluation metrics

Enabled metrics are controlled via `ENABLED_METRICS` (comma-separated). Defaults target common RAG-quality checks:

- `faithfulness`
- `answer_relevancy`
- `contextual_relevancy`
- `completeness`
- `informativeness`
- optional: `prompt_alignment` (gated by `ENABLE_PROMPT_ALIGNMENT=true`)

Thresholds are configurable per metric (e.g. `THRESHOLD_FAITHFULNESS=0.7`).

The judge model runs through Ollama. The service can inject a system prompt into judge calls via
`JUDGE_SYSTEM_PROMPT` or `JUDGE_SYSTEM_PROMPT_FILE`.

See: `src/deepeval_mvp/eval.py`


## Logging and error handling

- Structured logs in **key=value** format to stdout/stderr
- Optional rotating error file log: `logs/errors.log` (configurable)
- Per-event error boundaries so one bad message does not stop the service loop
- Preflight checks on startup validate:
  - required env vars
  - DeepEval is importable
  - database connectivity (ping)
  - PromptAlignment config coherence

See: `docs/logging.md` and `src/deepeval_mvp/preflight.py`


## Testing

Test suite is split into:
- unit tests (fast, deterministic)
- integration tests (dry-run service/eval flow; no external LLM calls)
- system tests (real judge backend; environment-dependent)

Common commands:

```bash
uv run poe test              # unit tests (fast, no external calls)
uv run poe test-v            # unit tests verbose with stdout
uv run poe test-cov          # unit tests with coverage report
uv run poe test-integration  # integration dry-run (mocked eval)
uv run poe test-system       # system tests against real judge
uv run poe test-all          # all tests including system
uv run poe demo-dry          # dry-run demo with stubbed pipeline
uv run poe demo              # live demo with real judge (streaming)
uv run poe lint              # run ruff linter
uv run poe lint-fix          # auto-fix ruff lint issues
```

See: `docs/testing.md`


## Configuration reference (selected)

### Required
- `JUDGE_MODEL` — Ollama model name used as judge (e.g. `qwen3:8b`)
- `MONGO_URI` / `MONGODB_URI`
- `MONGO_DB` / `MONGODB_DB`

### Common
- `LOCAL_MODEL_BASE_URL` — Ollama base URL (used by DeepEval OllamaModel)
- `MESSAGE_SOURCE` — `fixture` (default)
- `MESSAGE_FIXTURE_DIR` — directory containing `*.txt` fixture messages
- `ALLOWED_SYSTEMS`, `ALLOWED_EVENT_TYPES` — filtering allowlists
- `ENABLED_METRICS` — enabled DeepEval metrics
- `EVAL_RETRIES`, `EVAL_RETRY_BACKOFF_MS` — app-level retry around evaluation
- `METRIC_ASYNC_MODE` — toggles DeepEval internal async mode
- `STORE_ONLY_FAILS` — if enabled, only failed evals are persisted (successful ones release the claim)
- `OUTPUT_TO_FILE` — use file-based output instead of MongoDB
- `OUTPUT_FILE_FORMAT` — when `OUTPUT_TO_FILE=1`, choose `text` (default) or `json`
- `STREAM_EVAL_OUTPUT` — stream judge tokens to stderr in real time
- `JUDGE_TEMPERATURE` — LLM sampling temperature (default 0.0)
- `EVAL_VERSION` — version label stamped in every result
- `OWNER_ID`, `POD_NAME` — worker identity for claim records
- `ERROR_LOG_DIR`, `LOG_LEVEL`

For a full list, see `docs/usage.md` or search for `os.getenv(` and `env_*(` in `src/deepeval_mvp/`.


## Repository layout

- `src/deepeval_mvp/` — service, protocols, evaluation, storage
- `tests/` — unit/integration/system tests + fixture samples
- `docs/` — architecture, features, flowcharts, UML, logging, usage, testing, changing I/O
- `output/` — optional demo output artifacts (if enabled)


## Thesis & contact

- Thesis publication search (LUTPub): https://lutpub.lut.fi/discover?scope=%2F&query=Jaakko+Lipponen&submit=
- Project site: http://jaalip.com/

---

_Last updated: 2026-02-27_
