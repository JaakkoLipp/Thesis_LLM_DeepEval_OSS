# Architecture

This project is designed around a single processing contract:

incoming message -> AIEvent -> pipeline -> persistence

The important constraint is source isolation:

- get_message.py owns input-source handling and parsing
- service.py and pipeline.py do not care whether data came from fixture files or Kafka

Related artifacts:

- [Flowcharts](./flowcharts.md)
- [UML Design Artifacts](./uml.md)

## Layered design

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
- Perform idempotent claim in Mongo
- Run pipeline and write status transitions
- Handle and persist parse/runtime errors

Not responsible for:

- Fixture paths
- Kafka consumer details
- Metric internals

### 3) Business pipeline

Module: src/deepeval_mvp/pipeline.py

Responsibilities:

- Apply filtering via should_evaluate(...)
- Run evaluation via eval_function(...)
- Return either skipped or evaluation result

This layer is deterministic and source-agnostic.

### 4) Evaluation engine

Module: src/deepeval_mvp/eval.py

Responsibilities:

- Execute configured DeepEval metrics
- Return normalized metric/result payload

### 5) Persistence

Module: src/deepeval_mvp/store_mongo.py

Responsibilities:

- Compute event IDs
- Claim events atomically
- Store done/skipped/error status
- Persist payload and evaluation details

### 6) Startup and lifecycle

Module: src/deepeval_mvp/main.py

Responsibilities:

- Parse CLI args
- Load environment
- Configure logging
- Run preflight
- Start service loop

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

- Parse failure before AIEvent creation: service writes mark_error using deterministic fallback ingest ID
- Claim-first flow prevents duplicate expensive evaluation
- Stage-aware logging separates parse, pipeline, and store failures

## Why this supports Kafka swap

Kafka integration only requires implementing the kafka branch in get_message.py so that it yields IncomingMessage with the same contract. service.py, pipeline.py, eval.py, and store_mongo.py remain unchanged.
