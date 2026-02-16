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

## Integration gating

Integration tests are dry-run and do not require model backend credentials.

## System gating

System tests require:

* `RUN_SYSTEM=1` (set by `test-system` and `demo` Poe tasks)
* `JUDGE_MODEL` (must be set)

System tests assert **result schema**, not exact scores.

---

# docs/TROUBLESHOOTING.md

## System test is skipped

Common reasons:

* `RUN_SYSTEM!=1` → run `uv run poe test-system` or `uv run poe demo`
* `JUDGE_MODEL not set` → set `JUDGE_MODEL`

See skip reasons:

* `uv run pytest -q -m system -rs`
