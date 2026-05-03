# Changing Input and Storage

This guide explains how to replace the MVP's input source (fixture files) and
result store (MongoDB) with production implementations (Kafka + CosmosDB) without
modifying the service, pipeline, evaluation, or filtering code.

## Why this works

The service layer never imports concrete I/O classes directly. It depends on two
Python Protocol interfaces:

| Boundary | Protocol | MVP implementation | Production replacement |
|---|---|---|---|
| Input | `MessageSource` | `FixtureMessageSource` (fixture files) | Kafka consumer adapter |
| Storage | `ResultStore` | `MongoResultStore` (pymongo) | CosmosDB adapter |

Both protocols live in the `deepeval_mvp` package and are importable:

```python
from deepeval_mvp import MessageSource, ResultStore, AIEvent, IncomingMessage
```

## What to implement

### 1. Kafka message source

Create a class that satisfies the `MessageSource` protocol:

```python
from deepeval_mvp import MessageSource, IncomingMessage, AIEvent

class KafkaMessageSource:
    def __init__(self, broker: str, topic: str, group_id: str):
        # set up your Kafka consumer here
        ...

    def iter_messages(
        self,
        poll_seconds: float = 5.0,
        max_cycles: int | None = None,
    ) -> Iterator[IncomingMessage]:
        """Yield IncomingMessage dicts from Kafka.

        Each dict MUST contain 'raw' (bytes). Optionally include:
        - 'kafka': {"topic": ..., "partition": ..., "offset": ...}
        - 'source_id': a human-readable fallback identifier
        """
        for msg in self.consumer.poll(...):
            yield {
                "raw": msg.value,
                "kafka": {
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                },
                "source_id": f"{msg.topic}:{msg.partition}:{msg.offset}",
            }

    def parse_event(self, message: IncomingMessage) -> AIEvent:
        """Convert a raw Kafka message to an AIEvent.

        Must return an AIEvent with all 6 fields populated:
        system, event_type, user_input, context, output, raw_meta
        """
        payload = json.loads(message["raw"])
        return AIEvent(
            system=payload["system"],
            event_type=payload["event_type"],
            user_input=str(payload["event_data"]["request"]),
            context=str(payload.get("retrieval_context", {}).get("output", "")),
            output=str(payload["event_data"]["response"]["output"]),
            raw_meta={...},  # include kafka envelope, session_id, etc.
        )
```

### 2. CosmosDB result store

Create a class that satisfies the `ResultStore` protocol:

```python
from deepeval_mvp import ResultStore, AIEvent

class CosmosDBResultStore:
    def __init__(self, connection_string: str, database: str, container: str):
        # set up your CosmosDB client here
        ...

    def claim_event(self, event: AIEvent, owner_id: str) -> tuple[str, bool]:
        """Atomically claim an event for processing.

        Returns (event_id, was_claimed):
        - event_id: a deterministic string ID for this event
        - was_claimed: True if this worker now owns it, False if already claimed

        The service uses this for idempotency — duplicate events are skipped
        without running the expensive LLM evaluation again.
        """
        event_id = self._compute_id(event)
        # Use a conditional write / upsert to claim atomically
        ...
        return event_id, was_claimed

    def release_claim(self, event_id: str) -> None:
        """Remove the claim document (used when STORE_ONLY_FAILS skips a success)."""
        ...

    def mark_done(self, event_id: str, event: AIEvent, evaluation: dict) -> None:
        """Persist a completed evaluation result.

        'evaluation' is the dict returned by eval_function(). It contains:
        - 'success': bool (overall pass/fail)
        - 'metrics': list of {name, score, threshold, success, reason, error}
        - 'eval_version': str or None
        """
        ...

    def mark_error(
        self,
        event_id: str,
        error_type: str,
        error_message: str,
        *,
        event: AIEvent | None = None,
        traceback_text: str | None = None,
    ) -> None:
        """Persist an error record when processing fails."""
        ...
```

### 3. Preflight health check

The preflight step pings the database before the service starts. Pass your own
check instead of the default pymongo ping:

```python
def cosmos_health_check(uri: str) -> None:
    """Raise on failure; return None on success."""
    client = CosmosClient(uri)
    client.get_database_client("your-db").read()  # or any lightweight call
```

## Wiring it up

In your production fork's `main.py`:

