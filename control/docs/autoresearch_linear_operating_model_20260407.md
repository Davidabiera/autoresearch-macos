# Autoresearch Linear Operating Model — 2026-04-07

## Summary

Linear now owns work tracking for this repo.

Project:
- name: `Autoresearch Experiment Program`
- team: `Systemsshaper`
- project URL: `https://linear.app/systemsshaper/project/autoresearch-experiment-program-01a30d049370`
- operating doc: `https://linear.app/systemsshaper/document/autoresearch-operating-model-9d178f1c833a`

Repo control docs remain the technical source of truth for:
- canonical frontier
- experiment verdicts
- plan/queue definitions
- reviewer outputs

Default repo entrypoint for active state:
- [/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_current_state.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_current_state.md)

Linear tracks:
- milestones
- issue ownership
- review state
- next safe actions

## Board Model

Use the existing `Systemsshaper` statuses directly:
- `Backlog`
  - possible work, not selected
- `Todo`
  - selected for the next cycle, no branch actively moving yet
- `In Progress`
  - one owner is actively changing code/docs or running a bounded loop
- `In Review`
  - waiting on a proof pack, verdict memo, PR review, or explicit human decision
- `Done`
  - loop closed and verdict recorded
- `Canceled` / `Duplicate`
  - abandoned, superseded, or merged into another item

Do not add custom statuses for v1.

## Issue Contract

Every non-trivial issue must include:
- objective
- owner
- branch/worktree
- repo proof path or verdict path
- next safe action

Use title prefixes instead of heavy label design:
- `REVIEW:`
- `CONTROL:`
- `RUN:`
- `DECISION:`
- `CLEANUP:`

Do not open a PR without a matching Linear issue.
Do not start a run without:
- a Linear issue
- a repo plan/queue
- a named reviewer surface

## Milestones

Created milestones:
- `M1 — Reconstruct and Simplify`
  - reconstruct actual state, classify branches/worktrees/queues, reduce ambiguity
- `M2 — Canonicalize Operating Surfaces`
  - make ownership, proof-pack flow, and current-state visibility durable
- `M3 — Decide Next Research Axis`
  - only after M1 and M2 are coherent

Recommended milestone usage:
- M1 covers the current review and cleanup work
- M2 covers repo-to-board operating cleanup
- M3 begins only after `mar24-night` status and branch indexing are explicit

## Seed Issues For Later Creation

Do not bulk-migrate yet. Create only the minimum next issues when ready:
- `REVIEW: Reconstruct mar10 and mar24 current-state narrative`
- `CLEANUP: Classify and index all codex execution branches`
- `CONTROL: Make critical current-state surfaces durable and non-ambiguous`
- `DECISION: Choose whether mar24-night remains active or becomes archival`
- `DECISION: Choose pause vs materially new axis after mar10`

Do not create a second-Mac execution issue yet.

## Operating Loop

The default loop from now on:
1. Select one issue.
2. Assign one owner and one branch/worktree.
3. Do the work.
4. Write the proof path or verdict path in the issue.
5. Move the issue to `In Review`.
6. Close it as `Done`, `Canceled`, or `Duplicate`.

This is the alignment rule:
- fewer branches treated as ambient possibility
- more work items with owner, state, and closure
