#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE="$(cd "${PROJECT_ROOT}/.." && pwd)"
OUTPUT_ROOT="${PROJECT_ROOT}/research_reports"
CANONICAL_REPORT_MD="${OUTPUT_ROOT}/rd_research_report.md"

RUN_NAME="${RUN_NAME:-V10_자동회차}"
TOP="${TOP:-6}"
FOCUS="${FOCUS:-}"
VERSION_TAG="${VERSION_TAG:-V10}"
RUN_MAX_FILES="${RUN_MAX_FILES:-1500}"
RUN_EXTENSIONS="${RUN_EXTENSIONS:-md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt}"
HISTORY_MAX_FILES="${HISTORY_MAX_FILES:-12}"
KEEP_LAST_RUNS="${KEEP_LAST_RUNS:-12}"
PERSIST_CYCLE_ARTIFACTS="${PERSIST_CYCLE_ARTIFACTS:-0}"
VERIFY_SCOPE="${VERIFY_SCOPE:-recent}"
VERIFY_MAX_FILES="${VERIFY_MAX_FILES:-6}"
DEBATE_ROUNDS="${DEBATE_ROUNDS:-2}"
RUN_CYCLES="${RUN_CYCLES:-1}"
VERIFY_ROUNDS="${VERIFY_ROUNDS:-3}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-8}"
VERIFY_RETRY_DELAY="${VERIFY_RETRY_DELAY:-1.2}"
BASELINE_SOURCE_FILES="${BASELINE_SOURCE_FILES:-$PROJECT_ROOT/research_reports/V9_대화흐름혁신_업무자동화_신뢰성강화/research_sources.json}"

PIPELINE_STAGES="${PIPELINE_STAGES:-analysis,deliberation,execution}"
PIPELINE_ALLOWED_SERVICES="${PIPELINE_ALLOWED_SERVICES:-b2b,b2b-android,b2c,ai,telecom,docs}"
PIPELINE_SERVICES="${PIPELINE_SERVICES:-}"
PIPELINE_FEATURES="${PIPELINE_FEATURES:-}"
ORCHESTRATION_PROFILE="${ORCHESTRATION_PROFILE:-${ORA_RD_ORCHESTRATION_PROFILE:-standard}}"
LLM_DELIBERATION_CMD="${LLM_DELIBERATION_CMD:-${PIPELINE_PLANNER_CMD:-}}"
LLM_DELIBERATION_TIMEOUT="${LLM_DELIBERATION_TIMEOUT:-45}"
LLM_CONSENSUS_CMD="${LLM_CONSENSUS_CMD:-${ORA_RD_LLM_CONSENSUS_CMD:-}}"
LLM_CONSENSUS_TIMEOUT="${LLM_CONSENSUS_TIMEOUT:-45}"

PIPELINE_EXECUTION_COMMAND="${PIPELINE_EXECUTION_COMMAND:-}"
PIPELINE_ROLLBACK_COMMAND="${PIPELINE_ROLLBACK_COMMAND:-}"
PIPELINE_RETRY_MAX="${PIPELINE_RETRY_MAX:-2}"
PIPELINE_RETRY_DELAY="${PIPELINE_RETRY_DELAY:-1.2}"
PIPELINE_FAIL_DEFAULT="${PIPELINE_FAIL_DEFAULT:-RETRY}"

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

is_true() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
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

select_service_scope() {
  if [ -n "${PIPELINE_SERVICES}" ]; then
    printf '%s' "${PIPELINE_SERVICES}"
  else
    printf '%s' "${PIPELINE_ALLOWED_SERVICES}"
  fi
}

extract_fail_labels() {
  local json_path="$1"
  "${PYTHON_BIN}" - "$json_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("")
    raise SystemExit(0)
payload = json.loads(path.read_text(encoding="utf-8"))
labels = []
for item in payload.get("orchestration", {}).get("pipeline_decisions", []):
    label = str(item.get("fail_label", "")).strip().upper()
    if label:
        labels.append(label)
print(",".join(labels))
PY
}

resolve_global_fail_label() {
  local labels="$1"
  local normalized="$(printf '%s' "${labels}" | tr '[:lower:]' '[:upper:]')"
  if echo "${normalized}" | grep -q "STOP"; then
    echo "STOP"
    return 0
  fi
  if echo "${normalized}" | grep -q "RETRY"; then
    echo "RETRY"
    return 0
  fi
  if echo "${normalized}" | grep -q "SKIP"; then
    echo "SKIP"
    return 0
  fi
  echo "${PIPELINE_FAIL_DEFAULT}"
}

