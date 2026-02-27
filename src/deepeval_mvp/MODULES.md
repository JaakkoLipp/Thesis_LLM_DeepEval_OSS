# Module Reference

| File | Purpose |
|---|---|
| `main.py` | CLI entry point — loads `.env`, configures logging, runs preflight, starts service loop |
| `service.py` | Orchestration layer — message loop, filtering, claim, evaluate, persist, graceful shutdown |
| `pipeline.py` | Thin bridge — calls `eval_function` and returns the result dict |
| `eval.py` | Evaluation engine — builds judge model, configures metrics, runs DeepEval, retries |
| `filtering.py` | Event filter — `should_evaluate()` predicate based on system/event_type allowlists |
| `models.py` | `AIEvent` frozen dataclass — the canonical internal event representation |
| `message_protocol.py` | `MessageSource` protocol + `IncomingMessage` TypedDict |
| `store_protocol.py` | `ResultStore` protocol (`claim_event`, `release_claim`, `mark_done`, `mark_error`) |
| `get_message.py` | MVP input — `FixtureMessageSource` reads `.txt` fixture files |
| `store_mongo.py` | MVP storage — `MongoResultStore` backed by pymongo, atomic claim via upsert |
| `store_file.py` | File storage — `FileResultStore` writes `.txt` results to disk (no database) |
| `preflight.py` | Startup validation — env vars, config coherence, deepeval import, DB ping |
| `env_utils.py` | Typed env helpers — `env_bool`, `env_float`, `env_int`, `env_csv` |
| `logging_utils.py` | Structured logging — `KeyValueFormatter`, rotating file handler, `event_log_context` |
