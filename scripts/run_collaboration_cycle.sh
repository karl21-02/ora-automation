#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE="$(cd "${PROJECT_ROOT}/.." && pwd)"
OUTPUT_ROOT="${PROJECT_ROOT}/research_reports"
RUN_NAME="${RUN_NAME:-V10_자동회차}"
TOP="${TOP:-6}"
FOCUS="${FOCUS:-}"
VERSION_TAG="${VERSION_TAG:-V10}"
RUN_MAX_FILES="${RUN_MAX_FILES:-1500}"
RUN_EXTENSIONS="${RUN_EXTENSIONS:-md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt}"
HISTORY_MAX_FILES="${HISTORY_MAX_FILES:-12}"
KEEP_LAST_RUNS="${KEEP_LAST_RUNS:-12}"
VERIFY_SCOPE="${VERIFY_SCOPE:-recent}"
VERIFY_MAX_FILES="${VERIFY_MAX_FILES:-6}"
DEBATE_ROUNDS="${DEBATE_ROUNDS:-2}"

# Repeat cycles for research iteration
RUN_CYCLES="${RUN_CYCLES:-1}"
# Source verification settings
VERIFY_ROUNDS="${VERIFY_ROUNDS:-3}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-8}"
VERIFY_RETRY_DELAY="${VERIFY_RETRY_DELAY:-1.2}"
BASELINE_SOURCE_FILES="${BASELINE_SOURCE_FILES:-$PROJECT_ROOT/research_reports/V9_대화흐름혁신_업무자동화_신뢰성강화/research_sources.json}"
ORA_RD_RESEARCH_ARXIV_SEARCH="${ORA_RD_RESEARCH_ARXIV_SEARCH:-${ORA_RD_ARXIV_SEARCH_ENABLED:-1}}"
ORA_RD_RESEARCH_CROSSREF_SEARCH="${ORA_RD_RESEARCH_CROSSREF_SEARCH:-1}"
ORA_RD_RESEARCH_OPENALEX_SEARCH="${ORA_RD_RESEARCH_OPENALEX_SEARCH:-1}"
ORA_RD_RESEARCH_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_SEARCH_TIMEOUT:-8}"
ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS:-${ORA_RD_ARXIV_SEARCH_MAX_RESULTS:-6}}"
ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS:-6}"
ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS:-6}"
ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT:-8}"
ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT:-8}"
ORA_RD_ARXIV_SEARCH_ENABLED="${ORA_RD_ARXIV_SEARCH_ENABLED:-${ORA_RD_RESEARCH_ARXIV_SEARCH:-1}}"
ORA_RD_ARXIV_SEARCH_MAX_RESULTS="${ORA_RD_ARXIV_SEARCH_MAX_RESULTS:-${ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS:-6}}"
ORA_RD_ARXIV_SEARCH_TIMEOUT="${ORA_RD_ARXIV_SEARCH_TIMEOUT:-${ORA_RD_RESEARCH_SEARCH_TIMEOUT:-8}}"
ORA_RD_CROSSREF_SEARCH_TIMEOUT="${ORA_RD_CROSSREF_SEARCH_TIMEOUT:-${ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT:-8}}"
ORA_RD_OPENALEX_SEARCH_TIMEOUT="${ORA_RD_OPENALEX_SEARCH_TIMEOUT:-${ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT:-8}}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
fi

sanitize_focus() {
  local raw="$1"
  local slug
  slug="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-' | tr ' ' '_')"
  if [ -z "$slug" ]; then
    echo "general"
  else
    echo "$slug"
  fi
}

