# docs/TESTING.md

Testing is split into **unit**, **integration (dry-run)**, and **system (wet-run)** tests.

## Commands (recommended)

Unit tests (fast, deterministic, no external LLM calls):

* `uv run poe test`
* `uv run poe test-v` (verbose, no output capture)

Integration tests (mocked dry-run of service/eval flow; no external LLM calls):

* `uv run poe test-integration`

System tests (real judge backend; slower; environment-dependent):

* `uv run poe test-system`
* `uv run poe demo` (live demo-style system run with progress printing)

Dry-run demo flow (same shape, mocked eval):

* `uv run poe demo-dry`

Coverage (unit tests only):

* `uv run poe test-cov`

Run everything:

* `uv run poe test-all` (runs all markers; system tests still require `JUDGE_MODEL`)

## Test coverage scope

Current test modules and what they cover:

- test_env_utils.py — env_bool, env_float, env_int, env_csv helpers (parametrized)
- test_preflight.py — required-var checks, PromptAlignment coherence, deepeval availability, db_ping
- test_filtering.py — allowed_systems/event_types lazy reads, should_evaluate logic
- test_eval_function.py — eval_function contract; judge and metrics are mocked
- test_pipeline.py — process_event delegates to eval_function correctly
- test_service.py — process_incoming_event, process_message, run_service incl. SIGTERM, STORE_ONLY_FAILS, PRINT_EVAL_RESULTS (logger-based)
- test_store_mongo.py — claim_event idempotency, mark_done/skipped/error, release_claim, payload truncation
- test_get_message.py — fixture iteration and parse contracts
- test_main.py — CLI arg parsing, dotenv loading, preflight gate
- test_integration_eval_real.py — real judge backend test (gated by RUN_SYSTEM=1)
- test_sanitizing_model.py — _SanitizingOllamaModel generate/a_generate, system prompt injection, streaming
- test_eval_retry.py — _run_metric retry behaviour and exponential back-off
- test_resolve_owner.py — resolve_owner_id hostname/POD_NAME/explicit owner derivation
- test_event_id.py — deterministic event ID computation (kafka ID, payload hash, edge cases)
- test_logging_utils.py — KeyValueFormatter, configure_logging, get_logger, event_log_context
- test_format_results.py — _format_results output shape

Shared test infrastructure:

- conftest.py — shared fixtures (sample_aievent, fixtures_dir, etc.) and FakeMongoResultStore
  (in-memory ResultStore fake with ImportError fallback for _compute_event_id)

## Recommended local test progression

1. Run unit tests first
2. Run integration marker tests
3. Run system tests only when model/backend is available

Suggested sequence:

- uv run poe test
- uv run poe test-integration
- uv run poe test-system

## Integration gating

Integration tests are dry-run and do not require model backend credentials.

## System gating

System tests require:

* `RUN_SYSTEM=1` (set by `test-system` and `demo` Poe tasks)
* `JUDGE_MODEL` (must be set)

System tests assert **result schema**, not exact scores.

## Targeted module validation examples

- uv run pytest -q tests/test_env_utils.py
- uv run pytest -q tests/test_preflight.py
- uv run pytest -q tests/test_get_message.py
- uv run pytest -q tests/test_filtering.py
- uv run pytest -q tests/test_eval_function.py
- uv run pytest -q tests/test_service.py
- uv run pytest -q tests/test_pipeline.py
- uv run pytest -q tests/test_store_mongo.py
- uv run pytest -q tests/test_main.py
- uv run pytest -q tests/test_sanitizing_model.py
- uv run pytest -q tests/test_eval_retry.py
- uv run pytest -q tests/test_resolve_owner.py
- uv run pytest -q tests/test_event_id.py
- uv run pytest -q tests/test_logging_utils.py
- uv run pytest -q tests/test_format_results.py

---

# docs/TROUBLESHOOTING.md

## System test is skipped

Common reasons:

* `RUN_SYSTEM!=1` → run `uv run poe test-system` or `uv run poe demo`
* `JUDGE_MODEL not set` → set `JUDGE_MODEL`

See skip reasons:

* `uv run pytest -q -m system -rs`
