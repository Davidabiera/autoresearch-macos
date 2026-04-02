# mar10 Hold Window — 2026-04-02

## Decision

- tonight is a hold window
- do not launch a new overnight queue
- `weight_decay_confirmation` already completed cleanly and should not be rerun

## Current Lead

- lead family: plain `WEIGHT_DECAY=0.22`
- latest trusted frontier repeat: `1.384847`
- latest trusted weight decay confirmation `c`: `1.380148`
- latest trusted weight decay confirmation `d`: `1.384010`
- next-run canonical commit/branch: `52769ae` on `codex/execution-weight-decay-022-ridge`

## Why Hold

- the fixed-step confidence step already completed on the baseline lane
- scalar `0.475` is stable but sub-threshold
- scalar `0.48125` is closed
- nearby unembedding reruns are closed
- no justified broad or mixed-axis overnight queue remains for tonight

## Next Actual Experiment

- launcher: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/run_mar10_weight_decay_ridge_fixed_step_bracket.sh`
- branch: `codex/execution-weight-decay-022-ridge`
- queue order:
  1. baseline `0.22` fixed-step repeat `m`
  2. `WEIGHT_DECAY=0.218`
  3. `WEIGHT_DECAY=0.2225`
  4. baseline `0.22` fixed-step repeat `n`
- acceptance rule:
  - all 4 runs must finish cleanly at `354` steps
  - `baseline_spread = abs(m - n) <= 0.0010`
  - review order is `stage_instability`, `inconclusive_drift`, `ridge_promoted`, `ridge_promising`, `ridge_closed`

## Preflight Snapshot

- ridge branch clean: `yes`
- ridge queue shape verified: `yes`
- ridge launcher target verified: `yes`
  - `best_commit 52769ae`
  - `best_val 1.384010`
- live train/orchestrator processes observed: `none at 2026-04-02T00:19:57-0700`
- stale baseline active-run marker: `reconciled to the finished confirmation state`

## Do Not Do

- do not rerun `weight_decay_confirmation`
- do not reopen scalar or unembedding follow-up tonight
- do not start broad mixed-axis search or a soak without an explicit override
