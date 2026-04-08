# Autoresearch Branch Index

Use this index to classify the repo's major branches and worktrees without inferring activity from branch presence alone.

| surface | branch | worktree_path | head_commit | status_class | role | proof_path | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| root workspace | `main` | `/Users/davidabiera/Projects/team/autoresearch-macos` | `3dcd3f1` | `general repo orientation` | top-level repo orientation only | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md` | Not an execution lane. Keep off archival branches. |
| control worktree | `codex/overnight-control` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control` | `3cbfe68` | `support/control` | control docs, Linear alignment, proof-pack surfaces | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/autoresearch_operating_review_20260407.md` | Active M2 control lane. |
| reliability worktree | `codex/autoresearch-reliability` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability` | `d271567` | `support/control` | live status, reviewer scripts, tests | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/session_status.py` | Active only when operator surfaces need code alignment. |
| parked frontier lane | `codex/execution-weight-decay-022-unembedding-followup` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-unembedding-followup` | `52769ae` | `canonical` | carrier of the surviving `mar10` frontier | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_frontier_declaration_20260402.md` | Parked frontier. Not an active run lane. |
| baseline trust evidence | `codex/execution-baseline-mar10` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10` | `c7f7325` | `archival evidence` | trust-path and baseline evidence | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-baseline-mar10/reports/overnight_execution-baseline-mar10.md` | Historical evidence for trust recovery and frontier declaration. |
| ridge retest evidence | `codex/execution-weight-decay-022-ridge` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-ridge` | `52769ae` | `archival evidence` | fixed-step ridge retest evidence | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_weight_decay_ridge_verdict_20260402.md` | Ridge is closed. |
| scalar bracket evidence | `codex/execution-weight-decay-022-scalar` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar` | `52769ae` | `archival evidence` | candidate-root scalar bracket evidence | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md` | Scalar neighborhood no longer active. |
| scalar 0.475 confirmation evidence | `codex/execution-weight-decay-022-scalar-confirmation` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation` | `a6a97d3` | `archival evidence` | fixed-step confirmation of promoted scalar candidate | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md` | `0.475` stayed sub-threshold. |
| scalar 0.48125 confirmation evidence | `codex/execution-weight-decay-022-scalar-048125-confirmation` | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-048125-confirmation` | `a8337e1` | `archival evidence` | fixed-step confirmation of backup scalar candidate | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar10_research_verdict_20260401.md` | `0.48125` closed. |
| historical overnight evidence | `autoresearch/mar24-night` | `none (remote-only historical branch)` | `143b78b` | `archival evidence` | historical overnight evidence retained for audit | `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/control/control/docs/mar24_night_archival_decision_20260407.md` | Appears exactly once here. Not a live lane. |

## Classification Rules

- `canonical`: carries the currently parked frontier.
- `support/control`: active only for docs, status surfaces, reviewers, and tests.
- `archival evidence`: historical proof paths kept for audit, not for current execution.
- `historical staging`: old staging branches mentioned in the operating review, not first-class execution lanes.
- `general repo orientation`: top-level workspace used for repo navigation, not experiment ownership.

## Reading Rule

- If a branch or worktree is not listed here as `canonical` or `support/control`, treat it as non-active by default.
- Presence in `git worktree list` does not imply current execution.
