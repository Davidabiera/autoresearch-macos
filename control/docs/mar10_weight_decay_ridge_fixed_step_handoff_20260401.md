# mar10 Weight-Decay Ridge Fixed-Step Handoff — 2026-04-01

Prepared future lane:
- branch: `codex/execution-weight-decay-022-ridge`
- execution root: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-ridge`
- launcher: `/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/reliability/scripts/run_mar10_weight_decay_ridge_fixed_step_bracket.sh`

Prepared queue order:
1. `candidate_weight_decay_022_fixed_step_repeat_m`
2. `weight_decay_0218_fixed_step`
3. `weight_decay_02225_fixed_step`
4. `candidate_weight_decay_022_fixed_step_repeat_n`

Acceptance rule:
- all 4 items must finish cleanly at `354` steps
- `baseline_spread = abs(m - n) <= 0.0010`
- `delta_0218 = baseline_mean - val_bpb(0.218)`
- `delta_02225 = baseline_mean - val_bpb(0.2225)`
- classify in this order:
  - `stage_instability`
  - `inconclusive_drift`
  - `ridge_promoted`
  - `ridge_promising`
  - `ridge_closed`

Operational default:
- do not run tonight
- use this package only in the next bounded run window if another narrow retest is warranted
