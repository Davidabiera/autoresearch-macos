# `mar24-night` Archival Decision — 2026-04-07

## Decision

- classification: `archival`
- active-lane status: `closed`
- remote-branch status: `retain`
- root-workspace status: `move off autoresearch/mar24-night`

## Why

- `mar24-night` is not the current frontier
- `mar10` now carries the coherent finished frontier line
- `mar24-night` still contains valuable historical evidence, but not current execution intent
- leaving the root workspace on `autoresearch/mar24-night` keeps a historical branch looking live when it is not

## Preserved References

- preservation proof: [mar24_night_archival_proof_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_proof_20260407.md)
- historical closeout: [mar24_night_closeout.md](/Users/davidabiera/Projects/team/autoresearch-macos/docs/reference/workflows/mar24_night_closeout.md)
- operating review: [autoresearch_operating_review_20260407.md](/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_operating_review_20260407.md)

## Required Consequences

- do not attach new research work to `autoresearch/mar24-night`
- do not treat the branch as part of the active milestone view
- keep the remote branch available as historical evidence for now
- move the root workspace onto a neutral non-archival branch

## Implementation Status

- root workspace re-homed: `complete`
- current root branch: `main`
- archival branch retained remotely: `yes`

## Next Active Focus

- close the root-workspace carryover by switching it off `autoresearch/mar24-night`
- then choose between:
  - pause/consolidation on the confirmed `mar10` frontier
  - one materially different next axis
