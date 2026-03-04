#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RAW_SERVICES="${QA_SERVICES:-b2b b2b-android b2c ai telecom}"
RETRY_MAX="${QA_RETRY_MAX:-1}"
RETRY_DELAY="${QA_RETRY_DELAY:-1.5}"
FAIL_FAST="${QA_FAIL_FAST:-0}"
OUTPUT_ROOT="${QA_OUTPUT_ROOT:-${PROJECT_ROOT}/research_reports/qa_runs}"
RUN_NAME="${QA_RUN_NAME:-qa_run_$(date +%Y%m%d_%H%M%S)}"

E2E_MODE="${E2E_SERVICE_MODE:-run}"
E2E_TOOL="${E2E_TOOL:-cypress}"
E2E_PM="${E2E_PM:-npm}"
E2E_BASE_URL="${E2E_BASE_URL:-}"
E2E_CONFIG_FILE="${E2E_CONFIG_FILE:-}"
E2E_SPEC_FILE="${E2E_SPEC_FILE:-}"
E2E_CMD="${E2E_CMD:-}"
E2E_PYTEST_ARGS="${E2E_PYTEST_ARGS:-}"
E2E_FORCE_CYPRESS="${E2E_FORCE_CYPRESS:-0}"

if ! [[ "$RETRY_MAX" =~ ^[0-9]+$ ]] || [ "$RETRY_MAX" -lt 1 ]; then
  echo "[qa] QA_RETRY_MAX must be an integer >= 1"
  exit 2
fi

RUN_DIR="${OUTPUT_ROOT}/${RUN_NAME}"
mkdir -p "${RUN_DIR}"

RESULT_TSV="${RUN_DIR}/results.tsv"
SUMMARY_MD="${RUN_DIR}/qa_summary.md"
SUMMARY_JSON="${RUN_DIR}/qa_summary.json"
touch "${RESULT_TSV}"

STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date +%s)"

IFS=$'\n' read -r -d '' -a SERVICES < <(printf '%s' "${RAW_SERVICES}" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sed '/^$/d' && printf '\0')

if [ "${#SERVICES[@]}" -eq 0 ]; then
  echo "[qa] no services resolved from QA_SERVICES='${RAW_SERVICES}'"
  exit 2
fi

overall=0

for service in "${SERVICES[@]}"; do
  service_safe="$(printf '%s' "${service}" | tr '/ ' '__')"
  service_start="$(date +%s)"
  status="FAILED"
  last_exit=1
  used_attempts=0

  for attempt in $(seq 1 "${RETRY_MAX}"); do
    used_attempts="${attempt}"
    log_file="${RUN_DIR}/${service_safe}_attempt${attempt}.log"
    echo "[qa] service=${service} attempt=${attempt}/${RETRY_MAX}"

    if (
      cd "${PROJECT_ROOT}" && \
      E2E_SERVICE="${service}" \
      E2E_SERVICE_MODE="${E2E_MODE}" \
      E2E_TOOL="${E2E_TOOL}" \
      E2E_PM="${E2E_PM}" \
      E2E_BASE_URL="${E2E_BASE_URL}" \
      E2E_CONFIG_FILE="${E2E_CONFIG_FILE}" \
      E2E_SPEC_FILE="${E2E_SPEC_FILE}" \
      E2E_CMD="${E2E_CMD}" \
      E2E_PYTEST_ARGS="${E2E_PYTEST_ARGS}" \
      E2E_FORCE_CYPRESS="${E2E_FORCE_CYPRESS}" \
      bash "${PROJECT_ROOT}/scripts/run_e2e_service.sh"
    ) >"${log_file}" 2>&1; then
      status="OK"
      last_exit=0
      break
    else
      last_exit=$?
      if [ "${attempt}" -lt "${RETRY_MAX}" ]; then
        sleep "${RETRY_DELAY}"
      fi
    fi
  done

  service_end="$(date +%s)"
  duration_sec="$((service_end - service_start))"
  final_log="${RUN_DIR}/${service_safe}_attempt${used_attempts}.log"

  printf "%s\t%s\t%s\t%s\t%s\t%s\n" \
    "${service}" "${status}" "${used_attempts}" "${duration_sec}" "${last_exit}" "${final_log}" >> "${RESULT_TSV}"

  if [ "${status}" != "OK" ]; then
    overall=1
    if [ "${FAIL_FAST}" = "1" ]; then
      echo "[qa] fail-fast: stop on service=${service}"
      break
    fi
  fi
done

FINISHED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
END_EPOCH="$(date +%s)"
TOTAL_DURATION="$((END_EPOCH - START_EPOCH))"

{
  echo "# QA 실행 리포트"
  echo
  echo "- run_name: \`${RUN_NAME}\`"
  echo "- started_at_utc: \`${STARTED_AT_UTC}\`"
  echo "- finished_at_utc: \`${FINISHED_AT_UTC}\`"
  echo "- total_duration_sec: \`${TOTAL_DURATION}\`"
  echo "- overall: \`$([ "${overall}" -eq 0 ] && echo SUCCESS || echo FAILED)\`"
  echo "- services: \`${RAW_SERVICES}\`"
  echo
  echo "| service | status | attempts | duration_sec | exit_code | log |"
  echo "|---|---|---:|---:|---:|---|"
  while IFS=$'\t' read -r svc stat att dur code logf; do
    echo "| ${svc} | ${stat} | ${att} | ${dur} | ${code} | \`${logf}\` |"
  done < "${RESULT_TSV}"
} > "${SUMMARY_MD}"

python3 - "${RESULT_TSV}" "${SUMMARY_JSON}" "${RUN_NAME}" "${STARTED_AT_UTC}" "${FINISHED_AT_UTC}" "${TOTAL_DURATION}" "${RAW_SERVICES}" "${overall}" <<'PY'
import json
import pathlib
import sys

results_tsv = pathlib.Path(sys.argv[1])
summary_json = pathlib.Path(sys.argv[2])
run_name = sys.argv[3]
started_at = sys.argv[4]
finished_at = sys.argv[5]
total_duration = int(sys.argv[6])
services_raw = sys.argv[7]
overall = "SUCCESS" if int(sys.argv[8]) == 0 else "FAILED"

items = []
for line in results_tsv.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    service, status, attempts, duration_sec, exit_code, log_path = line.split("\t")
    items.append(
        {
            "service": service,
            "status": status,
            "attempts": int(attempts),
            "duration_sec": int(duration_sec),
            "exit_code": int(exit_code),
            "log_path": log_path,
        }
    )

summary = {
    "run_name": run_name,
    "started_at_utc": started_at,
    "finished_at_utc": finished_at,
    "total_duration_sec": total_duration,
    "overall": overall,
    "services_raw": services_raw,
    "results": items,
}

summary_json.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY

ln -sfn "${RUN_DIR}" "${OUTPUT_ROOT}/latest"

echo "[qa] summary md : ${SUMMARY_MD}"
echo "[qa] summary json: ${SUMMARY_JSON}"
echo "[qa] latest symlink: ${OUTPUT_ROOT}/latest"

exit "${overall}"
