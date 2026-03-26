#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

export AUTORESEARCH_ROOT=/private/tmp/autoresearch-execution-baseline
export AUTORESEARCH_CONTROL_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control
export AUTORESEARCH_GATED_RESULTS_TAG=mar10
export AUTORESEARCH_PLAN_PATH=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/plans/mar10_backend_isolation_then_repeatability.json
export AUTORESEARCH_STAGE_ID=dedicated_repeatability
export AUTORESEARCH_LAUNCHER="$SCRIPT_DIR/run_mar10_dedicated_repeatability.sh"
export AUTORESEARCH_TRAIN_CMD='/Users/davidabiera/Projects/team/autoresearch-macos/.venv/bin/python /private/tmp/autoresearch-execution-baseline/train.py'

exec python3 "$SCRIPT_DIR/overnight_runner.py" \
  --branch codex/execution-baseline-mar10 \
  --best-commit 5b486fb \
  --best-val 1.386688 \
  --queue /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_repeatability_dedicated_session.jsonl \
  --session-kind repeatability \
  --timeout-seconds 750 \
  --stall-abort-ms 30000 \
  --stall-abort-step-max 20 \
  --stall-abort-count 3 \
  "$@"
