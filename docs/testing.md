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

## What changed in test focus

Service tests now validate message-driven contracts instead of fixture-path orchestration:

- process_incoming_event(event, ...)
- process_message(message, ...)
- run_service(...) consuming iter_incoming_messages(...)

Fixtures are still used as input mocks through get_message boundary, not as service-level file orchestration behavior.

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

- uv run pytest -q tests/test_get_message.py
- uv run pytest -q tests/test_service.py
- uv run pytest -q tests/test_pipeline.py
- uv run pytest -q tests/test_main.py

---

# docs/TROUBLESHOOTING.md

## System test is skipped

Common reasons:

* `RUN_SYSTEM!=1` → run `uv run poe test-system` or `uv run poe demo`
* `JUDGE_MODEL not set` → set `JUDGE_MODEL`

See skip reasons:

* `uv run pytest -q -m system -rs`
