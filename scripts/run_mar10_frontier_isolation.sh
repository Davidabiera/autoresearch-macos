#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos
RUN_ROOT=$REPO_ROOT/worktrees/frontier-isolation-mar10
RUN_BRANCH=codex/frontier-isolation-mar10
BASE_BRANCH=codex/execution-baseline-mar10
CONTROL_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control
QUEUE_PATH=$CONTROL_ROOT/queues/mar10_frontier_isolation.jsonl

if ! git -C "$RUN_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -e "$RUN_ROOT" ]]; then
    echo "run root exists but is not a git worktree: $RUN_ROOT" >&2
    exit 1
  fi
  git -C "$REPO_ROOT" worktree add -B "$RUN_BRANCH" "$RUN_ROOT" "$BASE_BRANCH"
fi

if [[ "$(git -C "$RUN_ROOT" branch --show-current)" != "$RUN_BRANCH" ]]; then
  echo "unexpected run root branch in $RUN_ROOT" >&2
  exit 1
fi

export AUTORESEARCH_ROOT="$RUN_ROOT"
export AUTORESEARCH_CONTROL_ROOT="$CONTROL_ROOT"
export AUTORESEARCH_GATED_RESULTS_TAG=mar10
export AUTORESEARCH_STAGE_ID=frontier_isolation
export AUTORESEARCH_LAUNCHER="$SCRIPT_DIR/run_mar10_frontier_isolation.sh"
export AUTORESEARCH_TRAIN_CMD="/Users/davidabiera/Projects/team/autoresearch-macos/.venv/bin/python $RUN_ROOT/train.py"

exec python3 "$SCRIPT_DIR/overnight_runner.py" \
  --branch "$RUN_BRANCH" \
  --best-commit 5b486fb \
  --best-val 1.386688 \
  --queue "$QUEUE_PATH" \
  --session-kind repeatability \
  --timeout-seconds 750 \
  --stall-abort-ms 30000 \
  --stall-abort-step-max 20 \
  --stall-abort-count 3 \
  "$@"
