#!/usr/bin/env bash
set -u

# Queue fixture evaluations across mixed judge backends.
#
# Usage:
#   bash scripts/queue_fixture_judges.sh
#
# Optional env overrides:
#   POLL_SECONDS=0.0
#   MAX_CYCLES=1
#   FIXTURE_DIR=tests/fixtures
#   RUN_TAG=my_custom_tag
#   OLLAMA_BASE_URL=http://10.5.147.207:11434
#   GRANITE_OLLAMA_MODEL=granite4.0:350m
#   QWEN_OLLAMA_MODEL=qwen3.5:2b
#   GEMMA_OLLAMA_MODEL=gemma-e4b
#   MINISTRAL_OPENROUTER_MODEL=mistralai/ministral-14b-2512

# Default Ollama endpoint for local/small models.
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://10.5.147.207:11434}"

# Local model tags are user-overridable because naming varies by Ollama pull/tag.
GRANITE_OLLAMA_MODEL="${GRANITE_OLLAMA_MODEL:-granite4.0:350m}"
QWEN_OLLAMA_MODEL="${QWEN_OLLAMA_MODEL:-qwen3.5:2b}"
GEMMA_OLLAMA_MODEL="${GEMMA_OLLAMA_MODEL:-gemma-e4b}"
MINISTRAL_OPENROUTER_MODEL="${MINISTRAL_OPENROUTER_MODEL:-mistralai/ministral-14b-2512}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

POLL_SECONDS="${POLL_SECONDS:-0.0}"
MAX_CYCLES="${MAX_CYCLES:-1}"
FIXTURE_DIR="${FIXTURE_DIR:-tests/fixtures}"
RUN_TAG="${RUN_TAG:-judge_matrix_$(date +%Y%m%d_%H%M%S)}"

LABELS=(
  "Granite 4.0 350M"
  "Qwen3.5 2B"
  "Gemma E4B"
  "Ministral 3 14B"
  "gpt-oss-120B"
  "Sonnet 4.6"
  "Kimi K2.6"
)

BACKENDS=(
  "ollama"
  "ollama"
  "ollama"
  "openrouter"
  "openrouter"
  "openrouter"
  "openrouter"
)

MODEL_REFS=(
  "$GRANITE_OLLAMA_MODEL"
  "$QWEN_OLLAMA_MODEL"
  "$GEMMA_OLLAMA_MODEL"
  "$MINISTRAL_OPENROUTER_MODEL"
  "openai/gpt-oss-120b"
  "anthropic/claude-sonnet-4.6"
  "moonshotai/kimi-k2.6"
)

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

printf '\nStarting judge queue\n'
printf 'Run tag      : %s\n' "$RUN_TAG"
printf 'Fixture dir  : %s\n' "$FIXTURE_DIR"
printf 'Max cycles   : %s\n' "$MAX_CYCLES"
printf 'Poll seconds : %s\n\n' "$POLL_SECONDS"
printf 'Ollama URL   : %s\n\n' "$OLLAMA_BASE_URL"

mkdir -p "output/judge-matrix/$RUN_TAG" "logs/judge-matrix/$RUN_TAG"

success_count=0
fail_count=0
failed_labels=()

for i in "${!MODEL_REFS[@]}"; do
  label="${LABELS[$i]}"
  backend="${BACKENDS[$i]}"
  model_ref="${MODEL_REFS[$i]}"
  model_slug="$(slugify "$label")"
  out_dir="output/judge-matrix/$RUN_TAG/$model_slug"
  log_file="logs/judge-matrix/$RUN_TAG/$model_slug.log"

  printf '============================================================\n'
  printf 'Running: %s\n' "$label"
  printf 'Backend: %s\n' "$backend"
  printf 'Model  : %s\n' "$model_ref"
  printf 'Output : %s\n' "$out_dir"
  printf 'Log    : %s\n' "$log_file"

  mkdir -p "$out_dir"

  if [[ -z "$model_ref" ]]; then
    printf 'Status : FAILED (empty model ref for %s)\n\n' "$label"
    fail_count=$((fail_count + 1))
    failed_labels+=("$label")
    continue
  fi

  run_env=(
    "JUDGE_BACKEND=$backend"
    "JUDGE_MODEL=$model_ref"
    "MESSAGE_SOURCE=fixture"
    "MESSAGE_FIXTURE_DIR=$FIXTURE_DIR"
    "OUTPUT_TO_FILE=1"
    "OUTPUT_FILE_FORMAT=json"
    "OUTPUT_DIR=$out_dir"
    "STORE_ONLY_FAILS=0"
    "EVAL_VERSION=judge-matrix:${RUN_TAG}:${model_slug}"
  )

  if [[ "$backend" == "ollama" ]]; then
    run_env+=("LOCAL_MODEL_BASE_URL=$OLLAMA_BASE_URL")
  fi

  if env "${run_env[@]}" \
    uv run python -m deepeval_mvp.main --poll-seconds "$POLL_SECONDS" --max-cycles "$MAX_CYCLES" \
    >"$log_file" 2>&1; then
    printf 'Status : OK\n\n'
    success_count=$((success_count + 1))
  else
    printf 'Status : FAILED (see %s)\n\n' "$log_file"
    fail_count=$((fail_count + 1))
    failed_labels+=("$label")
  fi
done

printf '============================================================\n'
printf 'Queue complete\n'
printf 'Succeeded: %d\n' "$success_count"
printf 'Failed   : %d\n' "$fail_count"
printf 'Run root : output/judge-matrix/%s\n' "$RUN_TAG"
printf 'Logs root: logs/judge-matrix/%s\n' "$RUN_TAG"

if [[ "$fail_count" -gt 0 ]]; then
  printf '\nFailed models:\n'
  for name in "${failed_labels[@]}"; do
    printf ' - %s\n' "$name"
  done
  exit 1
fi

exit 0
