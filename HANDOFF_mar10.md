# Handoff: `autoresearch/mar10`

Derived artifact. Canonical precedence:
1. `results.tsv`
2. control state JSON
3. control report Markdown
4. narrative Markdown

## Current Frontier

- Branch: `autoresearch/mar10`
- Best commit: `5b486fb`
- Best `val_bpb`: `1.386688`
- Branch HEAD: `5b486fb`
- Rollback target: `5b486fb`

## Canonical Artifacts

- Ledger: `results.tsv`
- Control state: `worktrees/control/control/state/overnight_mar10.json`
- Control report: `worktrees/control/control/reports/overnight_mar10.md`

## Confirmed Additive Wins

- `814dc55` `1.447119` baseline
- `fbb1d57` `1.402182` reduce total batch size to 32768
- `71804ff` `1.395468` raise matrix lr to 0.045
- `9837e67` `1.393572` set final lr frac to 0.05
- `f19ef7f` `1.387882` raise matrix lr to 0.046
- `5b486fb` `1.386688` raise unembedding lr to 0.00475

## Nearest Clean Losses

- `fc7c5e8` `1.386732` raise weight decay to 0.22 (delta `+0.000044`)
- `cff3339` `1.388004` lower weight decay to 0.18 (delta `+0.001316`)
- `6dbcf54` `1.388378` lower scalar lr to 0.475 (delta `+0.001690`)
- `d4abce5` `1.388756` lower weight decay to 0.19 (delta `+0.002068`)
- `e634d49` `1.389167` raise weight decay to 0.21 (delta `+0.002479`)

## Remaining Queue

- `adam_betas_08_096` change adam betas to (0.8, 0.96)
- `adam_betas_0775_095` change adam betas to (0.775, 0.95)
- `warmdown_ratio_052` lengthen warmdown ratio to 0.52
- `warmdown_ratio_048` shorten warmdown ratio to 0.48
- `warmup_ratio_0001` add warmup ratio of 0.001
- `warmup_ratio_00025` add warmup ratio of 0.0025

## Operational Blockers

- [warning] handoff: handoff frontier is stale (`9837e67` / `1.393572`)
- [warning] git-status: worktree is not clean (17 pending entries)

## Latest Control Window

- attempted: `21`
- keeps: `0`
- discards: `8`
- crashes: `13`
- stopped because: `elapsed time reached 4.0 hours`
