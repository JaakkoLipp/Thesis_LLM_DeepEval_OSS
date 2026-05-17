# `analyse_judge_matrix.py`

Replication script for the agreement analysis reported in Chapter 6.3 of the
thesis *"Can AI Judge AI? Designing and Building an Automated LLM Evaluation
Platform for Enterprise Generative AI Systems"*.

Given a directory of LLM-judge outputs and a reference-labels spreadsheet,
the script computes reliability, self-consistency, Cohen's κ against the
reference, and (in matrix mode) pairwise judge-vs-judge κ.

---

## Requirements

```bash
pip install pandas scikit-learn openpyxl
pip install matplotlib   # only required for --figures
```

If you use `uv`, these are also available via the `analysis` extra defined in
the repository's `pyproject.toml`:

```bash
uv pip install -e ".[analysis]"
```

---

## Input layouts

The script auto-detects three shapes. Pick whichever applies; no flag is
needed to switch modes.

### Single run, single judge (flat, for informal probes)

```
<input>/
    evt_*.json
```

### Multi-run, single judge

```
<input>/
    run1/<judge>/evt_*.json
    run2/<judge>/evt_*.json
    run3/<judge>/evt_*.json
```

### Multi-run, multi-judge (the canonical scored matrix)

```
<input>/
    run1/<judge_a>/evt_*.json
    run1/<judge_b>/evt_*.json
    run2/<judge_a>/evt_*.json
    ...
```

Events must conform to the `deepeval_mvp` event schema: either
`status: "done"` with an `evaluation.metrics` array, or `status: "error"`
with an `error.type` and `error.message` field.

The reference-labels xlsx must contain columns `fixture`, `metric`,
`difficulty`, `user_input`, `model_output`, and `label` (where `label` is
`pass` or `fail`).

---

## Usage

### Reproduce Chapter 6.3 end-to-end

```bash
python scripts/analyse_judge_matrix.py \
    --input  output/judge-matrix/<canonical_matrix_timestamp> \
    --labels tests/reference_labels_COMPLETED.xlsx \
    --out    output/analysis/scored_matrix \
    --figures
```

This single command produces every number reported in Section 6.3:
overall reliability, self-consistency, pooled κ, per-metric κ, per-tier κ,
pairwise judge κ, plus PNG reproductions of Figures 6.1 and 6.2.

### Analyse a single informal probe

```bash
python scripts/analyse_judge_matrix.py \
    --input  output/judge-matrix/<single_judge_directory> \
    --labels tests/reference_labels_COMPLETED.xlsx \
    --out    output/analysis/<judge_name>
```

---

## Output files

Per-judge files (one set per judge analysed):

| File | Contents |
|---|---|
| `<judge>_reliability.csv` | Reliability per metric and overall |
| `<judge>_self_consistency.csv` | Per-metric self-consistency (multi-run only) |
| `<judge>_score_swings.csv` | Cells with score range ≥ 0.5 across runs (multi-run only) |
| `<judge>_kappa_per_metric.csv` | κ, % agreement, n per metric |
| `<judge>_kappa_per_tier.csv` | κ, % agreement, n per difficulty tier |
| `<judge>_joined.csv` | Per-cell join of judge majority verdict and reference label |
| `<judge>_long.csv` | Long-form dump of every record (one row per run × fixture × metric) |

Cross-judge files (matrix mode only):

| File | Contents |
|---|---|
| `summary.csv` | One row per judge with headline reliability, self-consistency, κ, n |
| `pairwise_kappa.csv` | Cohen's κ between every pair of judges' majority verdicts |
| `figure_6_1_reliability_vs_agreement.png` | Figure 6.1 reproduction (with `--figures`) |
| `figure_6_2_agreement_by_tier.png` | Figure 6.2 reproduction (with `--figures`) |

---

## Implementation notes

- **Fixture matching** uses the `(user_input, model_output)` pair rather than
  `user_input` alone. Some fixtures (e.g. `valid_sample` and
  `not_valid_sample`) share a `user_input` but differ in `model_output`, so
  matching on input alone would misattribute their labels.
- **Cohen's κ with a constant rater** returns `NaN` rather than `0.0`. When
  every observation in a subset has the same label (most commonly on the
  stress tier, where the reference rates almost everything as fail), κ is
  mathematically undefined; reporting `NaN` is more honest than the sklearn
  default of `0.0` with a warning.
- **Majority verdict** is used as the per-cell judge verdict in multi-run
  mode (the verdict that appears in ≥ 2 of 3 runs). Cells where any run
  errored are excluded from the κ computation.

---

## Reproducibility note

LLM inference at temperature zero is **not** perfectly deterministic across
hardware, vendor backend versions, or quantisation settings. Replicating
the analysis end-to-end may produce κ values that differ from those
reported in the thesis by small amounts (typically less than 0.02 in
pooled κ), and self-consistency percentages may differ by a few percentage
points. These differences do not indicate a failure to replicate; they
reflect the documented non-determinism of small-judge inference that
Section 6.3 itself analyses.

The fixed inputs of the experiment are:

- The 27 evaluation-eligible fixtures in `tests/fixtures/`
- The reference labels in `tests/reference_labels_COMPLETED.xlsx`
- The five DeepEval metrics (`Faithfulness`, `AnswerRelevancy`,
  `ContextualRelevancy`, `Completeness`, `Informativeness`)
- Temperature set to zero for every judge invocation

The components that may legitimately vary across replications are:

- Exact judge-model weights served by Ollama or OpenRouter at the time of
  the run
- Local quantisation choices
- Vendor-side model updates (relevant for OpenRouter-hosted judges)
