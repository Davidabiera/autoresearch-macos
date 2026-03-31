#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKTREE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PLIST_PATH=/Users/davidabiera/Library/LaunchAgents/com.codex.mar10-fixed-step-post-reboot.plist
LOG_PATH=$WORKTREE_ROOT/logs/mar10_fixed_step_post_reboot_launch.log
ARM_STATE_PATH=$WORKTREE_ROOT/state/mar10_fixed_step_post_reboot_arm.env

mkdir -p "$(dirname "$LOG_PATH")"
mkdir -p "$(dirname "$ARM_STATE_PATH")"

CURRENT_BOOT_EPOCH=$(sysctl -n kern.boottime | sed -E 's/.*sec = ([0-9]+).*/\1/')
if [[ -z "$CURRENT_BOOT_EPOCH" ]]; then
  {
    echo "mar10_fixed_step_post_reboot_once fired at $(date)"
    echo "failed to determine current boot epoch"
  } >>"$LOG_PATH"
  exit 1
fi

if [[ ! -f "$ARM_STATE_PATH" ]]; then
  {
    echo "mar10_fixed_step_post_reboot_once fired at $(date)"
    echo "missing arm state: $ARM_STATE_PATH"
    echo "preserving LaunchAgent for manual inspection"
  } >>"$LOG_PATH"
  exit 1
fi

source "$ARM_STATE_PATH"

{
  echo "mar10_fixed_step_post_reboot_once fired at $(date)"
  echo "launch wrapper: $0"
  echo "runner: $SCRIPT_DIR/run_mar10_fixed_step_post_reboot.sh"
  echo "armed boot epoch: ${ARMED_BOOT_EPOCH:-unknown}"
  echo "current boot epoch: $CURRENT_BOOT_EPOCH"
} >>"$LOG_PATH"

if [[ -z "${ARMED_BOOT_EPOCH:-}" ]]; then
  {
    echo "arm state is missing ARMED_BOOT_EPOCH"
    echo "preserving LaunchAgent for manual inspection"
  } >>"$LOG_PATH"
  exit 1
fi

if (( CURRENT_BOOT_EPOCH <= ARMED_BOOT_EPOCH )); then
  {
    echo "same-boot load detected; waiting for a later reboot before consuming the one-shot agent"
  } >>"$LOG_PATH"
  exit 0
fi

if [[ -f "$PLIST_PATH" ]]; then
  rm -f "$PLIST_PATH"
fi

rm -f "$ARM_STATE_PATH"

exec /bin/zsh "$SCRIPT_DIR/run_mar10_fixed_step_post_reboot.sh" >>"$LOG_PATH" 2>&1
