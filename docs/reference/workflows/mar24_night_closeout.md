# `mar24-night` Closeout

## Overnight summary

- canonical overnight report: `worktrees/control/control/reports/overnight_mar24-night.md`
- start best: `518a773 / 1.388021`
- end best: `d883544 / 1.378980`
- elapsed hours: `6.45`
- experiments attempted: `50`
- keeps: `3`
- discards: `47`
- crashes: `0`
- stopped because: `max_experiments reached (50)`

## Current branch map

- research branch: `autoresearch/mar24-night` at `befa711`
  - daytime follow-up probes and rebaseline evidence after the overnight run
- reliability branch: `codex/autoresearch-reliability` at `899ee52`
  - trust-path orchestration, reboot handoff, and backend-isolation status/reporting logic
- control branch: `codex/overnight-control` at `4510df5`
  - canonical `mar10` and `mar24-night` control plans and queues
- execution-baseline branch: `codex/execution-baseline-mar10` at `c7f7325`
  - fixed-step trust-mode training path for the rebooted comparability gate

## Open loop

- the `mar10` post-reboot trust path is still unresolved
- search remains blocked until the fixed-step trust gates pass
- latest durable runtime-forensics evidence stops at same-session fixed-step frontier isolation
- the March 28 reboot does not count as a successful trust-path run because the staged LaunchAgent pointed at a `/tmp` wrapper that disappeared across reboot

## What not to trust

- raw local runtime logs under `logs/overnight/mar24-night/`
- dirty-workspace or manual signals outside the controlled gate path
- single attractive numbers that were not produced under the fixed-step trust protocol
- untracked local lockfiles, runtime state, and ad hoc handoff files

## GitHub closeout intent

- publish the active research, reliability, control, and execution-baseline branches to the `github` fork
- keep branches separate; do not merge support branches into the research branch
- use this document plus the tracked control reports as the durable away-from-local handoff
