# Stability-First Resume: `mar10`

Operational protocol. This file defines the next execution block and branching rules.

## Current Position

- canonical frontier remains `5b486fb / 1.386688`
- runner contamination is fixed
- repeatability is still failing
- the current single baseline signal probe is not the proof run; it exists only to confirm whether instability reproduces from a clean worktree

## Dedicated-Session Protocol

Before the next proof run:

1. reboot the Mac
2. close Chrome
3. close Adobe Acrobat and Adobe Desktop Service
4. close Messages
5. avoid active desktop use during the run
6. run only from a clean disposable worktree rooted at the execution baseline
7. write the reboot LaunchAgent to disk first with `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/install_mar10_fixed_step_post_reboot_agent.sh`
8. the installer arms the current boot epoch; same-boot auto-load must only log and wait
9. do not manually `bootstrap` the LaunchAgent before reboot; it must fire only after login

Runner defaults:

- `--session-kind repeatability`
- `--timeout-seconds 750`
- `--stall-abort-ms 30000`
- `--stall-abort-step-max 20`
- `--stall-abort-count 3`

Launch helper:

- `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/run_mar10_dedicated_repeatability.sh`

## Queues

- dedicated-session repeatability block:
  - `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_repeatability_dedicated_session.jsonl`
- weight-decay confirmation block:
  - `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_weight_decay_confirmation.jsonl`
- scalar-first canary:
  - `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_scalar_first_canary.jsonl`
- scalar follow-up extension:
  - `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/queues/mar10_scalar_followup_extension.jsonl`

## Decision Rules

Fail the environment immediately if any repeatability run:

- stall-aborts
- times out
- finishes with `num_steps < 300`

Treat the environment as stable only if:

- both frontier repeats complete cleanly
- frontier repeat spread is `<= 0.0010`
- neither frontier run shows repeated early stalls

After the dedicated-session block:

- if the environment is unstable:
  - pause all hyperparameter search
  - open backend/environment investigation
- if the environment is stable and `WEIGHT_DECAY=0.22` mean beats frontier mean by `> 0.0010`:
  - run the weight-decay confirmation block
- if the environment is stable and `WEIGHT_DECAY=0.22` does not beat frontier mean by `> 0.0010`:
  - close weight decay
  - launch the scalar-first canary

## Overnight Re-entry

Do not schedule a full overnight until both are true:

- one clean dedicated-session repeatability block has passed
- one clean 2-item canary on the next chosen axis has passed
