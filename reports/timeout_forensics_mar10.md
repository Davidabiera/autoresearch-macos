# Timeout Forensics: `mar10`

Operational report. This file documents runner behavior and timing evidence. It is not a frontier or ledger artifact.

## Findings

- Clean informative runs land around `470s` to `480s` total wall time because validation adds roughly `160s` after the `300s` training budget.
- `training_seconds` understates full training wall time because the first `11` steps are counted as warmup and excluded from the steady-state training total.
- The historical timeout backlog splits into:
  - `1` `late-timeout`
  - `3` `early-step-stall`
  - `9` `startup-hang`
- The old `uv`-wrapped timeout path is the most likely cause of the contamination cascade because killing the wrapper can strand the child Python trainer process.

## Runtime Split

Observed from the instrumented gate run family:

- healthy training budget: about `300.6s` to `300.7s`
- warmup segment excluded from `training_seconds`: about `10.7s` to `14.3s`
- evaluation tail: about `157.8s` to `164.8s`
- total wall time: about `469.9s` to `480.7s`

Interpretation:

- A clean run already consumes most of a `600s` watchdog budget.
- The remaining slack is too small to tolerate a large late step or a contaminated runner state.

## Timeout Taxonomy

Historical `overnight_mar10` control backlog, classified with the current deterministic classifier:

- `late-timeout`
  - timeout after the training budget was effectively exhausted
  - representative symptom: last logged `remaining: 0s`
- `early-step-stall`
  - timeout after a giant step-0 or step-1 latency spike
  - representative symptom: early `dt` in the `164s` to `526s` range
- `startup-hang`
  - timeout before any usable training-step progress
  - representative symptom: timeout marker with no step log, or startup output only

Informative outcomes from the same historical control window classified as `post-train-overrun`: `8`.

## Root Cause Assessment

The strongest runner-level failure mechanism is orphaned trainer processes created by the old timeout path:

- the old runner launched training through `uv`, which stayed as a parent wrapper
- killing the wrapper on timeout did not reliably kill the child Python process
- a surviving child process could continue consuming device/runtime resources after the runner believed the job had ended

This fits the observed progression:

- one late timeout
- then degraded early-step stalls
- then pure startup-hang failures

Sleep, thermal, and memory-pressure evidence did not support those as primary causes during the timeout window.

## Verification After Runner Fix

After replacing the timeout behavior with direct Python execution and full process-group termination, historically bad items reran as informative discards instead of hanging:

- `embedding_lr_0625`
  - class: `post-train-overrun`
  - `val_bpb`: `1.393760`
  - `training_seconds`: `300.7`
  - `eval_seconds`: `164.8`
  - `total_seconds`: `480.7`
  - `stall_trace`: absent
- `adam_betas_081_095`
  - class: `post-train-overrun`
  - `val_bpb`: `1.387974`
  - `training_seconds`: `300.6`
  - `eval_seconds`: `157.8`
  - `total_seconds`: `469.9`
  - `stall_trace`: absent

Interpretation:

- the runner fix appears to eliminate the historical `startup-hang` and `early-step-stall` behavior for these reproduced cases
- the remaining operational issue is the evaluation tail, not runner contamination

## Operational Default

- use the process-group-safe runner path
- run new experiments as `1`-item gates from a clean execution worktree
- use `STALL_TRACE_THRESHOLD_MS=30000`
- use a timeout budget above `600s` while the validation tail remains unchanged
