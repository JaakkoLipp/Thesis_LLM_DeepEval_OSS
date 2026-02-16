# DeepEval_MVP

Engineering master's thesis project module OSS version with redacted internal details.
Intended to evaluate LLM output based on input and retrieval context.

### running the code:
```uv run python -m deepeval_mvp.main```

### docker (minimal)
Build image:
```docker build -t deepeval-mvp:latest .```

Run container:
```docker run --rm --env-file .env deepeval-mvp:latest```

The service includes claim-first idempotent processing so duplicate events can be skipped before expensive evaluation calls.

### Disclaimer
project not intended for production.

contact me at http://jaalip.com/
