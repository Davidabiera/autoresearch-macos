# Canonical Overnight Evaluation: `mar10`

## Summary

- evaluated branch: `autoresearch/mar10`
- canonical best: `5b486fb` / `1.386688` from `raise unembedding lr to 0.00475`
- current git position: branch `autoresearch/mar10`, `HEAD` `5b486fb`
- ledger rows: `60` total, `6` keeps, `40` discards, `14` crashes
- prior frontier: `f19ef7f` / `1.387882` from `raise matrix lr to 0.046`; improvement to current frontier: `+0.001194`
- latest overnight control run: `21` attempted, `0` keeps, `8` discards, `13` crashes, stopped because `elapsed time reached 4.0 hours`

## Current Frontier Settings

- `TOTAL_BATCH_SIZE` = `32768`
- `DEVICE_BATCH_SIZE` = `16`
- `EMBEDDING_LR` = `0.6`
- `UNEMBEDDING_LR` = `0.00475`
- `MATRIX_LR` = `0.046`
- `SCALAR_LR` = `0.5`
- `WEIGHT_DECAY` = `0.2`
- `ADAM_BETAS` = `(0.8, 0.95)`
- `WARMUP_RATIO` = `0.0`
- `WARMDOWN_RATIO` = `0.5`
- `FINAL_LR_FRAC` = `0.05`
- `DEPTH` = `4`

## What Happened

### Confirmed Additive Wins

- `814dc55` `1.447119` baseline
- `fbb1d57` `1.402182` reduce total batch size to 32768
- `71804ff` `1.395468` raise matrix lr to 0.045
- `9837e67` `1.393572` set final lr frac to 0.05
- `f19ef7f` `1.387882` raise matrix lr to 0.046
- `5b486fb` `1.386688` raise unembedding lr to 0.00475

### Ranked Top Results From Latest Evaluated Band

- `fc7c5e8` `1.386732` `discard` raise weight decay to 0.22 (delta to best: `+0.000044`)
- `cff3339` `1.388004` `discard` lower weight decay to 0.18 (delta to best: `+0.001316`)
- `6dbcf54` `1.388378` `discard` lower scalar lr to 0.475 (delta to best: `+0.001690`)
- `d4abce5` `1.388756` `discard` lower weight decay to 0.19 (delta to best: `+0.002068`)
- `e634d49` `1.389167` `discard` raise weight decay to 0.21 (delta to best: `+0.002479`)

### Nearest Clean Losses

- `fc7c5e8` `1.386732` raise weight decay to 0.22 (delta to best: `+0.000044`)
- `cff3339` `1.388004` lower weight decay to 0.18 (delta to best: `+0.001316`)
- `6dbcf54` `1.388378` lower scalar lr to 0.475 (delta to best: `+0.001690`)
- `d4abce5` `1.388756` lower weight decay to 0.19 (delta to best: `+0.002068`)
- `e634d49` `1.389167` raise weight decay to 0.21 (delta to best: `+0.002479`)

### Non-Informative Outcomes

- timeout: `13` runs (timeout after 600 seconds)

## Coherence Status

- results.tsv: current (`5b486fb` / `1.386688`)
- HEAD: current (`5b486fb` / `1.386688`)
- control state: current (`5b486fb` / `1.386688`)
- control report: current (`5b486fb` / `1.386688`)
- handoff current frontier: stale (`9837e67` / `1.393572` vs canonical `5b486fb` / `1.386688`)

## What We Know Now

- The best observed configuration remains `5b486fb` / `1.386688`.
- The latest evaluated band produced `8` informative outcomes and `13` non-informative outcomes.
- Narrative docs are not canonical; they can lag the ledger and control state.

## Recommended Next Steps

- Branch position: stay on `autoresearch/mar10` at `HEAD`; it already matches the canonical best commit `5b486fb`.
- Process priority: fix timeout/coherence issues before another long overnight; 13 of 21 completed items were watchdog timeouts.
- Next experiment band: resume with `adam_betas_08_096` change adam betas to (0.8, 0.96) (remaining band: ADAM_BETAS: (0.8, 0.96), (0.775, 0.95); WARMDOWN_RATIO: 0.52, 0.48; WARMUP_RATIO: 0.001, 0.0025).

## Inputs Used

- ledger: `results.tsv`
- control state: `worktrees/control/control/state/overnight_mar10.json`
- control report: `worktrees/control/control/reports/overnight_mar10.md`
- handoff: `HANDOFF_mar10.md`
- run notes: `RUN_NOTES_mar10.md`
- beta report: `BETA_REPORT_mar10.md`
