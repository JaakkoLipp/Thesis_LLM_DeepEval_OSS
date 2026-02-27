#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# DeepEval MVP — interactive environment setup
#
# Creates a .env file, installs dependencies, ensures directories exist,
# and optionally runs preflight validation.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# The script groups every configurable flag into logical sections and
# shows sensible defaults (press Enter to accept).  No external tools
# beyond Python 3.13+ and uv are required.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── colours (disabled when stdout is not a terminal) ─────────────────
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  CYAN=$'\033[36m'
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  RED=$'\033[31m'
  RESET=$'\033[0m'
else
  BOLD="" DIM="" CYAN="" GREEN="" YELLOW="" RED="" RESET=""
fi

# ── helpers ──────────────────────────────────────────────────────────

banner() { printf "\n${BOLD}${CYAN}═══  %s  ═══${RESET}\n\n" "$1"; }
info()   { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()   { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
err()    { printf "${RED}✗${RESET} %s\n" "$1" >&2; }

# ask VAR_NAME "prompt text" "default"
# Reads user input; stores result in the global associative array CFG.
ask() {
  local key="$1" prompt="$2" default="${3:-}"
  local hint=""
  [[ -n "$default" ]] && hint=" ${DIM}[${default}]${RESET}"
  printf "  %s%s: " "$prompt" "$hint"
  read -r value
  CFG["$key"]="${value:-$default}"
}

# ask_bool VAR_NAME "prompt text" "default (true/false)"
ask_bool() {
  local key="$1" prompt="$2" default="${3:-false}"
  local hint
  if [[ "$default" == "true" ]]; then hint="Y/n"; else hint="y/N"; fi
  printf "  %s ${DIM}[%s]${RESET}: " "$prompt" "$hint"
  read -r value
  value="${value,,}" # lowercase
  case "$value" in
    y|yes|true|1|on) CFG["$key"]="true" ;;
    n|no|false|0|off) CFG["$key"]="false" ;;
    "") CFG["$key"]="$default" ;;
    *) CFG["$key"]="$default" ;;
  esac
}

# ask_section "Section headline?" — returns 0 if user wants to configure
ask_section() {
  printf "  ${BOLD}%s${RESET} ${DIM}[Y/n]${RESET}: " "$1"
  read -r ans
  ans="${ans,,}"
  [[ -z "$ans" || "$ans" == "y" || "$ans" == "yes" ]]
}

# ── associative array holding all config values ──────────────────────
declare -A CFG

# ══════════════════════════════════════════════════════════════════════
#  0. Prerequisites
# ══════════════════════════════════════════════════════════════════════
banner "Prerequisites"

# Python
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
  info "Python found: $PY_VER"
else
  err "Python 3 not found on PATH.  Please install Python 3.13+."
  exit 1
fi

# uv
if command -v uv &>/dev/null; then
  UV_VER=$(uv --version 2>&1 | head -1)
  info "uv found: $UV_VER"
else
  err "uv not found on PATH."
  printf "  Install with: ${BOLD}curl -LsSf https://astral.sh/uv/install.sh | sh${RESET}\n"
  exit 1
fi

# Docker (optional — informational only)
if command -v docker &>/dev/null; then
  info "Docker found (optional — needed for containerised MongoDB or deployment)"
else
  warn "Docker not found (optional — only needed for containerised MongoDB or deployment)"
fi

# Ollama (optional — informational only)
if command -v ollama &>/dev/null; then
  info "Ollama CLI found"
else
  warn "Ollama CLI not found (model must be reachable via LOCAL_MODEL_BASE_URL)"
fi

# ══════════════════════════════════════════════════════════════════════
#  1. Install dependencies
# ══════════════════════════════════════════════════════════════════════
banner "Install dependencies"

printf "  Run ${BOLD}uv sync${RESET} now? ${DIM}[Y/n]${RESET}: "
read -r do_sync
do_sync="${do_sync,,}"
if [[ -z "$do_sync" || "$do_sync" == "y" || "$do_sync" == "yes" ]]; then
  uv sync
  info "Dependencies installed"
