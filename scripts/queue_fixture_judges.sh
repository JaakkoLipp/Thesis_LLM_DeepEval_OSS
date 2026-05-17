#!/usr/bin/env bash
set -u

# Queue fixture evaluations across mixed judge backends with repeated runs.
#
# Usage:
#   bash scripts/queue_fixture_judges.sh
#
# Output structure:
#   output/judge-matrix/<run_tag>/
#     run1/<model_slug>/   ← one JSON per fixture
#     run2/<model_slug>/
#     ...
#
# Optional env overrides:
#   NUM_RUNS=3
#   POLL_SECONDS=0.0
#   MAX_CYCLES=1
#   FIXTURE_DIR=tests/fixtures
#   RUN_TAG=my_custom_tag
#   OLLAMA_BASE_URL=http://10.5.147.207:11434
#   GRANITE_OLLAMA_MODEL=granite4.0:350m
#   QWEN_OLLAMA_MODEL=qwen3.5:2b
#   GEMMA_OLLAMA_MODEL=gemma4:e4b
#   MINISTRAL_OPENROUTER_MODEL=mistralai/ministral-14b-2512

# Default Ollama endpoint for local/small models.
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://10.5.147.207:11434}"

# Local model tags are user-overridable because naming varies by Ollama pull/tag.
GRANITE_OLLAMA_MODEL="${GRANITE_OLLAMA_MODEL:-granite4:350m}"
QWEN_OLLAMA_MODEL="${QWEN_OLLAMA_MODEL:-qwen3.5:2b}"
GEMMA_OLLAMA_MODEL="${GEMMA_OLLAMA_MODEL:-gemma4:e4b}"
MINISTRAL_OPENROUTER_MODEL="${MINISTRAL_OPENROUTER_MODEL:-mistralai/ministral-14b-2512}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

NUM_RUNS="${NUM_RUNS:-3}"
POLL_SECONDS="${POLL_SECONDS:-0.0}"
MAX_CYCLES="${MAX_CYCLES:-1}"
FIXTURE_DIR="${FIXTURE_DIR:-tests/fixtures}"
RUN_TAG="${RUN_TAG:-judge_matrix_$(date +%Y%m%d_%H%M%S)}"

LABELS=(
  # "Granite 4.0 350M"  # disabled — too small for reliable structured JSON
  # "Qwen3.5 2B"
  "Gemma4 e4b"
  # "Ministral 3 14B"
  # "Qwen3.6 35B"  # disabled
  # "Gemini 3.1 Flash Lite"
  # "DeepSeek V4 Pro"
  # "Gemini 3.1 Pro Preview"
  # "Gemma 4 31B"
)

BACKENDS=(
  # "ollama"
  # "ollama"
  "ollama"
  # "openrouter"
  # "openrouter"
  # "openrouter"
  # "openrouter"
  # "openrouter"
  # "openrouter"
)

MODEL_REFS=(
  # "$GRANITE_OLLAMA_MODEL"
  # "$QWEN_OLLAMA_MODEL"
  "$GEMMA_OLLAMA_MODEL"
  # "$MINISTRAL_OPENROUTER_MODEL"
  # "qwen/qwen3.6-35b-a3b"
  # "google/gemini-3.1-flash-lite"
  # "deepseek/deepseek-v4-pro"
  # "google/gemini-3.1-pro-preview"
  # "google/gemma-4-31b-it"
)

# Optional OpenRouter provider override per model (empty string = no override).
# When set, requests route only to that provider.
PROVIDERS=(
  # ""  # Granite
  # ""  # Qwen3.5 2B
  # ""  # Gemma4 e4b
  # ""  # Ministral
  # ""  # Qwen3.6 35B
  # ""  # Gemini Flash Lite
  # ""  # DeepSeek V4 Pro
  # ""  # Gemini Pro Preview
 # "Parasail,Venice"  # Gemma 4 31B — Parasail primary, Venice fallback
)

