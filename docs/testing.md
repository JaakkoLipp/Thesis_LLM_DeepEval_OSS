# docs/TESTING.md

Testing is split into **unit** and **integration** tests.

## Commands (recommended)

Unit tests (fast, deterministic, no external LLM calls):

* `uv run poe test`
* `uv run poe test-v` (verbose, no output capture)

Integration tests (real judge backend; slower; environment-dependent):

* `uv run poe test-integration`

Coverage (unit tests only):

* `uv run poe test-cov`

If you have optional tasks:

* `uv run poe test-cov-all` (unit + integration coverage; requires integration env)

## Integration gating

Integration tests require:

* `RUN_INTEGRATION=1` (should be set by the `test-integration` Poe task)
* `JUDGE_MODEL` (must be set)

Integration tests assert **result schema**, not exact scores.

---

# docs/TROUBLESHOOTING.md

## Integration test is skipped

Common reasons:

* `RUN_INTEGRATION!=1` → run `uv run poe test-integration`
* `JUDGE_MODEL not set` → set `JUDGE_MODEL`

See skip reasons:

* `uv run pytest -q -m integration -rs`
