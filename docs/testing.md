# Testing

This project uses a **layered testing strategy** to ensure correctness while avoiding flaky or slow tests during normal development.

Tests are executed via **pytest**, orchestrated using **Poe** and **uv** for reproducibility.

## Summary

| Command                | Purpose                        |
| ---------------------- | ------------------------------ |
| `poe test`             | Fast unit tests (default)      |
| `poe test-integration` | Real backend integration tests |
| `poe test-cov`         | Unit test coverage             |



## Test types

### Unit tests (default)

* Fast and deterministic
* Do **not** call external LLMs or APIs
* Use mocks/stubs for evaluation backends
* Safe to run locally and in CI on every change

Run with:

```bash
uv run poe test
```

This command runs:

* all tests **except** those marked `integration`


### Integration tests (opt-in)

* Execute the **real evaluation stack**
* Call an actual judge backend (e.g. Ollama or Azure OpenAI)
* Validate end-to-end behavior and output schema
* Slower (typically ~1–2 minutes)

Run with:

```bash
uv run poe test-integration
```

Integration tests are explicitly gated and will not run unless enabled.


## Environment variables for integration tests

Integration tests require additional configuration, by default loads .env file from repo.

### Required

* `JUDGE_MODEL`
  The judge model or deployment name to use.

### Provider-specific (examples)

**Ollama**

* Ollama must be running locally
* The selected model must fit available system/GPU memory

**Azure OpenAI**

* `AZURE_OPENAI_API_KEY`
* `AZURE_OPENAI_ENDPOINT`
* `AZURE_OPENAI_API_VERSION`

Secrets should be provided via:

* shell environment
* `.env` file (local development)
* CI secrets

They must **not** be committed to the repository.


## Why integration tests are gated

Integration tests:

* incur cost (Azure)
* depend on system resources (GPU / RAM)
* are inherently slower and less deterministic

For this reason:

* unit tests are the default
* integration tests require an explicit command
* CI should run unit tests on every change, and integration tests selectively

This mirrors production testing practices for LLM-based systems.


## Coverage

* Unit test coverage focuses on **deterministic logic**
* External LLM evaluation paths are validated via integration tests, not unit coverage
* CLI/entrypoint code is excluded from coverage by design

Coverage can be run with:

```bash
uv run poe test-cov
```

