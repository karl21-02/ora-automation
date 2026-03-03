#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"

if [ "${E2E_LIST_ONLY:-0}" = "1" ]; then
  cat <<'EOF'
b2b: OraB2bServer (Gradle e2e tests: com.anbucall.e2e.*)
b2b-android: OraB2bAndroid (Android module unit tests: :app:test)
b2c: OraWebAppFrontend (Node/NPM test command)
ai: OraAiServer (LLM_server/TTS_server pytest)
telecom: OraServer (Gradle tests)
free: ai 호환 alias
EOF
  exit 0
fi

SERVICE="${E2E_SERVICE:-}"
MODE="${E2E_MODE:-run}"
PM="${E2E_PM:-npm}"
TOOL="${E2E_TOOL:-cypress}"
BASE_URL="${E2E_BASE_URL:-}"
CONFIG_FILE="${E2E_CONFIG_FILE:-}"
SPEC_FILE="${E2E_SPEC_FILE:-}"
CMD_OVERRIDE="${E2E_CMD:-}"
PYTEST_ARGS="${E2E_PYTEST_ARGS:-}"
FORCE_CYPRESS="${E2E_FORCE_CYPRESS:-0}"
PROJECT_DIR_OVERRIDE="${E2E_PROJECT_DIR:-}"

if [ -z "$SERVICE" ]; then
  echo "[error] E2E_SERVICE가 비어있습니다. (예: b2b|android|b2c|ai|telecom)"
  exit 1
fi

SERVICE_KEY="$(printf '%s' "$SERVICE" | tr '[:upper:]' '[:lower:]')"

run_shell_command() {
  local project_dir="$1"
  local command="$2"

  if [ ! -d "$project_dir" ]; then
    echo "[error] 디렉토리를 찾을 수 없습니다: $project_dir"
    exit 1
  fi

  echo "[e2e:$SERVICE_KEY] $command"
  (cd "$project_dir" && bash -lc "$command")
}

run_gradle_e2e() {
  local project_dir="$1"
  local task="${2:-test}"
  local test_filter="${3:-}"
  local task_cmd="$task"

  if [ -n "$test_filter" ]; then
    task_cmd="${task_cmd} --tests \"${test_filter}\""
  fi

  if [ -x "${project_dir}/gradlew" ]; then
    run_shell_command "$project_dir" "./gradlew ${task_cmd}"
    return
  fi
  if command -v gradle >/dev/null 2>&1; then
    run_shell_command "$project_dir" "gradle ${task_cmd}"
    return
  fi
  echo "[error] gradle 실행기가 없습니다. ${project_dir}/gradlew 또는 gradle 필요"
  exit 1
}

run_pytest() {
  local project_dir="$1"
  local extra_args="$2"
  local pytest_cmd

  if [ -x "${project_dir}/.venv/bin/pytest" ]; then
    pytest_cmd="${project_dir}/.venv/bin/pytest"
  elif [ -x "${project_dir}/.venv/bin/python" ]; then
    pytest_cmd="${project_dir}/.venv/bin/python -m pytest"
  elif command -v uv >/dev/null 2>&1; then
    pytest_cmd="uv run pytest"
  elif command -v pytest >/dev/null 2>&1; then
    pytest_cmd="pytest"
  elif command -v python3 >/dev/null 2>&1; then
    pytest_cmd="python3 -m pytest"
  else
    echo "[error] pytest 실행 도구를 찾을 수 없습니다. python3/pytest/uv 중 하나가 필요"
    exit 1
  fi

  if [ -z "$extra_args" ]; then
    extra_args="tests"
  fi
  run_shell_command "$project_dir" "${pytest_cmd} ${extra_args}"
}

