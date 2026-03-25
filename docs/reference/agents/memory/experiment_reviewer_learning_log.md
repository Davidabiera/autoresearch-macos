# experiment_reviewer Learning Log

This file is the parent-persisted memory surface for `experiment_reviewer`.

The reviewer itself is read-only and must return a fenced `LEARNING_LOG_ENTRY` block instead of appending here directly.

## Template

```text
## [run timestamp or issue id]
- Parent workflow:
- Trigger:
- Inputs used:
- Output delivered:
- What worked:
- Friction:
- Uncertainty:
- Reusable pattern:
- Proposed dossier change:
- Proposed AGENTS or skill change:
- Confidence: [high | medium | low]
```

## [20260324-baseline-autoresearch-mar24-night-1cdbc21]
- Parent workflow: overnight experiment loop with post-run reviewer handoff
- Trigger: baseline run completed with run.log summary and header-only results.tsv
- Inputs used: program.md, README.md, current train.py, last commit 1cdbc21, run.log, results.tsv, prepare.py
- Output delivered: keep verdict for baseline, strict TSV row, one next-step recommendation
- What worked: baseline completed cleanly and produced a valid val_bpb for the nightly branch
- Friction: peak_vram_mb reported as 0.0 on the current MPS path, so memory evidence is weak
- Uncertainty: no prior TSV row exists yet, so this is a baseline establishment judgment rather than a comparative improvement judgment
- Reusable pattern: first completed run with header-only results.tsv should usually be logged as baseline keep when the metric is valid
- Proposed dossier change: note explicitly that MPS baseline runs may yield non-informative memory fields if only CUDA memory is instrumented
- Proposed AGENTS or skill change: none
- Confidence: medium

## [20260324-weight-decay-02195-autoresearch-mar24-night-e9f7896]
- Parent workflow: post-run experiment judgment inside the overnight loop
- Trigger: completed-but-failed run with no final summary and empty grep for val_bpb
- Inputs used: program.md, README.md, current train.py, last commit e9f7896, run.log, results.tsv
- Output delivered: crash-rework verdict with one crash TSV row and one bounded next step
- What worked: the evidence was sufficient to rule out keep and to confirm current macOS/MPS startup safety
- Friction: no traceback and no final summary block, so root cause remains unclear despite clear run failure
- Uncertainty: medium uncertainty on cause; low uncertainty that the run outcome is unusable
- Reusable pattern: when a narrowly scoped hyperparameter change produces no val_bpb and the run is terminated for pathological slowness, adjudicate crash-rework and log status as crash
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: medium

## [20260324-232700_autoresearch-mar24-night_7e1d2d0_3f47684]
- Parent workflow: overnight experiment loop with post-run reviewer handoff
- Trigger: completed post-baseline run with valid summary metrics and a one-line matrix learning rate change
- Inputs used: program.md, README.md, current train.py, last commit 3f47684, run.log, results.tsv
- Output delivered: discard verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed within budget and produced a valid comparable val_bpb against the established baseline
- Friction: late-run step-time spikes appeared around steps 194-197, but the run still completed and yielded usable evidence
- Uncertainty: low uncertainty on the discard verdict; memory evidence remains weak on the current MPS path because peak_vram_mb is non-informative
- Reusable pattern: when a one-line hyperparameter increase completes cleanly but materially worsens val_bpb versus the kept baseline, discard and restore train.py to the prior frontier
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high