# Optional OpenRouter quantization override per model (empty = no override).
QUANTIZATIONS=(
  # ""  # Granite
  # ""  # Qwen3.5 2B
  # ""  # Gemma4 e4b
  # ""  # Ministral
  # ""  # Qwen3.6 35B
  # ""  # Gemini Flash Lite
  # ""  # DeepSeek V4 Pro
  # ""  # Gemini Pro Preview
  "bf16"  # Gemma 4 31B
)

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

printf '\nStarting judge queue\n'
printf 'Run tag      : %s\n' "$RUN_TAG"
printf 'Num runs     : %s\n' "$NUM_RUNS"
printf 'Fixture dir  : %s\n' "$FIXTURE_DIR"
printf 'Max cycles   : %s\n' "$MAX_CYCLES"
printf 'Poll seconds : %s\n' "$POLL_SECONDS"
printf 'Ollama URL   : %s\n\n' "$OLLAMA_BASE_URL"

total_success=0
total_fail=0
failed_entries=()

# ── Helper: build env array for a single model invocation ─────────────────
build_run_env() {
  local backend="$1" model_ref="$2" out_dir="$3" run_dir="$4" model_slug="$5" provider="${6:-}" quantization="${7:-}"
  RUN_ENV=(
    "JUDGE_BACKEND=$backend"
    "JUDGE_MODEL=$model_ref"
    "MESSAGE_SOURCE=fixture"
    "MESSAGE_FIXTURE_DIR=$FIXTURE_DIR"
    "OUTPUT_TO_FILE=1"
    "OUTPUT_FILE_FORMAT=json"
    "OUTPUT_DIR=$out_dir"
    "STORE_ONLY_FAILS=0"
    "EVAL_VERSION=judge-matrix:${RUN_TAG}:${run_dir}:${model_slug}"
  )
  if [[ "$backend" == "ollama" ]]; then
    RUN_ENV+=("LOCAL_MODEL_BASE_URL=$OLLAMA_BASE_URL")
    RUN_ENV+=("OLLAMA_ENABLE_THINKING=false")
  fi
  if [[ "$backend" == "openrouter" ]]; then
    RUN_ENV+=("METRIC_ASYNC_MODE=true")
    if [[ -n "$provider" ]]; then
      RUN_ENV+=("OPENROUTER_PROVIDER=$provider")
    fi
    if [[ -n "$quantization" ]]; then
      RUN_ENV+=("OPENROUTER_QUANTIZATION=$quantization")
    fi
  fi
}

# Resolve Python once — avoids uv's dep-resolution overhead per invocation.
PYTHON="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  printf 'ERROR: %s not found. Run "uv sync" first.\n' "$PYTHON" >&2
  exit 1
fi

for run_num in $(seq 1 "$NUM_RUNS"); do
  run_dir="run${run_num}"
  mkdir -p "output/judge-matrix/$RUN_TAG/$run_dir" \
           "logs/judge-matrix/$RUN_TAG/$run_dir"
done

# ── Phase 1: Launch ALL OpenRouter jobs across all runs in parallel ───────
or_pids=()
or_labels=()
or_logs=()

for run_num in $(seq 1 "$NUM_RUNS"); do
  run_dir="run${run_num}"

  for i in "${!MODEL_REFS[@]}"; do
    [[ "${BACKENDS[$i]}" != "openrouter" ]] && continue

    label="${LABELS[$i]}"
    model_ref="${MODEL_REFS[$i]}"
    provider="${PROVIDERS[$i]:-}"
    quantization="${QUANTIZATIONS[$i]:-}"
    model_slug="$(slugify "$label")"
    out_dir="output/judge-matrix/$RUN_TAG/$run_dir/$model_slug"
    log_file="logs/judge-matrix/$RUN_TAG/$run_dir/$model_slug.log"

    printf '  [openrouter]  %-24s → %s/%s (parallel)\n' "$label" "$run_dir" "$model_slug"
    mkdir -p "$out_dir"

    if [[ -z "$model_ref" ]]; then
      printf '  [openrouter]  SKIPPED — empty model ref for %s\n' "$label"
      total_fail=$((total_fail + 1))
      failed_entries+=("${run_dir}/${label}")
      continue
    fi

    build_run_env "openrouter" "$model_ref" "$out_dir" "$run_dir" "$model_slug" "$provider" "$quantization"

    env "${RUN_ENV[@]}" \
      "$PYTHON" -m deepeval_mvp.main --poll-seconds "$POLL_SECONDS" --max-cycles "$MAX_CYCLES" \
      >"$log_file" 2>&1 &

    or_pids+=($!)
    or_labels+=("${run_dir}/${label}")
    or_logs+=("$log_file")
  done
