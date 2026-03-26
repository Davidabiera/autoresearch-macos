# `mar10` Fixed-Step Reboot Handoff

Current state:

- same-session fixed-step isolation passed
- search remains blocked
- next gate is rebooted dedicated-session fixed-step isolation
- if that passes, fixed-step dedicated repeatability runs automatically from the same launcher

Canonical evidence:

- anchor: `5b486fb / 1.386688`
- same-session fixed-step repeat A: `1.387670`
- same-session fixed-step repeat B: `1.387150`
- same-session fixed-step spread: `0.000520`
- same-session fixed-step mean drift vs anchor: `+0.000722`

Why reboot is still required:

- the next variable under test is fresh session state, not app state
- quitting Codex or updating Codex is not equivalent to resetting OS-level session state, MPS/Metal state, and background session accumulation

After reboot:

1. keep the desktop quiet
2. avoid opening extra apps
3. run:

```bash
/tmp/autoresearch-reliability/scripts/run_mar10_fixed_step_post_reboot.sh
```

What that launcher does:

1. rebooted fixed-step frontier isolation
2. fixed-step dedicated repeatability, but only if rebooted fixed-step isolation passes

Control surface:

```bash
python3 /tmp/autoresearch-reliability/scripts/session_status.py --branch autoresearch/mar10 --target-root /Users/davidabiera/Projects/team/autoresearch-macos --control-root /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control --format md
```

Checkpointed branches:

- reliability: `c8b121a`
- control: `0965c4f`