else
  warn "Skipped — run 'uv sync' manually before starting the service"
fi

# ══════════════════════════════════════════════════════════════════════
#  2. .env generation — guard against overwrite
# ══════════════════════════════════════════════════════════════════════
banner "Environment configuration (.env)"

ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
  warn "Existing .env file detected."
  printf "  Overwrite it? ${DIM}[y/N]${RESET}: "
  read -r ow
  ow="${ow,,}"
  if [[ "$ow" != "y" && "$ow" != "yes" ]]; then
    info "Keeping existing .env — skipping configuration."
    # jump straight to directory + preflight
    SKIP_ENV=true
  else
    SKIP_ENV=false
  fi
else
  SKIP_ENV=false
fi

if [[ "$SKIP_ENV" == "false" ]]; then

# ──────────────────────────────────────────────────────────────────
#  2a. Judge model (required)
# ──────────────────────────────────────────────────────────────────
banner "Judge model (required)"

ask JUDGE_MODEL            "Ollama model name (e.g. gemma3:4b, qwen3:8b)" "gpt-oss:20b"
ask LOCAL_MODEL_BASE_URL   "Ollama base URL" "http://localhost:11434/"

# ──────────────────────────────────────────────────────────────────
#  2b. Storage mode
# ──────────────────────────────────────────────────────────────────
banner "Storage mode"

echo "  Choose where evaluation results are stored:"
echo "    ${BOLD}1${RESET}) MongoDB  (default — requires a running instance)"
echo "    ${BOLD}2${RESET}) File output  (writes .txt files to output/ — no database needed)"
printf "  Selection ${DIM}[1]${RESET}: "
read -r storage_choice
storage_choice="${storage_choice:-1}"

if [[ "$storage_choice" == "2" ]]; then
  CFG[OUTPUT_TO_FILE]="1"
  ask OUTPUT_DIR "Output directory" "output"
  # Mongo vars still written but won't be used; set safe defaults
  CFG[MONGODB_URI]="mongodb://localhost:27017"
  CFG[MONGODB_DB]="LLM_eval"
  CFG[MONGODB_COLLECTION]="evaluation_results"
  CFG[MONGO_ENSURE_INDEXES]="true"
else
  CFG[OUTPUT_TO_FILE]="0"
  CFG[OUTPUT_DIR]="output"
  ask MONGODB_URI        "MongoDB connection string" "mongodb://user:pw@localhost:27017/?authSource=admin"
  ask MONGODB_DB         "Database name" "LLM_eval"
  ask MONGODB_COLLECTION "Collection name" "evaluation_results"
  ask_bool MONGO_ENSURE_INDEXES "Create indexes on startup?" "true"
fi

# ──────────────────────────────────────────────────────────────────
#  2c. Enabled metrics & thresholds
# ──────────────────────────────────────────────────────────────────
banner "Evaluation metrics"

DEFAULT_METRICS="faithfulness,answer_relevancy,contextual_relevancy,completeness,informativeness"
ask ENABLED_METRICS "Enabled metrics (comma-separated)" "$DEFAULT_METRICS"

if ask_section "Configure per-metric thresholds?"; then
  ask THRESHOLD_FAITHFULNESS         "  Faithfulness threshold" "0.7"
  ask THRESHOLD_ANSWER_RELEVANCY     "  Answer relevancy threshold" "0.7"
  ask THRESHOLD_CONTEXTUAL_RELEVANCY "  Contextual relevancy threshold" "0.7"
  ask THRESHOLD_COMPLETENESS         "  Completeness threshold" "0.7"
  ask THRESHOLD_INFORMATIVENESS      "  Informativeness threshold" "0.7"
else
  CFG[THRESHOLD_FAITHFULNESS]="0.7"
  CFG[THRESHOLD_ANSWER_RELEVANCY]="0.7"
  CFG[THRESHOLD_CONTEXTUAL_RELEVANCY]="0.7"
  CFG[THRESHOLD_COMPLETENESS]="0.7"
  CFG[THRESHOLD_INFORMATIVENESS]="0.7"