run_execution_step() {
  local fail_label="$1"
  local cycle="$2"
  if [ -z "${PIPELINE_EXECUTION_COMMAND}" ]; then
    echo "[cycle ${cycle}] [execution] command not configured (PIPELINE_EXECUTION_COMMAND empty)"
    return 0
  fi
  case "${fail_label}" in
    SKIP)
      echo "[cycle ${cycle}] [execution] fail_label=SKIP -> execution skipped"
      return 0
      ;;
    RETRY)
      local attempt=1
      while [ "${attempt}" -le "${PIPELINE_RETRY_MAX}" ]; do
        echo "[cycle ${cycle}] [execution] RETRY attempt=${attempt}/${PIPELINE_RETRY_MAX}"
        if bash -lc "${PIPELINE_EXECUTION_COMMAND}"; then
          echo "[cycle ${cycle}] [execution] success"
          return 0
        fi
        attempt=$((attempt + 1))
        if [ "${attempt}" -le "${PIPELINE_RETRY_MAX}" ]; then
          sleep "${PIPELINE_RETRY_DELAY}"
        fi
      done
      echo "[cycle ${cycle}] [execution] failed after retry limit"
      if [ -n "${PIPELINE_ROLLBACK_COMMAND}" ]; then
        echo "[cycle ${cycle}] [execution] running rollback"
        bash -lc "${PIPELINE_ROLLBACK_COMMAND}" || true
      fi
      return 1
      ;;
    STOP)
      echo "[cycle ${cycle}] [execution] fail_label=STOP -> stop execution"
      if [ -n "${PIPELINE_ROLLBACK_COMMAND}" ]; then
        echo "[cycle ${cycle}] [execution] running rollback"
        bash -lc "${PIPELINE_ROLLBACK_COMMAND}" || true
      fi
      return 1
      ;;
    *)
      echo "[cycle ${cycle}] [execution] unknown fail label=${fail_label}, using single-run"
      bash -lc "${PIPELINE_EXECUTION_COMMAND}"
      ;;
  esac
}

