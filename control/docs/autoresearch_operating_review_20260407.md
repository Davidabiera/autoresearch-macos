# Autoresearch Operating Review — 2026-04-07

## Summary

This review freezes execution and reconstructs the real operating state across `mar10` and `mar24-night`.

Working conclusion:
- `mar10` is a coherent finished research loop
- plain `WEIGHT_DECAY=0.22` at `52769ae` is the surviving confirmed frontier
- scalar, unembedding, and nearby ridge follow-ups are closed or sub-threshold
- `mar24-night` is archival historical evidence, not an active frontier lane
- the main problem is no longer experiment logic; it is workflow sprawl and weak milestone/ownership visibility

## What Was Actually Achieved

### `mar10`

- trust recovery succeeded under fixed-step controls
- `WEIGHT_DECAY=0.22` was confirmed as the surviving lead
- scalar follow-up was resolved:
  - `0.475` was real but below the material-win bar
  - `0.48125` closed
- unembedding follow-up closed
- nearby ridge retest closed
- result: local neighborhood around the `0.22` lead is exhausted enough to stop spending run budget there

Primary durable references:
- [mar10_research_verdict_20260401.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md)
- [mar10_weight_decay_ridge_verdict_20260402.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_weight_decay_ridge_verdict_20260402.md)
- [mar10_frontier_declaration_20260402.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_frontier_declaration_20260402.md)

### `mar24-night`

- the overnight line materially improved the then-current best value from `1.388021` to `1.378980`
- subsequent daytime follow-up and repeatability work produced useful evidence, but the line never got re-indexed into the current `mar10` control system
- the branch remains present and pushed as evidence, but it is now archived rather than treated as live work

Primary durable references:
- [mar24_night_closeout.md](/Users/davidabiera/Projects/team/autoresearch-macos/docs/reference/workflows/mar24_night_closeout.md)
- [mar24_night_archival_proof_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_proof_20260407.md)
- [mar24_night_archival_decision_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md)

## What Is Active Versus Merely Present

### Worktrees

- `general repo orientation`
  - [/Users/davidabiera/Projects/team/autoresearch-macos](/Users/davidabiera/Projects/team/autoresearch-macos)
    - current branch `main`
    - no longer used as the `mar24-night` worktree

- `canonical`
  - [execution-weight-decay-022-unembedding-followup](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-unembedding-followup)
    - carrier of the surviving `mar10` frontier commit `52769ae`
    - not an active run lane today

- `support/control`
  - [control](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control)
  - [reliability](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability)

- `archival evidence`
  - [execution-baseline-mar10](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10)
  - [execution-weight-decay-022-ridge](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-ridge)
  - [execution-weight-decay-022-scalar](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar)
  - [execution-weight-decay-022-scalar-confirmation](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation)
  - [execution-weight-decay-022-scalar-048125-confirmation](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-048125-confirmation)

- `stale/unindexed`
  - none

### Branch families

- `first-class`
  - `codex/overnight-control`
  - `codex/autoresearch-reliability`
  - `codex/execution-weight-decay-022-unembedding-followup`

- `historical execution evidence`
  - `codex/execution-baseline-mar10`
  - `codex/execution-weight-decay-022-ridge`
  - `codex/execution-weight-decay-022-scalar*`
  - `autoresearch/mar24-night`

- `historical staging`
  - `autoresearch/mar10`
  - `codex/frontier-baseline-stability-mar10`
  - `codex/frontier-isolation-mar10`
  - `codex/canary-*`
  - `codex/gate-*`
  - `codex/overnight-weight-decay-fine`
  - `codex/repeatability-weight-decay-mar10`
  - `codex/repeatability-smoke-mar24`
  - `codex/runner-gate-mar10`

### Plans and queues

- `archival executed control packages`
  - all `mar10` trust-recovery, confirmation, scalar, unembedding, and ridge plans/queues
  - `mar24_night_overnight*.jsonl`

- `prepared but not currently committed`
  - `mar10_overnight.jsonl`
  - `mar10_scalar_followup_extension.jsonl`

Working rule from this review:
- no visible plan or queue counts as active unless it is attached to a current milestone and a current board item

## What Is Working

- control and reliability are properly separated from execution lanes
- bounded runs plus dedicated reviewer scripts gave decision-grade answers
- fixed-step controls solved the main comparability failure for `mar10`
- hold-window discipline prevented reopening search after the local neighborhood was exhausted
- verdict docs are stronger than raw logs and are already close to a good proof-pack model

## What Is Failing

- too many branches, worktrees, plans, and queues exist without a single active-state board
- local-only coordination surfaces still matter for current state, which weakens away-from-chat visibility
- branch presence is being mistaken for activity
- historical lanes can still leak into active mental models if the root workspace is left on them
- milestone intent is implicit in chat and docs, not explicit in a tracked work system
- prepared control packages accumulate faster than explicit decisions to run or retire them

## What Remains Unclear

- whether the next step after `mar10` is pause/consolidation or a materially different axis
- which historical staging branches deserve a durable index versus simple archival treatment

## Minimum Next Decisions

1. Decide whether the next phase is `pause and consolidate` or `design one materially different axis`.
2. Move branch/worktree ownership and status out of ambient memory and into the Linear project plus repo proof paths.
3. Keep the root workspace off archival branches.