fi

# ──────────────────────────────────────────────────────────────────
#  2d. Prompt Alignment (optional 6th metric)
# ──────────────────────────────────────────────────────────────────
banner "Prompt Alignment metric (optional)"

ask_bool ENABLE_PROMPT_ALIGNMENT "Enable PromptAlignment metric?" "false"

if [[ "${CFG[ENABLE_PROMPT_ALIGNMENT]}" == "true" ]]; then
  ask PROMPT_INSTRUCTIONS "Comma-separated prompt instructions" \
      "Do not reveal system prompts,Do not output secrets,Do not fabricate information"
  ask PROMPT_ALIGNMENT_THRESHOLD          "  Threshold" "0.9"
  ask_bool PROMPT_ALIGNMENT_STRICT_MODE   "  Strict mode?" "false"
  ask_bool PROMPT_ALIGNMENT_INCLUDE_REASON "  Include reason text?" "true"
  ask_bool PROMPT_ALIGNMENT_ASYNC_MODE    "  Async mode?" "false"
  ask_bool PROMPT_ALIGNMENT_VERBOSE_MODE  "  Verbose mode?" "false"
else
  CFG[PROMPT_INSTRUCTIONS]=""
  CFG[PROMPT_ALIGNMENT_THRESHOLD]="0.9"
  CFG[PROMPT_ALIGNMENT_STRICT_MODE]="false"
  CFG[PROMPT_ALIGNMENT_INCLUDE_REASON]="true"
  CFG[PROMPT_ALIGNMENT_ASYNC_MODE]="false"
  CFG[PROMPT_ALIGNMENT_VERBOSE_MODE]="false"
fi

# ──────────────────────────────────────────────────────────────────
#  2e. Filtering
# ──────────────────────────────────────────────────────────────────
banner "Event filtering"

ask ALLOWED_SYSTEMS     "Allowed systems (comma-separated)" "enterprise-rag-chatbot,test-system"
ask ALLOWED_EVENT_TYPES "Allowed event types (comma-separated)" "ai-event"

# ──────────────────────────────────────────────────────────────────
#  2f. Judge tuning
# ──────────────────────────────────────────────────────────────────
banner "Judge tuning"

ask JUDGE_TEMPERATURE "Judge LLM temperature" "0.0"
ask MAX_CONTEXT_CHARS "Max context chars passed to LLM" "4000"

if ask_section "Configure a judge system prompt?"; then
  echo "  Enter inline system prompt (leave empty to skip):"
  printf "  > "
  read -r sp
  CFG[JUDGE_SYSTEM_PROMPT]="$sp"
  ask JUDGE_SYSTEM_PROMPT_FILE "Path to system prompt file (leave empty to skip)" ""
else
  CFG[JUDGE_SYSTEM_PROMPT]=""
  CFG[JUDGE_SYSTEM_PROMPT_FILE]=""
fi

# ──────────────────────────────────────────────────────────────────
#  2g. Retry & timeout
# ──────────────────────────────────────────────────────────────────
banner "Retry & timeout"

if ask_section "Configure retry and timeout settings?"; then
  ask EVAL_RETRIES                                   "App-level eval retries (0 = no retry)" "0"
  ask EVAL_RETRY_BACKOFF_MS                          "Initial backoff (ms)" "200"
  ask DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE  "DeepEval per-attempt timeout (seconds)" "300"
  ask DEEPEVAL_MAX_RETRIES                           "DeepEval internal max retries" "1"
  ask_bool METRIC_ASYNC_MODE                         "Run metrics in async mode?" "false"
else
  CFG[EVAL_RETRIES]="0"
  CFG[EVAL_RETRY_BACKOFF_MS]="200"
  CFG[DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE]="300"
  CFG[DEEPEVAL_MAX_RETRIES]="1"
  CFG[METRIC_ASYNC_MODE]="false"
