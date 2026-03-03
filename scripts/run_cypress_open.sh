#!/usr/bin/env bash
set -euo pipefail

E2E_MODE=open bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_e2e_cypress.sh"
