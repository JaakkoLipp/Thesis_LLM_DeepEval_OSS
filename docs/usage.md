# docs/RUNNING.md

The project has two primary modes: `demo` and `run`.

## Demo mode (one-shot)

Evaluates all fixture files in a directory and prints results.

* `uv run python -m deepeval_mvp.main demo --fixtures tests/fixtures`
* `uv run python -m deepeval_mvp.main demo --fixtures /path/to/fixtures`

## Service mode (long-running)

Current implementation polls a fixture directory and processes each file once. This simulates a service loop until Kafka integration is added.

* `uv run python -m deepeval_mvp.main run --fixtures tests/fixtures --poll-seconds 5`

Arguments:

* `--fixtures`: directory containing `*.txt` fixture files
* `--poll-seconds`: poll interval

Shutdown:

* Ctrl+C

---

# docs/CONFIGURATION.md

Configuration is via environment variables.

## Evaluation

`JUDGE_MODEL` (required for integration tests)

* model identifier for the judge backend
* examples (Ollama): `llama3:8b`, `qwen2.5:7b`, etc.

`MAX_CONTEXT_CHARS` (optional)

* maximum number of characters from context passed into evaluation
* default: `4000`

Example:

* `export MAX_CONTEXT_CHARS=2000`

## Integration test gating

`RUN_INTEGRATION`

* integration tests run only if `RUN_INTEGRATION=1`
* should be set by `poe test-integration`

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
