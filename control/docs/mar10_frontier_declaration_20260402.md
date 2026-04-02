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
- do not open a new experimental axis before the second Mac proves a clean bootstrap and validation pass
- use the next work window to durabilize the control docs, bring up the second Mac at the same absolute path, and instantiate its local `frontier.json`, handoff packet, and triage board

## Rebuild Local `frontier.json` From This Note

Use this note plus `control/docs/frontier_ledger_template.json` to seed the new machine's local control state with:
- `frontier_branch = codex/execution-weight-decay-022-unembedding-followup`
- `frontier_commit = 52769ae`
- `frontier_val_bpb = 1.384010`
- `trust_status = passed`
- `trust_evidence_report = /Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10/reports/overnight_execution-baseline-mar10.md`
- `next_safe_action = bootstrap the second Mac as a validation node first; do not start free exploration`
