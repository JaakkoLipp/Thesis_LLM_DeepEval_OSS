# Running and Configuration

## Service mode

Start the service:

- uv run python -m deepeval_mvp.main

Optional CLI arguments:

- --poll-seconds FLOAT (default 5.0)
- --max-cycles INT (default None; useful for local/demo bounded runs)

Example bounded run:

- uv run python -m deepeval_mvp.main --poll-seconds 1.0 --max-cycles 1

## How runtime input is selected

Input mode is selected by environment variable MESSAGE_SOURCE:

- fixture: implemented, reads mock Kafka-style fixture messages
- kafka: contract exists; adapter implementation pending

When using fixture mode, the source directory is configured by MESSAGE_FIXTURE_DIR.

Defaults:

- MESSAGE_SOURCE=fixture
- MESSAGE_FIXTURE_DIR=tests/fixtures

## Detailed runtime behavior

At startup, main.py does the following in order:

1. Load .env
2. Configure logging
3. Run preflight checks
4. Start service loop

During service execution:

1. service.run_service asks get_message.iter_incoming_messages for the next message
2. service.process_message calls get_message.parse_incoming_event
3. service.process_incoming_event claims event ownership in Mongo
4. pipeline.process_event applies filtering and evaluation
5. store writes done/skipped/error status

The service and pipeline layers are source-agnostic.

## Environment variables

### Input selection

- MESSAGE_SOURCE: fixture or kafka
- MESSAGE_FIXTURE_DIR: path to fixture directory when MESSAGE_SOURCE=fixture

### Evaluation

- JUDGE_MODEL
- ENABLED_METRICS
- THRESHOLD_FAITHFULNESS
- THRESHOLD_ANSWER_RELEVANCY
- THRESHOLD_CONTEXTUAL_RELEVANCY
- THRESHOLD_COMPLETENESS
- THRESHOLD_INFORMATIVENESS
- ENABLE_PROMPT_ALIGNMENT and related PROMPT_ALIGNMENT_* settings
- MAX_CONTEXT_CHARS
- JUDGE_TEMPERATURE

### Filtering

- ALLOWED_SYSTEMS
- ALLOWED_EVENT_TYPES

### Storage

- MONGO_URI or MONGODB_URI
- MONGO_DB or MONGODB_DB
- MONGO_COLLECTION or MONGODB_COLLECTION
- STORE_FULL_CONTEXT
- CONTEXT_STORE_MAX_CHARS

### Logging and retry/error behavior

- LOG_LEVEL
- EVAL_RETRIES
- EVAL_RETRY_BACKOFF_MS
- ERROR_TRACEBACK_MAX_CHARS

## Common task aliases

- uv run poe service
- uv run poe test
- uv run poe test-integration
- uv run poe test-system
- uv run poe demo-dry
- uv run poe demo
