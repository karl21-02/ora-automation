#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${E2E_PROJECT_DIR:-$PWD/../OraMainFrontend}"
PM="${E2E_PM:-npm}"
MODE="${E2E_MODE:-open}"
BASE_URL="${E2E_BASE_URL:-}"
CONFIG_FILE="${E2E_CONFIG_FILE:-}"
SPEC_FILE="${E2E_SPEC_FILE:-}"

if [ ! -d "$PROJECT_DIR" ]; then
  echo "[error] E2E project directory not found: $PROJECT_DIR"
  exit 1
fi

if [ ! -f "$PROJECT_DIR/package.json" ]; then
  echo "[error] package.json not found in: $PROJECT_DIR"
  exit 1
fi

case "$PM" in
  npm)
    INSTALL_CMD=(npm install cypress --save-dev)
    ;;
  pnpm)
    INSTALL_CMD=(pnpm add -D cypress)
    ;;
  yarn)
    INSTALL_CMD=(yarn add -D cypress)
    ;;
  *)
    echo "[error] unsupported E2E_PM=$PM (use npm|pnpm|yarn)"
    exit 1
    ;;
esac

cd "$PROJECT_DIR"

echo "[e2e] installing Cypress (mode=${PM}) in $(pwd)"
"${INSTALL_CMD[@]}"

echo "[e2e] cypress install complete"

if [ "$MODE" = "install" ]; then
  exit 0
fi

CYPRESS_ARGS=()
if [ -n "$CONFIG_FILE" ]; then
  CYPRESS_ARGS+=(--config-file "$CONFIG_FILE")
fi
if [ -n "$BASE_URL" ]; then
  CYPRESS_ARGS+=(--config "baseUrl=$BASE_URL")
fi
if [ -n "$SPEC_FILE" ]; then
  CYPRESS_ARGS+=(--spec "$SPEC_FILE")
fi

echo "[e2e] run mode: $MODE"
if [ "$MODE" = "run" ]; then
  npx cypress run "${CYPRESS_ARGS[@]}"
elif [ "$MODE" = "open" ]; then
  npx cypress open "${CYPRESS_ARGS[@]}"
else
  echo "[error] unsupported E2E_MODE=$MODE (use open or run)"
  exit 1
fi
