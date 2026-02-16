# docs/RUNNING.md

The project runs in service mode by default.

## Service mode (long-running)

Current implementation polls a fixture directory and processes each file once. This simulates a service loop until Kafka integration is added.

* `uv run python -m deepeval_mvp.main --fixtures tests/fixtures --poll-seconds 5`

Arguments:

* `--fixtures`: directory containing `*.txt` fixture files
* `--poll-seconds`: poll interval

Shutdown:

* Ctrl+C

## Fixture-driven full-system checks

The old demo flow is now covered by tests that run the same service processing path over fixture messages.

* `uv run poe demo` (wet-run, real model backend)
* `uv run poe demo-dry` (dry-run, mocked evaluation)

---

# docs/CONFIGURATION.md

Configuration is via environment variables.

## Evaluation

`JUDGE_MODEL` (required for system/wet-run tests)

* model identifier for the judge backend
* examples (Ollama): `llama3:8b`, `qwen2.5:7b`, etc.

`MAX_CONTEXT_CHARS` (optional)

* maximum number of characters from context passed into evaluation
* default: `4000`

Example:

* `export MAX_CONTEXT_CHARS=2000`

## System test gating

`RUN_SYSTEM`

* system tests run only if `RUN_SYSTEM=1`
* set automatically by `poe demo` and `poe test-system`

## Azure judge (only if configured/used)

Typical variables:

* `AZURE_OPENAI_ENDPOINT`
* `AZURE_OPENAI_API_KEY`
* `AZURE_OPENAI_API_VERSION`

Provide secrets via:

* shell environment
* `.env` (local only)
* CI secrets

Do not commit secrets to the repository.
