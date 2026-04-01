#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
EXECUTION_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation

export AUTORESEARCH_ROOT="$EXECUTION_ROOT"
export AUTORESEARCH_CONTROL_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control
export AUTORESEARCH_GATED_RESULTS_TAG=mar10
export AUTORESEARCH_PLAN_PATH=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/plans/mar10_scalar_0475_fixed_step_confirmation.json
export AUTORESEARCH_STAGE_ID=scalar_0475_fixed_step_confirmation
export AUTORESEARCH_LAUNCHER="$SCRIPT_DIR/run_mar10_scalar_0475_fixed_step_confirmation.sh"
export AUTORESEARCH_TRAIN_CMD="/Users/davidabiera/Projects/team/autoresearch-macos/.venv/bin/python $EXECUTION_ROOT/train.py"

exec python3 "$SCRIPT_DIR/overnight_runner.py" \
  --branch codex/execution-weight-decay-022-scalar-confirmation \
  --best-commit a6a97d3 \
  --best-val 1.380746 \
  --queue /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_scalar_0475_fixed_step_confirmation.jsonl \
  --session-kind repeatability \
  --timeout-seconds 750 \
  --stall-abort-ms 30000 \
  --stall-abort-step-max 20 \
  --stall-abort-count 3 \
  --trust-target-steps 354 \
  --max-experiments 4 \
  "$@"