cycle=1
while [ "${cycle}" -le "${RUN_CYCLES}" ]; do
  FOCUS_SLUG="$(sanitize_focus "${FOCUS}")"
  RUN_ROOT="${OUTPUT_ROOT}/${RUN_NAME}"
  if [ -n "${FOCUS}" ]; then
    RUN_ROOT="${RUN_ROOT}/${FOCUS_SLUG}"
  fi

  TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
  OUT_DIR="${RUN_ROOT}/${TIMESTAMP}"
  # Directory is created by the Python pipeline (output_dir.mkdir) only when
  # there is actual content to write — avoids leftover empty directories.

  HISTORY_ARGS=()
  while IFS= read -r -d '' path; do
    HISTORY_ARGS+=("${path}")
  done < <(find "${OUTPUT_ROOT}" -type f -name "ora_rd_research_report_*.md" -print0)
  if [ "${#HISTORY_ARGS[@]}" -gt "${HISTORY_MAX_FILES}" ]; then
    HISTORY_ARGS=("${HISTORY_ARGS[@]:0:${HISTORY_MAX_FILES}}")
  fi

  SERVICE_SCOPE="$(select_service_scope)"
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
    --orchestration-profile "${ORCHESTRATION_PROFILE}"
    --orchestration-stages "${PIPELINE_STAGES}"
    --service-scope "${SERVICE_SCOPE}"
    --feature-scope "${PIPELINE_FEATURES}"
    --llm-deliberation-timeout "${LLM_DELIBERATION_TIMEOUT}"
    --llm-consensus-timeout "${LLM_CONSENSUS_TIMEOUT}"
  )
  if [ -n "${LLM_DELIBERATION_CMD}" ]; then
    CMD_ARGS+=(--llm-deliberation-cmd "${LLM_DELIBERATION_CMD}")
  fi
  if [ -n "${LLM_CONSENSUS_CMD}" ]; then
    CMD_ARGS+=(--llm-consensus-cmd "${LLM_CONSENSUS_CMD}")
  fi
  if [ "${#HISTORY_ARGS[@]}" -gt 0 ]; then
    CMD_ARGS+=("--history" "${HISTORY_ARGS[@]}")
  fi

  echo "[cycle ${cycle}] [analysis+deliberation] run orchestrator"
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
  echo "[cycle ${cycle}] [done] markdown=${latest_md}"
  echo "[cycle ${cycle}] [done] json=${latest_json}"
  if [ -n "${latest_md}" ] && [ -f "${latest_md}" ]; then
    cp "${latest_md}" "${CANONICAL_REPORT_MD}"
    echo "[cycle ${cycle}] [done] canonical_markdown=${CANONICAL_REPORT_MD}"
  fi

  SOURCE_FILES=()
  if [ -f "${OUT_DIR}/research_sources.json" ]; then
    SOURCE_FILES+=("${OUT_DIR}/research_sources.json")
  fi
  if [ -f "${BASELINE_SOURCE_FILES}" ]; then
    SOURCE_FILES+=("${BASELINE_SOURCE_FILES}")
  fi
  if [ "${VERIFY_SCOPE}" = "all" ] || [ "${VERIFY_SCOPE}" = "recent" ]; then
    while IFS= read -r -d '' path; do
      SOURCE_FILES+=("${path}")
    done < <(find "${OUTPUT_ROOT}" -type f -name "research_sources.json" -print0)
  fi
  if [ "${#SOURCE_FILES[@]}" -gt 0 ]; then
    deduped_sources=()
    for path in "${SOURCE_FILES[@]}"; do
      already_seen=0
      for existing in "${deduped_sources[@]-}"; do
        if [ "${existing}" = "${path}" ]; then
          already_seen=1
          break
        fi
      done
      if [ "${already_seen}" -eq 0 ]; then
        deduped_sources+=("${path}")
      fi
    done
    SOURCE_FILES=("${deduped_sources[@]}")
  fi
  if [ "${VERIFY_SCOPE}" = "recent" ] && [ "${#SOURCE_FILES[@]}" -gt "${VERIFY_MAX_FILES}" ]; then
    SOURCE_FILES=("${SOURCE_FILES[@]:0:${VERIFY_MAX_FILES}}")
  fi
  if [ "${#SOURCE_FILES[@]}" -gt 0 ]; then
    echo "[cycle ${cycle}] [verify] start ${VERIFY_ROUNDS} rounds"
    for source_file in "${SOURCE_FILES[@]}"; do
      echo "[cycle ${cycle}] [verify] ${source_file}"
      "${PYTHON_BIN}" "${PROJECT_ROOT}/scripts/verify_sources.py" \
        --in-place \
        --source "${source_file}" \
        --rounds "${VERIFY_ROUNDS}" \
        --timeout "${VERIFY_TIMEOUT}" \
        --retry-delay "${VERIFY_RETRY_DELAY}" || true
    done
  else
    echo "[cycle ${cycle}] [verify] no source files"
  fi

  fail_labels=""
  if [ -n "${latest_json}" ] && [ -f "${latest_json}" ]; then
    fail_labels="$(extract_fail_labels "${latest_json}")"
  fi
  global_fail_label="$(resolve_global_fail_label "${fail_labels}")"
  if [ -z "${PIPELINE_EXECUTION_COMMAND}" ]; then
    global_fail_label="SKIP"
  fi
  echo "[cycle ${cycle}] [execution] fail-policy=${global_fail_label}"
  if [ -z "${PIPELINE_EXECUTION_COMMAND}" ]; then
    echo "[cycle ${cycle}] [execution] command not configured (PIPELINE_EXECUTION_COMMAND empty)"
  else
    run_execution_step "${global_fail_label}" "${cycle}" || {
      echo "[cycle ${cycle}] [execution] stopped by policy"
      exit 1
    }
  fi

  if is_true "${PERSIST_CYCLE_ARTIFACTS}"; then
    cleanup_old_runs "${RUN_ROOT}" "${KEEP_LAST_RUNS}"
  else
    rm -rf "${OUT_DIR}"
    rmdir "${RUN_ROOT}" 2>/dev/null || true
    rmdir "${OUTPUT_ROOT}/${RUN_NAME}" 2>/dev/null || true
    echo "[cycle ${cycle}] [cleanup] removed cycle artifacts (canonical report kept)"
  fi

  cycle=$((cycle + 1))
  if [ "${cycle}" -le "${RUN_CYCLES}" ]; then
    sleep 1
  fi
done
