#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

exec "$SCRIPT_DIR/run_mar10_backend_isolation.sh" "$@"