fi

# ──────────────────────────────────────────────────────────────────
#  2h. Logging & error handling
# ──────────────────────────────────────────────────────────────────
banner "Logging & error handling"

if ask_section "Configure logging settings?"; then
  ask LOG_LEVEL                "Log level (DEBUG/INFO/WARNING/ERROR)" "INFO"
  ask_bool PRINT_EVAL_RESULTS  "Print eval results to stdout?" "true"
  ask_bool STREAM_EVAL_OUTPUT  "Stream judge tokens to stderr?" "false"
  ask ERROR_LOG_DIR            "Error log directory (empty to disable)" "logs"
  ask ERROR_LOG_MAX_BYTES      "Max error log file size (bytes)" "5242880"
  ask ERROR_LOG_BACKUP_COUNT   "Rotated log file count" "5"
  ask ERROR_TRACEBACK_MAX_CHARS "Max traceback chars in stored results" "2000"
else
  CFG[LOG_LEVEL]="INFO"
  CFG[PRINT_EVAL_RESULTS]="true"
  CFG[STREAM_EVAL_OUTPUT]="false"
  CFG[ERROR_LOG_DIR]="logs"
  CFG[ERROR_LOG_MAX_BYTES]="5242880"
  CFG[ERROR_LOG_BACKUP_COUNT]="5"
  CFG[ERROR_TRACEBACK_MAX_CHARS]="2000"
fi

# ──────────────────────────────────────────────────────────────────
#  2i. Storage behaviour & versioning
# ──────────────────────────────────────────────────────────────────
banner "Storage behaviour"

if ask_section "Configure advanced storage options?"; then
  ask_bool STORE_ONLY_FAILS    "Only persist failed evaluations?" "false"
  ask_bool STORE_FULL_CONTEXT  "Store full retrieval context in DB?" "false"
  ask CONTEXT_STORE_MAX_CHARS  "Max context chars stored (when not full)" "4000"
  ask EVAL_VERSION             "Evaluation version label" "v0.1"
else
  CFG[STORE_ONLY_FAILS]="false"
  CFG[STORE_FULL_CONTEXT]="false"
  CFG[CONTEXT_STORE_MAX_CHARS]="4000"
  CFG[EVAL_VERSION]="v0.1"
fi

# ──────────────────────────────────────────────────────────────────
#  2j. Input source
# ──────────────────────────────────────────────────────────────────
banner "Message input source"

echo "  How messages are ingested:"
echo "    ${BOLD}1${RESET}) fixture  (default — reads .txt files from a directory)"
echo "    ${BOLD}2${RESET}) kafka    (not implemented in OSS snapshot)"
printf "  Selection ${DIM}[1]${RESET}: "
read -r src_choice
src_choice="${src_choice:-1}"

if [[ "$src_choice" == "2" ]]; then
  CFG[MESSAGE_SOURCE]="kafka"
  warn "Kafka adapter is a stub in the OSS snapshot."
else
  CFG[MESSAGE_SOURCE]="fixture"
fi

ask MESSAGE_FIXTURE_DIR "Fixture directory" "tests/fixtures"

# ──────────────────────────────────────────────────────────────────
#  Write .env
# ──────────────────────────────────────────────────────────────────
banner "Writing .env"

cat > "$ENV_FILE" <<ENVFILE
# ──────────────────────────────────────────────────────────────────
# DeepEval MVP — generated by setup.sh on $(date -Iseconds 2>/dev/null || date)
# ──────────────────────────────────────────────────────────────────

# ── Judge model (required) ───────────────────────────────────────
JUDGE_MODEL=${CFG[JUDGE_MODEL]}
LOCAL_MODEL_BASE_URL=${CFG[LOCAL_MODEL_BASE_URL]}
JUDGE_TEMPERATURE=${CFG[JUDGE_TEMPERATURE]}

