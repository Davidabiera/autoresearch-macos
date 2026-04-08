# mar10 Frontier Declaration — 2026-04-02

## Canonical Frontier

- frontier branch: `codex/execution-weight-decay-022-unembedding-followup`
- frontier commit: `52769ae`
- frontier `val_bpb`: `1.384010`
- trust status: `passed`
- trust evidence report: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10/reports/overnight_execution-baseline-mar10.md`

## Why This Is Canonical

- the weight-decay ridge bracket is closed
- plain `WEIGHT_DECAY=0.22` remains the surviving lead family
- no nearby scalar, unembedding, or ridge follow-up survived review strongly enough to replace this commit

## Current Closeouts

- scalar `0.475`: `promising` but sub-threshold
- scalar `0.48125`: `closed`
- unembedding follow-up: `closed`
- weight-decay ridge bracket: `ridge_closed`

## Next Safe Action

- do not rerun the ridge bracket
- use [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_current_state.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_current_state.md) as the current operator entrypoint
- finish M2 control work before choosing `pause/consolidate` or one materially different new axis
- do not treat second-Mac bootstrap notes as the current next-step surface

## Historical Local `frontier.json` Rebuild Note

If a local ledger must be rebuilt later, use this note plus `control/docs/frontier_ledger_template.json` and the current-state index. This is a parked historical reference, not the current operator instruction.

Use these values:
- `frontier_branch = codex/execution-weight-decay-022-unembedding-followup`
- `frontier_commit = 52769ae`
- `frontier_val_bpb = 1.384010`
- `trust_status = passed`
- `trust_evidence_report = /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10/reports/overnight_execution-baseline-mar10.md`
- `next_safe_action = finish M2 control work, then decide pause/consolidation versus one materially different axis`
