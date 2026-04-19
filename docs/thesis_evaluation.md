# Thesis Evaluation Guide

This document describes how to systematically evaluate the deepeval-mvp system
for a master's thesis in software engineering. It covers functional validation,
judge model comparison, architecture assessment, and limitations.

## 1. Fixture test suite

The fixture set in `tests/fixtures/` is designed as a controlled benchmark.
Each fixture file has a `# META:` header with two tags:

- **difficulty** — how hard the fixture is for the judge model to evaluate correctly
- **brevity** — payload size category

### Difficulty tiers

| Tier | Tag | Description | Fixture count |
|------|-----|-------------|---------------|
| 1 | `1-easy` | Obvious pass or fail; any model should get right | 4 |
| 2 | `2-medium` | Requires baseline reasoning (hallucinations, off-topic, injections) | 8 |
| 3 | `3-hard` | Ambiguous edges: partial answers, rounding, mixed facts, padding | 9 |
| 4 | `4-stress` | Requires strong reasoning: nuance, cross-language, math, multi-entity | 6 |
| — | `filter` | Not evaluated (wrong system/event_type); tests the filtering logic | 2 |

### Brevity categories

| Tag | Description |
|-----|-------------|
| `minimal` | Empty or trivial payload |
| `short` | 1–2 sentence answer |
| `medium` | Paragraph-length answer |
| `long` | Multi-paragraph, dense technical content |

### Running a subset

Set env vars to filter which fixtures are processed:

```bash
# Only easy and medium fixtures:
FIXTURE_DIFFICULTY=1-easy,2-medium

# Only short fixtures:
FIXTURE_BREVITY=short

# Combined (AND logic — fixture must match both):
FIXTURE_DIFFICULTY=3-hard,4-stress
FIXTURE_BREVITY=long
```

Leave both unset (or empty) to run all fixtures.

## 2. Functional validation

### 2.1 Expected outcomes per fixture

This table documents what a correct judge should produce for each fixture.
Comparing actual results to this table is the core of functional validation.

| Fixture | Faith. | Ans.Rel. | Ctx.Rel. | Compl. | Inform. | Prompt.A. | Notes |
|---------|--------|----------|----------|--------|---------|-----------|-------|
| valid_sample | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Baseline: all pass |
| valid_technical_sample | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Dense technical, all pass |
| perfect_paraphrase | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Different words, same meaning |
| not_valid_sample | ✗ | ✗ | ✓ | ✗ | ✗ | ? | Completely wrong facts |
| contradicts_context | ✗ | ✗ | ✓ | ✗ | ✗ | ? | Says opposite of context |
| off_topic_answer | ✗ | ✗ | ✓ | ✗ | ✗ | ? | Unrelated response |
| empty_output | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | No output at all |
| refusal_answer | ? | ? | ✓ | ✗ | ✗ | ? | "I don't know" despite good context |
| vague_answer | ? | ? | ✓ | ✗ | ✗ | ? | No concrete information |
| partial_answer | ✓ | ✓ | ✓ | ✗ | ? | ✓ | Correct but incomplete |
| sample | ? | ✓ | ✓ | ? | ✓ | ✓ | Minor factual error (Nobel year) |
| unfaithful_extrapolation | ✗ | ✓ | ✓ | ? | ✓ | ? | Adds claims not in context |
| hallucinated_source | ✗ | ✓ | ✓ | ? | ✓ | ? | Cites nonexistent study |
| fabricated_statistics | ✗ | ✓ | ✓ | ? | ✓ | ? | Made-up numbers |
| irrelevant_context | ? | ✓ | ✗ | ? | ✓ | ✓ | Good answer, wrong context |
| prompt_injection_leak | ? | ? | ? | ? | ? | ✗ | Leaks "system prompt" |
| correct_but_padded | ✓ | ✓ | ✓ | ✓ | ? | ✓ | Right answer buried in filler |
| mixed_correct_and_wrong | ✗ | ✓ | ✓ | ? | ✓ | ? | Some facts right, some wrong |
| near_correct_rounding | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 13.96M→"~14M" is acceptable |
| correct_with_extras_beyond_context | ? | ✓ | ✓ | ✓ | ✓ | ✓ | True extras not in context |
| minimal_context_good_answer | ? | ✓ | ✓ | ✓ | ✓ | ✓ | Expands from sparse context |
| nuanced_ambiguous | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Genuinely debatable topic |
| subtle_restatement_different_framing | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Same meaning, different framing |
| complex_technical_comparison | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Multi-claim dense comparison |
| deep_multi_entity_reasoning | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 3 systems compared in detail |
| correct_wrong_language | ✓ | ? | ✓ | ✓ | ✓ | ? | Correct but in wrong language |
| math_notation_heavy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Mathematical symbols |

Legend: ✓ = should pass, ✗ = should fail, ? = depends on judge model capability

### 2.2 Running the evaluation

```bash
# Run all fixtures
uv run python -m deepeval_mvp.main

# Run only easy/medium (quick smoke test)
FIXTURE_DIFFICULTY=1-easy,2-medium uv run python -m deepeval_mvp.main

# Run only stress tests
FIXTURE_DIFFICULTY=4-stress uv run python -m deepeval_mvp.main
```

Results appear in the `output/` directory as individual `.txt` files.

## 3. Judge model comparison

### 3.1 Methodology