run_frontend_cypress() {
  local project_dir="$1"
  local cypress_mode="$2"
  if [ "$cypress_mode" = "install" ]; then
    E2E_MODE=install bash "${PROJECT_ROOT}/scripts/run_e2e_cypress.sh"
    return
  fi

  E2E_PROJECT_DIR="$project_dir" \
  E2E_PM="$PM" \
  E2E_MODE="$cypress_mode" \
  E2E_BASE_URL="$BASE_URL" \
  E2E_CONFIG_FILE="$CONFIG_FILE" \
  E2E_SPEC_FILE="$SPEC_FILE" \
  bash "${PROJECT_ROOT}/scripts/run_e2e_cypress.sh"
}

run_frontend_playwright() {
  local project_dir="$1"
  local playwright_mode="$2"
  if [ "$playwright_mode" = "install" ]; then
    E2E_MODE=install bash "${PROJECT_ROOT}/scripts/run_e2e_playwright.sh"
    return
  fi

  E2E_PROJECT_DIR="$project_dir" \
  E2E_PM="$PM" \
  E2E_MODE="$playwright_mode" \
  E2E_BASE_URL="$BASE_URL" \
  E2E_CONFIG_FILE="$CONFIG_FILE" \
  E2E_SPEC_FILE="$SPEC_FILE" \
  bash "${PROJECT_ROOT}/scripts/run_e2e_playwright.sh"
}

case "$SERVICE_KEY" in
  b2b|b2b-server|b2b-backend)
    SERVICE_DIR="${PROJECT_DIR_OVERRIDE:-$WORKSPACE_ROOT/OraB2bServer}"
    if [ -n "$CMD_OVERRIDE" ]; then
      run_shell_command "$SERVICE_DIR" "$CMD_OVERRIDE"
    else
      run_gradle_e2e "$SERVICE_DIR" "test" "com.anbucall.e2e.*"
    fi
    ;;

  b2b-android|android|b2b-app|mobile)
    SERVICE_DIR="${PROJECT_DIR_OVERRIDE:-$WORKSPACE_ROOT/OraB2bAndroid}"
    if [ -n "$CMD_OVERRIDE" ]; then
      run_shell_command "$SERVICE_DIR" "$CMD_OVERRIDE"
    else
      run_gradle_e2e "$SERVICE_DIR" ":app:test"
    fi
    ;;

  b2c|b2c-server|freeform|consumer|webapp)
    SERVICE_DIR="${PROJECT_DIR_OVERRIDE:-$WORKSPACE_ROOT/OraWebAppFrontend}"
    if [ -n "$CMD_OVERRIDE" ]; then
      run_shell_command "$SERVICE_DIR" "$CMD_OVERRIDE"
    else
      if [ "$FORCE_CYPRESS" = "1" ]; then
        run_frontend_cypress "$SERVICE_DIR" "$MODE"
      elif [ "$TOOL" = "playwright" ]; then
        run_frontend_playwright "$SERVICE_DIR" "$MODE"
      else
        run_shell_command "$SERVICE_DIR" "$PM run test --if-present"
      fi
    fi
    ;;

  ai|free|freeflow|free-talk|voice)
    if [ -n "$CMD_OVERRIDE" ]; then
      SERVICE_DIR="${PROJECT_DIR_OVERRIDE:-$WORKSPACE_ROOT/OraAiServer}"
      run_shell_command "$SERVICE_DIR" "$CMD_OVERRIDE"
      exit 0
    fi
    run_pytest "$WORKSPACE_ROOT/OraAiServer/LLM_server" "$PYTEST_ARGS"
    run_pytest "$WORKSPACE_ROOT/OraAiServer/TTS_server" "$PYTEST_ARGS"
    ;;

  telecom|ora-server|oraserver|call-server|telephony)
    SERVICE_DIR="${PROJECT_DIR_OVERRIDE:-$WORKSPACE_ROOT/OraServer}"
    if [ -n "$CMD_OVERRIDE" ]; then
      run_shell_command "$SERVICE_DIR" "$CMD_OVERRIDE"
    else
      run_gradle_e2e "$SERVICE_DIR"
    fi
    ;;

  *)
    echo "[error] 알 수 없는 서비스: $SERVICE"
    echo "지원 서비스: b2b | android | b2c | ai | telecom"
    exit 1
    ;;
esac