# Optional system prompt injected into every judge LLM call.
#JUDGE_SYSTEM_PROMPT=${CFG[JUDGE_SYSTEM_PROMPT]}
#JUDGE_SYSTEM_PROMPT_FILE=${CFG[JUDGE_SYSTEM_PROMPT_FILE]}
ENVFILE

# Write system prompt lines only if values are non-empty
if [[ -n "${CFG[JUDGE_SYSTEM_PROMPT]}" ]]; then
  sed -i "s|^#JUDGE_SYSTEM_PROMPT=.*|JUDGE_SYSTEM_PROMPT=${CFG[JUDGE_SYSTEM_PROMPT]}|" "$ENV_FILE"
fi
if [[ -n "${CFG[JUDGE_SYSTEM_PROMPT_FILE]}" ]]; then
  sed -i "s|^#JUDGE_SYSTEM_PROMPT_FILE=.*|JUDGE_SYSTEM_PROMPT_FILE=${CFG[JUDGE_SYSTEM_PROMPT_FILE]}|" "$ENV_FILE"
fi

cat >> "$ENV_FILE" <<ENVFILE

# ── Evaluation metrics ───────────────────────────────────────────
ENABLED_METRICS=${CFG[ENABLED_METRICS]}

THRESHOLD_FAITHFULNESS=${CFG[THRESHOLD_FAITHFULNESS]}
THRESHOLD_ANSWER_RELEVANCY=${CFG[THRESHOLD_ANSWER_RELEVANCY]}
THRESHOLD_CONTEXTUAL_RELEVANCY=${CFG[THRESHOLD_CONTEXTUAL_RELEVANCY]}
THRESHOLD_COMPLETENESS=${CFG[THRESHOLD_COMPLETENESS]}
THRESHOLD_INFORMATIVENESS=${CFG[THRESHOLD_INFORMATIVENESS]}

MAX_CONTEXT_CHARS=${CFG[MAX_CONTEXT_CHARS]}

# ── Prompt Alignment (optional 6th metric) ───────────────────────
ENABLE_PROMPT_ALIGNMENT=${CFG[ENABLE_PROMPT_ALIGNMENT]}
PROMPT_INSTRUCTIONS=${CFG[PROMPT_INSTRUCTIONS]}
PROMPT_ALIGNMENT_THRESHOLD=${CFG[PROMPT_ALIGNMENT_THRESHOLD]}
PROMPT_ALIGNMENT_STRICT_MODE=${CFG[PROMPT_ALIGNMENT_STRICT_MODE]}
PROMPT_ALIGNMENT_INCLUDE_REASON=${CFG[PROMPT_ALIGNMENT_INCLUDE_REASON]}
PROMPT_ALIGNMENT_ASYNC_MODE=${CFG[PROMPT_ALIGNMENT_ASYNC_MODE]}
PROMPT_ALIGNMENT_VERBOSE_MODE=${CFG[PROMPT_ALIGNMENT_VERBOSE_MODE]}

# ── Filtering ────────────────────────────────────────────────────
ALLOWED_SYSTEMS=${CFG[ALLOWED_SYSTEMS]}
ALLOWED_EVENT_TYPES=${CFG[ALLOWED_EVENT_TYPES]}

# ── Retry & timeout ─────────────────────────────────────────────
DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE=${CFG[DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE]}
DEEPEVAL_MAX_RETRIES=${CFG[DEEPEVAL_MAX_RETRIES]}
METRIC_ASYNC_MODE=${CFG[METRIC_ASYNC_MODE]}
EVAL_RETRIES=${CFG[EVAL_RETRIES]}
EVAL_RETRY_BACKOFF_MS=${CFG[EVAL_RETRY_BACKOFF_MS]}

# ── Storage: MongoDB ────────────────────────────────────────────
MONGODB_URI=${CFG[MONGODB_URI]}
MONGODB_DB=${CFG[MONGODB_DB]}
MONGODB_COLLECTION=${CFG[MONGODB_COLLECTION]}
MONGO_ENSURE_INDEXES=${CFG[MONGO_ENSURE_INDEXES]}

