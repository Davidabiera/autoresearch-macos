# `mar24-night` Archival Proof — 2026-04-07

## Decision Context

`autoresearch/mar24-night` is being closed as historical evidence, not kept as an active research lane.

Reason:
- the active frontier is now the `mar10` line, not `mar24-night`
- the root workspace remained on `autoresearch/mar24-night` as carryover, not because that line was still live
- the branch still contains unique tracked history, so archival must preserve durable knowledge before the root workspace is re-homed

## Unique Tracked Content Reviewed

Branch-only tracked content that matters:
- historical closeout narrative:
  - [mar24_night_closeout.md](/Users/davidabiera/Projects/team/autoresearch-macos/docs/reference/workflows/mar24_night_closeout.md)
- parent workflow/process refinements:
  - archive one raw `run.log` per completed run
  - restore only experiment-owned code surfaces on discard/crash rollback
  - preserve `results.tsv` and the learning log during rollback
- experiment-review learning-log entries added during the `mar24-night` loop
- the `mar24-night` `results.tsv` chain and research commit history showing improvement from `1.388021` to `1.378980`

Branch-only tracked content that does **not** survive as active frontier state:
- `train.py` parameter state on `mar24-night`
- any candidate-setting commits on that branch
- the root-workspace handoff file [HANDOFF_mar10.md](/Users/davidabiera/Projects/team/autoresearch-macos/HANDOFF_mar10.md)

Local-only content reviewed but intentionally not preserved as canonical truth:
- raw untracked logs under `logs/overnight/mar24-night/`

## What Is Preserved Into Current Canonical Surfaces

Preserved as durable current-state knowledge:
- the fact that `mar24-night` materially improved the then-current best to `1.378980`
- the fact that it was later superseded by the `mar10` fixed-step control system
- the fact that it is now archival, not active
- the workflow/process lessons:
  - archive per-run raw logs
  - restore only experiment-owned code surfaces on discard/crash rollback
  - preserve `results.tsv` and learning-log state during rollback

Current canonical surfaces carrying that forward:
- [autoresearch_operating_review_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_operating_review_20260407.md)
- [mar24_night_archival_decision_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md)
- the `Autoresearch Experiment Program` Linear project and its closure issues

## What Remains Historical-Only

These remain preserved on the archival branch and are intentionally not promoted into active frontier state:
- the full `mar24-night` research commit chain
- the branch-local `results.tsv` state
- branch-specific learning-log entries beyond the high-level lessons called out above
- the branch-local `train.py` settings used during historical probes

Operational rule:
- if any future work needs these details, use the archival branch as evidence
- do not treat them as live defaults or reopen them without a new explicit issue

## Outcome

This proof closes the preservation requirement:
- unique durable knowledge from `mar24-night` has been identified
- active versus historical-only material is now explicit
- the branch can be archived as evidence without keeping the root workspace on it