```python
from deepeval_mvp.preflight import run_preflight
from deepeval_mvp.service import run_service
from deepeval_mvp.logging_utils import configure_logging, get_logger

from your_kafka_adapter import KafkaMessageSource
from your_cosmos_store import CosmosDBResultStore, cosmos_health_check

configure_logging()
logger = get_logger("startup")

if not run_preflight(logger, db_ping=cosmos_health_check):
    sys.exit(1)

source = KafkaMessageSource(broker="...", topic="...", group_id="...")
store = CosmosDBResultStore(connection_string="...", database="...", container="...")

run_service(
    poll_seconds=5.0,
    store=store,
    message_source=source,
)
```

That's it. `run_service` accepts both via keyword arguments and uses them
throughout the processing loop. No other files need changes.

## Data contracts to honour

### IncomingMessage (TypedDict)

| Field | Type | Required | Purpose |
|---|---|---|---|
| `raw` | `bytes` | yes | The raw message payload |
| `kafka` | `dict[str, Any]` | no | Broker envelope: topic, partition, offset |
| `source_id` | `str` | no | Human-readable ID for diagnostics and fallback error IDs |

### AIEvent (frozen dataclass)

| Field | Type | Purpose |
|---|---|---|
| `system` | `str` | Source system name (used by filtering) |
| `event_type` | `str` | Event type (used by filtering) |
| `user_input` | `str` | The user's question / prompt |
| `context` | `str` | Retrieved context provided to the LLM |
| `output` | `str` | The LLM's response |
| `raw_meta` | `dict[str, Any]` | Non-business metadata (kafka envelope, session_id, timestamps, etc.) |

### Evaluation result dict (passed to mark_done)

```python
{
    "success": True,           # overall pass/fail
    "eval_version": "1.2.3",   # from EVAL_VERSION env var, or None
    "metrics": [
        {
            "name": "Faithfulness",
            "score": 0.85,
            "threshold": 0.7,
            "success": True,
            "reason": "...",
            "error": None,
        },
        ...
    ]
}
```

## What stays the same

These modules are **not touched** when swapping input/storage:

- `service.py` — orchestration (depends on protocols only)
- `pipeline.py` — evaluation bridge
- `eval.py` — LLM judge and metrics
- `filtering.py` — system/event_type filter
- `models.py` — AIEvent dataclass
- `env_utils.py` — typed env var helpers
- `logging_utils.py` — structured logging
- `message_protocol.py` — MessageSource protocol definition
- `store_protocol.py` — ResultStore protocol definition

## Built-in file output (no database)

For local development, demos, or CI runs you can skip the database entirely
and write evaluation results to individual text files:

```bash
OUTPUT_TO_FILE=1        # enable file-based output
OUTPUT_DIR=output       # optional, defaults to <repo_root>/output
OUTPUT_FILE_FORMAT=text # optional: text (default) or json
```

When `OUTPUT_TO_FILE=1`, the service creates a `FileResultStore` (defined in
`store_file.py`) instead of `MongoResultStore`. Each processed event produces
one output file named after its event ID in the output directory (`.txt` for
`text`, `.json` for `json`).

- The `output/` folder is git-ignored by default.
- All `ResultStore` protocol methods (`claim_event`, `release_claim`,
  `mark_done`, `mark_error`) are implemented, so the switch is fully
  transparent to the rest of the pipeline.
- Duplicate detection uses file existence on disk.

## What can be deleted

In the production fork, these MVP-only files can be safely removed:

- `get_message.py` — fixture file reader (replaced by your Kafka adapter)
- `store_mongo.py` — pymongo storage (replaced by your CosmosDB adapter)
- `tests/test_get_message.py` — tests for the fixture reader
- `tests/test_store_mongo.py` — tests for the MongoDB store
- `tests/test_event_id.py` — tests for MongoDB's event ID logic
- `tests/fixtures/` — sample fixture files

The shared test infrastructure (`conftest.py`, `FakeMongoResultStore`) has an
`ImportError` fallback so it continues to work even after `store_mongo.py` is
deleted — it falls back to a simple hash for event IDs.

## Testing your new implementations

Write tests for your Kafka and CosmosDB classes that verify:

1. `iter_messages` yields valid `IncomingMessage` dicts with `raw` as bytes
2. `parse_event` returns a fully populated `AIEvent`
3. `claim_event` returns `(str, True)` on first call, `(str, False)` on duplicate
4. `mark_done` persists and is retrievable
5. `mark_error` persists error details
6. `release_claim` removes the document

The existing `test_service.py` tests will pass unchanged because they use the
in-memory `FakeMongoResultStore` from `conftest.py`, not the real store.