done

if [[ ${#or_pids[@]} -gt 0 ]]; then
  printf '  [openrouter]  %d total jobs launched across %d runs\n' "${#or_pids[@]}" "$NUM_RUNS"
fi

# ── Phase 2: Run Ollama models sequentially (shared GPU, all runs) ────────
for run_num in $(seq 1 "$NUM_RUNS"); do
  run_dir="run${run_num}"

  for i in "${!MODEL_REFS[@]}"; do
    [[ "${BACKENDS[$i]}" != "ollama" ]] && continue

    label="${LABELS[$i]}"
    model_ref="${MODEL_REFS[$i]}"
    model_slug="$(slugify "$label")"
    out_dir="output/judge-matrix/$RUN_TAG/$run_dir/$model_slug"
    log_file="logs/judge-matrix/$RUN_TAG/$run_dir/$model_slug.log"

    printf -- '------------------------------------------------------------\n'
    printf '  [ollama]  %s  %s (sequential)\n' "$label" "$run_dir"
    printf '  Ref    : %s\n' "$model_ref"
    printf '  Output : %s\n' "$out_dir"
    printf '  Log    : %s\n' "$log_file"

    mkdir -p "$out_dir"

    if [[ -z "$model_ref" ]]; then
      printf '  Status : FAILED (empty model ref for %s)\n\n' "$label"
      total_fail=$((total_fail + 1))
      failed_entries+=("${run_dir}/${label}")
      continue
    fi

    build_run_env "ollama" "$model_ref" "$out_dir" "$run_dir" "$model_slug"

    if env "${RUN_ENV[@]}" \
      "$PYTHON" -m deepeval_mvp.main --poll-seconds "$POLL_SECONDS" --max-cycles "$MAX_CYCLES" \
      >"$log_file" 2>&1; then
      printf '  Status : OK\n'
      total_success=$((total_success + 1))
    else
      printf '  Status : FAILED (see %s)\n' "$log_file"
      total_fail=$((total_fail + 1))
      failed_entries+=("${run_dir}/${label}")
    fi
  done
done

# ── Phase 3: Collect all OpenRouter results ─────────────────────────────────
if [[ ${#or_pids[@]} -gt 0 ]]; then
  printf -- '------------------------------------------------------------\n'
  printf '  Waiting for %d OpenRouter jobs …\n' "${#or_pids[@]}"
  for j in "${!or_pids[@]}"; do
    if wait "${or_pids[$j]}"; then
      printf '  [openrouter]  %-36s OK\n' "${or_labels[$j]}"
      total_success=$((total_success + 1))
    else
      printf '  [openrouter]  %-36s FAILED (see %s)\n' "${or_labels[$j]}" "${or_logs[$j]}"
      total_fail=$((total_fail + 1))
      failed_entries+=("${or_labels[$j]}")
    fi
  done
fi

printf '============================================================\n'
printf 'Queue complete — %d runs × %d models\n' "$NUM_RUNS" "${#MODEL_REFS[@]}"
printf 'Succeeded: %d\n' "$total_success"
printf 'Failed   : %d\n' "$total_fail"
printf 'Run root : output/judge-matrix/%s\n' "$RUN_TAG"
printf 'Logs root: logs/judge-matrix/%s\n' "$RUN_TAG"

if [[ "$total_fail" -gt 0 ]]; then
  printf '\nFailed entries:\n'
  for name in "${failed_entries[@]}"; do
    printf ' - %s\n' "$name"
  done
  exit 1
fi

exit 0
