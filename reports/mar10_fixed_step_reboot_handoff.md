# `mar10` Fixed-Step Reboot Handoff

Current state:

- same-session fixed-step isolation passed
- search remains blocked
- next gate is rebooted dedicated-session fixed-step isolation
- if that passes, fixed-step dedicated repeatability runs automatically from the same launcher
- the latest reboot attempt was invalid launch orchestration, not a frontier result
- the pre-reboot manual load path fired the one-shot wrapper before reboot, deleted the plist, and left no real post-reboot stage execution

Canonical evidence:

- anchor: `5b486fb / 1.386688`
- same-session fixed-step repeat A: `1.387670`
- same-session fixed-step repeat B: `1.387150`
- same-session fixed-step spread: `0.000520`
- same-session fixed-step mean drift vs anchor: `+0.000722`

Why reboot is still required:

- the next variable under test is fresh session state, not app state
- quitting Codex or updating Codex is not equivalent to resetting OS-level session state, MPS/Metal state, and background session accumulation

Before reboot:

1. keep the desktop quiet
2. write the one-shot LaunchAgent to disk only:

```bash
/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/install_mar10_fixed_step_post_reboot_agent.sh
```

3. the installer records the current boot epoch; if launchd loads the agent in the same boot, the wrapper logs and exits without consuming itself
4. do not manually `bootstrap` or otherwise load the LaunchAgent
5. reboot the Mac
6. avoid opening extra apps after login

What the post-reboot launcher does:

1. rebooted fixed-step frontier isolation
2. fixed-step dedicated repeatability, but only if rebooted fixed-step isolation passes
3. if rebooted fixed-step isolation fails, it now runs a same-boot frontier-only replay to separate cold-session effects from persistent runtime drift

Review checks for the next attempt:

1. before reboot:
   - plist exists at `~/Library/LaunchAgents/com.codex.mar10-fixed-step-post-reboot.plist`
   - arm state exists at `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/state/mar10_fixed_step_post_reboot_arm.env`
   - plist points at the repo-local once wrapper
   - no active `mar10` orchestrator or repeatability process is live
2. after reboot/login:
   - launch log is non-empty and newly timestamped
   - launch log shows a boot epoch newer than the armed boot epoch
   - `session_status.py` shows fresh timestamps rather than stale interrupted-only state
   - `attempted > 0` or a completed stage appears
   - a fresh runtime-forensics bundle is created

Decision ladder:

1. rebooted frontier pair passes only if:
   - both repeats hit `354` steps
   - both emit full completion markers through `post_summary`
   - both emit `completion_result`
   - no timeout, no stall-abort, no truncation, no completion error
   - spread `<= 0.0010`
   - mean drift vs `1.386688` `<= 0.0010`
2. if rebooted frontier fails and the same-boot replay passes:
   - cold-session or session-initialization effects are the leading hypothesis
   - search stays blocked
3. if rebooted frontier fails and the same-boot replay fails:
   - persistent MPS/runtime drift is the leading hypothesis
   - search stays blocked
4. if rebooted frontier passes but fixed-step dedicated repeatability fails:
   - frontier-only trust improved
   - `WEIGHT_DECAY=0.22` stays unresolved
   - search stays blocked
5. if fixed-step dedicated repeatability passes:
   - confirm `WEIGHT_DECAY=0.22` only if `weight_decay_mean < frontier_mean - 0.0010`
   - otherwise discard `WEIGHT_DECAY=0.22` as the next candidate
   - only then is a bounded day-2 canary earned

Control surface:

```bash
python3 /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/session_status.py --branch autoresearch/mar10 --target-root /Users/davidabiera/Projects/team/autoresearch-macos --control-root /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control --format md
```

Checkpointed logic:

- reliability trust-path logic: `bc6104c`
- control trust-path plan: `28154fc`