Run the **same fixture set** with different judge models and compare score
agreement. This reveals the minimum model capability required for reliable
evaluation.

Recommended procedure:

1. Clear the `output/` directory between runs.
2. Change `JUDGE_MODEL` in `.env` for each run.
3. Collect all output files per model into separate directories.
4. Compare scores per fixture across models.

Example models to compare (via OpenRouter):

| Model | Size | Category | Expected cost |
|-------|------|----------|---------------|
| `google/gemma-4-26b-a4b-it:free` | 26B | Small/free | $0 |
| `meta-llama/llama-4-maverick:free` | Large MoE | Large/free | $0 |
| `google/gemini-2.5-flash-preview` | — | Cloud/paid | ~$0.01/run |
| `anthropic/claude-sonnet-4` | — | Cloud/paid | ~$0.10/run |

### 3.2 What to measure

For each fixture × model combination, record:

- **Score per metric** (0.0–1.0)
- **Pass/fail** (score ≥ threshold)
- **Agreement with expected outcome** (from section 2.1 table)
- **Reasoning quality** (is the `reason` field coherent and correct?)

### 3.3 Analysis angles

- **Accuracy by tier**: What percentage of expected outcomes does each model
  match per difficulty tier? A good judge should get 100% on tier 1, ≥90% on
  tier 2, and degrade gracefully on tiers 3–4.
- **Score stability**: Run the same fixture 3× with the same model. How much
  do scores vary? This measures non-determinism inherent to LLM-as-a-judge.
- **Failure modes**: Where does a small model disagree with a large one? These
  are the interesting cases to discuss in the thesis.
- **Cost-accuracy trade-off**: Plot accuracy vs. cost per model.

## 4. Architecture evaluation

### 4.1 Extensibility

The codebase uses protocol-driven design for both input and output:

| Component | Protocol | MVP implementation | Swap example |
|-----------|----------|--------------------|--------------|
| Message source | `MessageSource` | `FixtureMessageSource` | Kafka adapter |
| Result storage | `ResultStore` | `FileResultStore` / `MongoResultStore` | CosmosDB |
| Judge backend | `DeepEvalBaseLLM` + env | `_SanitizingOllamaModel` / `_OpenRouterModel` | Any OpenAI-compatible API |

To evaluate extensibility, count how many files need to change to add:
- A new metric → 1 file (eval.py + env var)
- A new judge backend → 1 file (eval.py)
- A new storage backend → 1 file (new store module) + 1 line (service.py)
- A new message source → 1 file (new source module) + 1 line (service.py)

### 4.2 Testability

```bash
# Unit tests (fast, no external dependencies)
uv run pytest -q -m 'not integration and not system'

# Integration tests (mocked external services)
uv run pytest -q -m 'integration and not system'

# System tests (live model backend required)
RUN_SYSTEM=1 uv run pytest -q -m system

# Coverage report
uv run pytest -q -m 'not integration and not system' --cov=src --cov-report=term-missing
```

### 4.3 Configuration surface

All behaviour is controlled via environment variables (29 documented in
`sample_.env_file`). This enables:
- Different configs per environment (dev/staging/prod) without code changes
- Docker/Kubernetes native deployment via env injection
- Easy CI/CD integration

## 5. Limitations to discuss

### 5.1 Non-determinism
LLM-as-a-judge is inherently stochastic. Even with `JUDGE_TEMPERATURE=0.0`,
different runs can produce slightly different scores. This is a fundamental
limitation of the approach, not a system defect.

### 5.2 Judge model dependency
Evaluation quality is bounded by the judge model's capability. A weak judge
(small model, free tier) will produce unreliable scores on hard fixtures. The
system cannot be better than its judge.

### 5.3 Single-model evaluation
The system uses one judge model for all metrics. Ensemble judging (multiple
models voting) or metric-specific judges could improve reliability but add
complexity and cost.

### 5.4 Fixture-based input
The MVP uses static fixture files. A production system would consume a live
message stream (e.g., Kafka). The `MessageSource` protocol makes this swap
straightforward, but the MVP itself does not demonstrate live evaluation.

### 5.5 No longitudinal tracking
Results are stored per-event but not tracked over time. There is no built-in
mechanism to detect score drift or regression across versions of the evaluated
LLM system.

### 5.6 Rate limiting on free tiers
Free API models have aggressive rate limits that can cause evaluation failures.
The system mitigates this with retries (`OPENROUTER_MAX_RETRIES`,
`EVAL_RETRIES`) but cannot fully overcome upstream throttling.

## 6. Suggested thesis structure for the evaluation chapter

```
6. Evaluation
   6.1 Evaluation criteria and methodology
       - What is being measured (functional correctness, extensibility,
         reliability, judge quality)
       - How it is measured (fixture suite, model comparison, code analysis)
   6.2 Functional validation
       - Results table: fixture × metric × pass/fail
       - Discussion of expected vs. actual outcomes
   6.3 Judge model comparison
       - Score comparison across 2–4 models
       - Accuracy by difficulty tier (bar chart)
       - Score stability analysis
       - Cost-accuracy trade-off
   6.4 Architecture assessment
       - Extensibility evaluation (protocol-driven design)
       - Test coverage metrics
       - Configuration analysis
   6.5 Limitations and future work
       - Non-determinism, model dependency, single-judge limitation
       - Proposed improvements (ensemble judging, live input, drift detection)
```
