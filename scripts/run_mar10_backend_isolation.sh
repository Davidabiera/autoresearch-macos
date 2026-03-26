#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

exec python3 "$SCRIPT_DIR/session_orchestrator.py" \
  --plan /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/plans/mar10_backend_isolation_then_repeatability.json \
  --mode tonight \
  "$@"
