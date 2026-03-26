# Runtime/MPS Forensics: `mar10`

Operational report. This file documents repeatability failure, not frontier truth.

## Findings

- The `WEIGHT_DECAY` fine overnight was empty. Best of that band was `weight_decay_02225 -> 1.388087`, still worse than the frontier `1.386688`.
- The repeatability block invalidated further search. Canonical frontier repeats were not stable enough to support new-axis exploration.
- `frontier_repeat_a` collapsed after step `8` and finished at `2.244121`.
- `frontier_repeat_b` ran normally and finished at `1.392134`.
- `WEIGHT_DECAY=0.22` repeats were materially tighter than the frontier repeats, but still worse than the frontier:
  - `1.389019`
  - `1.387159`

## Repeatability Results

- canonical frontier: `5b486fb / 1.386688`
- `frontier_repeat_a`
  - `val_bpb`: `2.244121`
  - `training_seconds`: `322.0`
  - `total_seconds`: `654.7`
  - `num_steps`: `14`
- `frontier_repeat_b`
  - `val_bpb`: `1.392134`
  - `training_seconds`: `300.7`
  - `total_seconds`: `471.6`
  - `num_steps`: `342`
- frontier repeat spread: `0.851987`
- `weight_decay_repeat_022_a`
  - `val_bpb`: `1.389019`
  - `training_seconds`: `300.8`
  - `total_seconds`: `470.5`
- `weight_decay_repeat_022_b`
  - `val_bpb`: `1.387159`
  - `training_seconds`: `300.6`
  - `total_seconds`: `469.2`
- weight-decay repeat spread: `0.001860`

## Failure Signature

`frontier_repeat_a` shows the decisive pathological shape:

- steps `0` to `8`: normal `dt` around `0.9s` to `1.4s`
- step `9`: `25.754s`
- step `10`: `81.118s`
- step `11`: `101.609s`
- step `12`: `114.921s`
- step `13`: `105.462s`

Interpretation:

- the run did not fail at startup
- the run did not hit the old watchdog contamination path
- the process entered a severe early-step slowdown inside the training workload itself
- because the same frontier config reran normally in `frontier_repeat_b`, the current issue is reproducibility/runtime stability, not a deterministic hyperparameter defect

## Clean Baseline Signal Probe

A later single-item clean-worktree signal probe reproduced the same failure family even after the runner and worktree were cleaned:

- worktree: `codex/frontier-baseline-stability-mar10`
- queue item: `frontier_repeat_clean_c`
- early step timings observed before completion:
  - step `0`: `51.481s`
  - step `1`: `77.740s`
  - step `2`: `71.106s`

Interpretation:

- the current instability reproduces even from a clean disposable worktree
- that strengthens the local runtime/MPS diagnosis
- this probe is signal only; the next proof run must still be a rebooted dedicated-session repeatability block
- this probe also exposed a runner edge case: when live stall abort attempted a process-group `SIGKILL`, the runner hit a `PermissionError`; the runner now falls back to direct process termination in that case

## Frontier-Only Isolation Results

A later 2-item frontier-only isolation block removed the mixed repeatability queue and reran only the canonical frontier from a clean disposable worktree:

- `frontier_repeat_isolation_a`
  - `val_bpb`: `1.394587`
  - `training_seconds`: `300.5`
  - `total_seconds`: `479.9`
  - `num_steps`: `337`
  - `max_dt_ms`: `9509`
- `frontier_repeat_isolation_b`
  - `val_bpb`: `1.392884`
  - `training_seconds`: `300.6`
  - `total_seconds`: `475.7`
  - `num_steps`: `340`
  - `max_dt_ms`: `2046`
- frontier isolation spread: `0.001703`
- frontier isolation mean: `1.393736`
- anchor delta vs canonical frontier `1.386688`: `+0.007048`

Interpretation:

- catastrophic `30s+` early stalls did not reproduce in the isolation block
- baseline quality still degraded materially relative to the canonical anchor
- the environment therefore remains untrusted even when the run shape looks operationally clean
- search should stay frozen because the system can now produce both:
  - visibly unstable runs
  - superficially clean but materially degraded frontier repeats

## System-Level Evidence

- `pmset -g log` for the repeatability window shows `0` sleep/wake events since boot and no sleep transition during the run
- unified log review for `2026-03-24 19:35` to `20:15` did not show a clear thermal-throttling or explicit MPS fault for the trainer
- the narrow unified-log query did show non-critical memory-pressure chatter in unrelated desktop/WebKit processes with `system vm pressure critical: 0`

Interpretation:

- there is no current evidence that sleep/wake or a global thermal event explains the collapse
- there is weak evidence that desktop memory pressure may be contributing noise, but not enough to attribute the failure conclusively
- the best current explanation is intermittent MPS/runtime instability inside the process under current machine load

## Search Consequence

- pause hyperparameter exploration
- do not launch the prebuilt scalar canary yet
- treat `WEIGHT_DECAY=0.22` as unresolved by reproducibility, but not competitive enough to justify more local search now

## Next Forensics Pass

The next loop is backend/environment isolation, not search:

1. keep hyperparameter search frozen
2. collect only frontier-baseline evidence until two repeats are both:
   - full-length (`num_steps >= 300`)
   - within `0.0010` of `1.386688`
3. before the next baseline run:
   - reboot
   - close Chrome
   - close Adobe Acrobat
   - close Adobe Desktop Service
   - close Messages
   - avoid active desktop use during the run
4. on the next baseline run, capture:
   - `pmset -g log | tail -n 200`
   - `memory_pressure`
   - `ps -Ao pid,etime,command | rg "train.py|overnight_runner.py|python .*train.py"`
   - unified-log slice around the run window for `thermal`, `Jetsam`, `memorystatus`, `MPS`, and `Metal`
5. compare three classes of frontier evidence:
   - visibly unstable: `frontier_repeat_a`, `frontier_repeat_clean_c`, `frontier_repeat_dedicated_b`
   - superficially clean but degraded: `frontier_repeat_dedicated_a`, `frontier_repeat_isolation_a`, `frontier_repeat_isolation_b`
   - historical anchor: canonical frontier `5b486fb / 1.386688`
6. reopen the controlled autonomy loop only after two clean frontier-only repeats satisfy the anchor tolerance

## Operational Default Until Resolved

- keep `750s` timeout budget
- keep process-group-safe runner path
- keep live stall abort enabled for unattended runs
- use `session_status.py` as the single control surface
- treat repeatability as a hard gate before any new overnight exploration
