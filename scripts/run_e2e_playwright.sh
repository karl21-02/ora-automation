#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${E2E_PROJECT_DIR:-$PWD/../OraMainFrontend}"
PM="${E2E_PM:-npm}"
MODE="${E2E_MODE:-run}"
BASE_URL="${E2E_BASE_URL:-}"
CONFIG_FILE="${E2E_CONFIG_FILE:-}"
SPEC_FILE="${E2E_SPEC_FILE:-}"
INSTALL_BROWSERS="${E2E_INSTALL_BROWSERS:-1}"

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
    INSTALL_CMD=(npm install -D @playwright/test)
    ;;
  pnpm)
    INSTALL_CMD=(pnpm add -D @playwright/test)
    ;;
  yarn)
    INSTALL_CMD=(yarn add -D @playwright/test)
    ;;
  *)
    echo "[error] unsupported E2E_PM=$PM (use npm|pnpm|yarn)"
    exit 1
    ;;
esac

cd "$PROJECT_DIR"

echo "[e2e-playwright] installing @playwright/test (pm=$PM) in $(pwd)"
"${INSTALL_CMD[@]}"

if [ "$INSTALL_BROWSERS" = "1" ]; then
  echo "[e2e-playwright] installing browser binaries"
  npx playwright install
fi

if [ "$MODE" = "install" ]; then
  exit 0
fi

PLAYWRIGHT_ARGS=()
if [ -n "$CONFIG_FILE" ]; then
  PLAYWRIGHT_ARGS+=(--config "$CONFIG_FILE")
fi
if [ -n "$SPEC_FILE" ]; then
  PLAYWRIGHT_ARGS+=("$SPEC_FILE")
fi

if [ "$MODE" = "run" ]; then
  if [ -n "$BASE_URL" ]; then
    BASE_URL="$BASE_URL" npx playwright test "${PLAYWRIGHT_ARGS[@]}"
  else
    npx playwright test "${PLAYWRIGHT_ARGS[@]}"
  fi
elif [ "$MODE" = "open" ]; then
  if [ -n "$BASE_URL" ]; then
    BASE_URL="$BASE_URL" npx playwright test --ui "${PLAYWRIGHT_ARGS[@]}"
  else
    npx playwright test --ui "${PLAYWRIGHT_ARGS[@]}"
  fi
else
  echo "[error] unsupported E2E_MODE=$MODE (use open, run, install)"
  exit 1
fi
