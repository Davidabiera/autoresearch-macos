#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
EXECUTION_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar

export AUTORESEARCH_ROOT="$EXECUTION_ROOT"
export AUTORESEARCH_CONTROL_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control
export AUTORESEARCH_GATED_RESULTS_TAG=mar10
export AUTORESEARCH_PLAN_PATH=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/plans/mar10_candidate_root_scalar_bracket.json
export AUTORESEARCH_STAGE_ID=scalar_candidate_bracket
export AUTORESEARCH_LAUNCHER="$SCRIPT_DIR/run_mar10_scalar_candidate_bracket.sh"
export AUTORESEARCH_TRAIN_CMD="/Users/davidabiera/Projects/team/autoresearch-macos/.venv/bin/python $EXECUTION_ROOT/train.py"

exec python3 "$SCRIPT_DIR/overnight_runner.py" \
  --branch codex/execution-weight-decay-022-scalar \
  --best-commit 52769ae \
  --best-val 1.384010 \
  --queue /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_scalar_candidate_bracket.jsonl \
  --session-kind repeatability \
  --timeout-seconds 750 \
  --stall-abort-ms 30000 \
  --stall-abort-step-max 20 \
  --stall-abort-count 3 \
  --max-experiments 6 \
  "$@"