cleanup_old_runs() {
  local target_dir="$1"
  local keep="$2"

  if ! echo "$keep" | grep -Eq '^[0-9]+$' || [ "$keep" -le 0 ]; then
    return 0
  fi

  local run_dirs=()
  while IFS= read -r path; do
    run_dirs+=("$path")
  done < <(ls -1dt "${target_dir}"/*/ 2>/dev/null)

  if [ "${#run_dirs[@]}" -le "$keep" ]; then
    return 0
  fi

  local idx
  for ((idx=keep; idx<${#run_dirs[@]}; idx++)); do
    rm -rf "${run_dirs[$idx]}"
  done
}

cycle=1
while [ ${cycle} -le ${RUN_CYCLES} ]; do
  FOCUS_SLUG="$(sanitize_focus "${FOCUS}")"
  RUN_ROOT="${OUTPUT_ROOT}/${RUN_NAME}"
  if [ -n "${FOCUS}" ]; then
    RUN_ROOT="${RUN_ROOT}/${FOCUS_SLUG}"
  fi

  TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
  OUT_DIR="${RUN_ROOT}/${TIMESTAMP}"
  mkdir -p "${OUT_DIR}"

  HISTORY_ARGS=()
  while IFS= read -r -d '' path; do
    HISTORY_ARGS+=("${path}")
  done < <(find "${OUTPUT_ROOT}" -type f -name "ora_rd_research_report_*.md" -print0)
  if [ "${#HISTORY_ARGS[@]}" -gt "${HISTORY_MAX_FILES}" ]; then
    HISTORY_ARGS=("${HISTORY_ARGS[@]:0:${HISTORY_MAX_FILES}}")
  fi

  CMD_ARGS=(
    --workspace "${WORKSPACE}"
    --output-dir "${OUT_DIR}"
    --output-name "rd_research_report"
    --top "${TOP}"
    --max-files "${RUN_MAX_FILES}"
    --extensions "${RUN_EXTENSIONS}"
    --focus "${FOCUS}"
    --version-tag "${VERSION_TAG}"
    --debate-rounds "${DEBATE_ROUNDS}"
  )

  if [ "${#HISTORY_ARGS[@]}" -gt 0 ]; then
    CMD_ARGS+=("--history" "${HISTORY_ARGS[@]}")
  fi

  echo "[cycle ${cycle}] run orchestrator..."
  ORA_RD_RESEARCH_ARXIV_SEARCH="${ORA_RD_RESEARCH_ARXIV_SEARCH}" \
  ORA_RD_RESEARCH_CROSSREF_SEARCH="${ORA_RD_RESEARCH_CROSSREF_SEARCH}" \
  ORA_RD_RESEARCH_OPENALEX_SEARCH="${ORA_RD_RESEARCH_OPENALEX_SEARCH}" \
  ORA_RD_RESEARCH_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_SEARCH_TIMEOUT}" \
  ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS}" \
  ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS}" \
  ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS="${ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS}" \
  ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT}" \
  ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT="${ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT}" \
  ORA_RD_ARXIV_SEARCH_ENABLED="${ORA_RD_ARXIV_SEARCH_ENABLED}" \
  ORA_RD_ARXIV_SEARCH_MAX_RESULTS="${ORA_RD_ARXIV_SEARCH_MAX_RESULTS}" \
  ORA_RD_ARXIV_SEARCH_TIMEOUT="${ORA_RD_ARXIV_SEARCH_TIMEOUT}" \
  ORA_RD_CROSSREF_SEARCH_TIMEOUT="${ORA_RD_CROSSREF_SEARCH_TIMEOUT}" \
  ORA_RD_OPENALEX_SEARCH_TIMEOUT="${ORA_RD_OPENALEX_SEARCH_TIMEOUT}" \
  PYTHONPATH="${PROJECT_ROOT}/src" "${PYTHON_BIN}" -m ora_rd_orchestrator.cli "${CMD_ARGS[@]}"

  latest_md="$(ls -t ${OUT_DIR}/rd_research_report_*.md 2>/dev/null | head -n 1 || true)"
  latest_json="$(ls -t ${OUT_DIR}/rd_research_report_*.json 2>/dev/null | head -n 1 || true)"

  echo "[cycle ${cycle}] [done] output md: ${latest_md}"
  echo "[cycle ${cycle}] [done] output json: ${latest_json}"

  SOURCE_FILES=()
  if [ -f "${OUT_DIR}/research_sources.json" ]; then
    SOURCE_FILES+=("${OUT_DIR}/research_sources.json")
  fi
  if [ -f "${BASELINE_SOURCE_FILES}" ]; then
    SOURCE_FILES+=("${BASELINE_SOURCE_FILES}")
  fi

  if [ "$VERIFY_SCOPE" = "all" ] || [ "$VERIFY_SCOPE" = "recent" ]; then
    while IFS= read -r -d '' path; do
      SOURCE_FILES+=("${path}")
    done < <(find "${OUTPUT_ROOT}" -type f -name "research_sources.json" -print0)
  fi

  if [ "${VERIFY_SCOPE}" = "latest" ]; then
    : # keep only OUT_DIR + BASELINE
  fi

  if [ "${VERIFY_SCOPE}" = "recent" ] && [ "${#SOURCE_FILES[@]}" -gt "${VERIFY_MAX_FILES}" ]; then
    SOURCE_FILES=("${SOURCE_FILES[@]:0:${VERIFY_MAX_FILES}}")
  fi

  if [ "${#SOURCE_FILES[@]}" -eq 0 ]; then
    echo "[warn] no research_sources.json found in ${OUTPUT_ROOT}"
  else
    echo "[cycle ${cycle}] start web verification (${VERIFY_ROUNDS} rounds)..."
    for source_file in "${SOURCE_FILES[@]}"; do
      echo "[cycle ${cycle}] verify source: ${source_file}"
      if ! "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/verify_sources.py" \
          --in-place \
          --source "${source_file}" \
          --rounds "${VERIFY_ROUNDS}" \
          --timeout "${VERIFY_TIMEOUT}" \
          --retry-delay "${VERIFY_RETRY_DELAY}"; then
        echo "[cycle ${cycle}] unresolved items remain in: ${source_file}"
      fi
    done
  fi

  cleanup_old_runs "${RUN_ROOT}" "${KEEP_LAST_RUNS}"

  cycle=$((cycle + 1))
  if [ ${cycle} -le ${RUN_CYCLES} ]; then
    echo "[cycle $((cycle - 1))] next cycle after 1 second pause..."
    sleep 1
  fi
done
