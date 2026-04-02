# mar10 Research Verdict — 2026-04-01

## Current Lead

- confirmed lead: `WEIGHT_DECAY=0.22`
- current posture: trust recovered under fixed-step controls; broad search remains closed
- tonight: no new overnight experiment is scheduled

## Reviewed Evidence

### Scalar `0.475` fixed-step confirmation

Artifacts:
- reviewer: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/review_mar10_scalar_0475_fixed_step_confirmation.py`
- state: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/state/archive/overnight_execution-weight-decay-022-scalar-confirmation_run2.json`

Result:
- baseline mean: `1.385342`
- baseline spread: `0.000198`
- candidate mean: `1.385084`
- candidate spread: `0.000044`
- delta: `+0.000258`
- classification: `scalar_promising`

Interpretation:
- real and stable
- below the `0.0010` material-win bar
- not promotable

### Scalar `0.48125` fixed-step confirmation

Artifacts:
- reviewer: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/review_mar10_scalar_048125_fixed_step_confirmation.py`
- state: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-048125-confirmation/state/overnight_execution-weight-decay-022-scalar-048125-confirmation.json`

Result:
- baseline mean: `1.3852525`
- baseline spread: `0.000001`
- candidate mean: `1.388347`
- candidate spread: `0.000660`
- delta: `-0.0030945`
- classification: `scalar_closed`

Interpretation:
- stable
- materially worse than plain `0.22`
- closed

### Unembedding fixed-step bracket

Artifacts:
- reviewer: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/review_mar10_unembedding_fixed_step_bracket.py`
- state: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-unembedding-followup/state/overnight_execution-weight-decay-022-unembedding-followup.json`

Result:
- baseline mean: `1.385447`
- baseline spread: `0.000000`
- `UNEMBEDDING_LR=0.0047`: `1.388063`, delta `-0.002616`
- `UNEMBEDDING_LR=0.0048`: `1.387149`, delta `-0.001702`
- classification: `unembedding_closed`

Interpretation:
- both nearby unembedding changes are stable and worse than plain `0.22`
- unembedding follow-up is closed

## Working Conclusion

- `WEIGHT_DECAY=0.22` remains the only confirmed lead
- scalar is exhausted for now:
  - `0.475` is promising but sub-threshold
  - `0.48125` is closed
- unembedding follow-up is closed
- no overnight run is justified tonight
