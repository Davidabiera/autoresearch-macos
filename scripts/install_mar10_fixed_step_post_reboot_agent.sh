#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
WORKTREE_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PLIST_PATH=/Users/davidabiera/Library/LaunchAgents/com.codex.mar10-fixed-step-post-reboot.plist
LOG_PATH=$WORKTREE_ROOT/logs/mar10_fixed_step_post_reboot_launch.log
WRAPPER_PATH=$SCRIPT_DIR/mar10_fixed_step_post_reboot_once.sh
ARM_STATE_PATH=$WORKTREE_ROOT/state/mar10_fixed_step_post_reboot_arm.env
CURRENT_BOOT_EPOCH=$(sysctl -n kern.boottime | sed -E 's/^\{ sec = ([0-9]+), usec = [0-9]+ \}.*/\1/')

mkdir -p "$(dirname "$PLIST_PATH")"
mkdir -p "$(dirname "$LOG_PATH")"
mkdir -p "$(dirname "$ARM_STATE_PATH")"
: >"$LOG_PATH"

cat >"$ARM_STATE_PATH" <<EOF
ARMED_BOOT_EPOCH=$CURRENT_BOOT_EPOCH
ARMED_AT_ISO=$(date '+%Y-%m-%dT%H:%M:%S%z')
EOF

{
  echo "install_mar10_fixed_step_post_reboot_agent.sh wrote arm state at $(date)"
  echo "armed boot epoch: $CURRENT_BOOT_EPOCH"
  echo "wrapper: $WRAPPER_PATH"
} >>"$LOG_PATH"

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.codex.mar10-fixed-step-post-reboot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>$WRAPPER_PATH</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_PATH</string>
  <key>StandardErrorPath</key>
  <string>$LOG_PATH</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST_PATH" >/dev/null

echo "Wrote $PLIST_PATH"
echo "Wrapper: $WRAPPER_PATH"
echo "Arm state: $ARM_STATE_PATH (boot epoch $CURRENT_BOOT_EPOCH)"
echo "Log path: $LOG_PATH"
echo "Do not bootstrap this LaunchAgent manually. Same-boot auto-load will wait; the real run should begin only after the next reboot/login."
