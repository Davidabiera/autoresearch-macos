# Beta Report: `autoresearch/mar10`

## Status

- Baseline commit: `814dc55`
- Baseline `val_bpb`: `1.447119`
- Current best commit: `9837e67`
- Current best `val_bpb`: `1.393572`
- Post-baseline experiments: `26`
- Keeps: `3`
- Discards: `22`
- Crashes: `1`

## Confirmed Additive Wins

1. Reduce `TOTAL_BATCH_SIZE` from `2**16` to `2**15`.
2. Raise `MATRIX_LR` from `0.04` to `0.045`.
3. Raise `FINAL_LR_FRAC` from `0.0` to `0.05`.

## What This Beta Established

- The repo works end to end on this machine and the keep/discard loop is stable.
- The machine prefers faster update cadence over larger per-step model capacity in the fixed 5-minute regime.
- `FINAL_LR_FRAC = 0.05` is now locally bracketed:
  - `0.025` regressed to `1.395900`
  - `0.04` regressed to `1.399596`
  - `0.06` regressed to `1.394738`
  - `0.075` regressed to `1.394921`
- `WEIGHT_DECAY` reductions remain unattractive in this local region:
  - `0.15` regressed to `1.401963`
  - `0.175` regressed to `1.396012`
- Warmdown is now bracketed as well:
  - `WARMDOWN_RATIO = 0.45` regressed to `1.402610`
  - `WARMDOWN_RATIO = 0.55` regressed to `1.399982`
- A legal cadence probe came close but did not win:
  - `DEVICE_BATCH_SIZE = 8` regressed slightly to `1.394027`
- Warmup still looks hostile even at tiny scale:
  - `WARMUP_RATIO = 0.005` regressed badly to `1.427855`
- One batch-size probe was invalid:
  - `TOTAL_BATCH_SIZE = 16384` hit the divisibility assertion

## Current Reading

The current optimizer region around `9837e67` looks near-local-optimal. That does not mean the repo is exhausted. It means broad optimizer wandering is no longer justified by the evidence.

## Recommended Next Decision

Choose one of these, in order of coherence:

1. Stop and synthesize from the existing artifacts before more runs.
2. If continuing immediately, keep the next band ultra-fine:
   - `MATRIX_LR = 0.044`
   - `MATRIX_LR = 0.046`
   - optionally `DEVICE_BATCH_SIZE = 4`
3. Do not reopen architecture search yet.
