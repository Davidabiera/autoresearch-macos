#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PLIST_PATH=/Users/davidabiera/Library/LaunchAgents/com.codex.mar10-fixed-step-post-reboot.plist
LOG_PATH=/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/logs/mar10_fixed_step_post_reboot_launch.log

mkdir -p "$(dirname "$LOG_PATH")"

if [[ -f "$PLIST_PATH" ]]; then
  rm -f "$PLIST_PATH"
fi

exec /bin/zsh "$SCRIPT_DIR/run_mar10_fixed_step_post_reboot.sh" >>"$LOG_PATH" 2>&1
