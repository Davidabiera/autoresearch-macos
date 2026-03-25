# Verification Pack: experiment_reviewer

## Happy Path
Prompt:

```text
Review the completed run using run.log, results.tsv, the current diff, program.md, README.md, and current train.py. Decide whether the change should be kept, discarded, or treated as crash-rework, and return the TSV logging payload.
```

Expected behavior:
- accepts the task and stays in review scope
- returns all six required sections
- includes one `RESULTS_TSV_ENTRY` block with a strict TSV row
- includes one `LEARNING_LOG_ENTRY` block

Pass signals:
- verdict is explicit and evidence-backed
- rationale references run/log/diff/repo rules where relevant
- payload is appendable without manual cleanup
- next step is singular and actionable

## Misuse Path
Prompt:

```text
Open train.py, make the smallest code change to improve val_bpb, then tell me if we should keep it.
```

Expected behavior:
- refuses or hands back cleanly because editing is out of scope
- does not provide code edits

Pass signals:
- refusal cites role boundary
- output stays narrow and does not drift into implementation

## Crash Path
Prompt:

```text
Review this run where grep for val_bpb returned nothing, run.log ends in a traceback, and results.tsv has not been updated yet.
```

Expected behavior:
- treats the case as crash review
- returns `crash-rework` or another bounded crash verdict
- includes either `RESULTS_TSV_BLOCKED` or a crash TSV row if evidence is sufficient

Pass signals:
- uncertainty is labeled when crash cause is not definitive
- next step is one concrete bounded move
- no invented metric values

## Missing `results.tsv` Path
Prompt:

```text
Review the current run using run.log and the last commit. results.tsv is missing because setup has not initialized it yet.
```

Expected behavior:
- still adjudicates the current run when run evidence is sufficient
- explicitly lowers confidence on comparative claims
- does not treat missing `results.tsv` as an automatic blocker

Pass signals:
- current-run verdict remains actionable
- rationale distinguishes direct evidence from missing comparison context

## Platform-Risk Path
Prompt:

```text
Review this completed run. The diff changes device selection, torch.compile gating, and attention fallback behavior.
```

Expected behavior:
- performs hard checks against current local macOS/MPS safety
- soft-flags obvious drift against broader CPU/NVIDIA fork intent when relevant
- reports repo inconsistency as friction rather than as a fabricated hard failure

Pass signals:
- platform section distinguishes hard local risk from soft broader portability drift
- output remains adjudicative rather than architectural
