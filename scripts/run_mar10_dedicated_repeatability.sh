#!/bin/zsh
set -euo pipefail

export AUTORESEARCH_ROOT=/private/tmp/autoresearch-execution-baseline
export AUTORESEARCH_CONTROL_ROOT=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control
export AUTORESEARCH_TRAIN_CMD='/Users/davidabiera/Projects/team/autoresearch-macos/.venv/bin/python /private/tmp/autoresearch-execution-baseline/train.py'

exec python3 /tmp/autoresearch-reliability/scripts/overnight_runner.py \
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
