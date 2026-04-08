# mar10 Next-Phase Decision — 2026-04-07

## Decision

- decision: `pause and consolidate`
- parked frontier branch: `codex/execution-weight-decay-022-unembedding-followup`
- parked frontier commit: `52769ae`
- parked frontier `val_bpb`: `1.384010`
- run posture: `no new bounded experiment is approved`

## Why This Is The Default

- `WEIGHT_DECAY=0.22` is still the only confirmed surviving lead
- scalar follow-up is exhausted enough for now:
  - `0.475` was real but sub-threshold
  - `0.48125` closed
- unembedding follow-up closed
- nearby weight-decay ridge closed
- `mar24-night` is archived and no longer participates in active research posture
- no adjacent local axis currently has a stronger case than consolidation

## Evidence

- scalar and unembedding verdict: [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md)
- ridge verdict: [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_weight_decay_ridge_verdict_20260402.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_weight_decay_ridge_verdict_20260402.md)
- operating review: [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_operating_review_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_operating_review_20260407.md)
- archival closeout: [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md)

## Default Operating Posture

- keep `52769ae` parked as the frontier
- keep broad search closed
- do not queue another run by default
- treat current work as consolidation and governance unless a new issue explicitly reopens research

## Reopen Rule

Research reopens only if all of the following are true:

1. Linear names one materially different axis as the next focus.
2. The axis has explicit acceptance criteria and a stronger case than consolidation.
3. The run satisfies [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/run_gating_checklist.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/run_gating_checklist.md).

## Non-Decision Notes

- This decision does not delete or demote the historical evidence lanes.
- This decision does not approve a second Mac path.
- This decision does not approve a new queue package.