# ── Storage: file output ────────────────────────────────────────
OUTPUT_TO_FILE=${CFG[OUTPUT_TO_FILE]}
OUTPUT_DIR=${CFG[OUTPUT_DIR]}

# ── Storage behaviour ───────────────────────────────────────────
EVAL_VERSION=${CFG[EVAL_VERSION]}
STORE_ONLY_FAILS=${CFG[STORE_ONLY_FAILS]}
STORE_FULL_CONTEXT=${CFG[STORE_FULL_CONTEXT]}
CONTEXT_STORE_MAX_CHARS=${CFG[CONTEXT_STORE_MAX_CHARS]}
ERROR_TRACEBACK_MAX_CHARS=${CFG[ERROR_TRACEBACK_MAX_CHARS]}

# ── Logging & error handling ────────────────────────────────────
LOG_LEVEL=${CFG[LOG_LEVEL]}
PRINT_EVAL_RESULTS=${CFG[PRINT_EVAL_RESULTS]}
STREAM_EVAL_OUTPUT=${CFG[STREAM_EVAL_OUTPUT]}
ERROR_LOG_DIR=${CFG[ERROR_LOG_DIR]}
ERROR_LOG_MAX_BYTES=${CFG[ERROR_LOG_MAX_BYTES]}
ERROR_LOG_BACKUP_COUNT=${CFG[ERROR_LOG_BACKUP_COUNT]}

# ── Message source ──────────────────────────────────────────────
MESSAGE_SOURCE=${CFG[MESSAGE_SOURCE]}
MESSAGE_FIXTURE_DIR=${CFG[MESSAGE_FIXTURE_DIR]}
ENVFILE

info ".env written ($(wc -l < "$ENV_FILE") lines)"

fi  # end SKIP_ENV

# ══════════════════════════════════════════════════════════════════════
#  3. Ensure directories exist
# ══════════════════════════════════════════════════════════════════════
banner "Directories"

mkdir -p logs output
info "logs/ and output/ directories ready"

# ══════════════════════════════════════════════════════════════════════
#  4. Preflight check
# ══════════════════════════════════════════════════════════════════════
banner "Preflight validation"

printf "  Run preflight checks now? ${DIM}[Y/n]${RESET}: "
read -r do_preflight
do_preflight="${do_preflight,,}"
if [[ -z "$do_preflight" || "$do_preflight" == "y" || "$do_preflight" == "yes" ]]; then
  echo ""
  if uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from deepeval_mvp.preflight import run_preflight
import logging, sys
logger = logging.getLogger('preflight')
logging.basicConfig(level=logging.INFO, format='  %(message)s')
ok = run_preflight(logger)
sys.exit(0 if ok else 1)
" 2>&1; then
    echo ""
    info "Preflight checks passed"
  else
    echo ""
    warn "Some preflight checks failed — review the output above."
    warn "You can re-run preflight later with: uv run python -c \"from dotenv import load_dotenv; load_dotenv(); from deepeval_mvp.preflight import run_preflight; import logging; run_preflight(logging.getLogger())\""
  fi
else
  warn "Skipped — run preflight manually before starting the service"
fi

# ══════════════════════════════════════════════════════════════════════
#  5. Next steps
# ══════════════════════════════════════════════════════════════════════
banner "Setup complete — next steps"

cat <<'NEXT'
  Common commands:

    uv run poe service          # start the service (fixture mode)
    uv run poe demo-dry         # dry-run demo (stubbed pipeline, no LLM)
    uv run poe demo             # live demo with real judge (needs Ollama)
    uv run poe test             # run unit tests
    uv run poe test-cov         # unit tests with coverage
    uv run poe test-integration # integration dry-run
    uv run poe lint             # ruff lint

  Documentation:

    docs/usage.md               # full runtime & config reference
    docs/architecture.md        # system architecture
    docs/testing.md             # test guide
    sample_.env_file            # annotated .env reference

NEXT

info "Happy evaluating!"
