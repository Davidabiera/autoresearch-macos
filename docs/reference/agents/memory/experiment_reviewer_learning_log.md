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

## [20260325-144957_autoresearch-mar24-night_fbc7ac9_21af6c2]
- Parent workflow: overnight experiment loop with post-run reviewer handoff
- Trigger: completed run with valid summary metrics after a one-line unembedding learning-rate increase
- Inputs used: program.md, README.md, current train.py, last commit 21af6c2, run.log, results.tsv, prepare.py
- Output delivered: keep verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed cleanly, improved val_bpb versus the kept baseline, and stayed operationally stable on the current macOS/MPS path
- Friction: memory evidence remains weak because peak_vram_mb is non-informative on this MPS path
- Uncertainty: low uncertainty on the keep verdict; low-to-medium uncertainty on memory interpretation only
- Reusable pattern: when a one-line hyperparameter increase on a previously winning axis yields a clear val_bpb improvement with no platform-risk signal, keep and advance the frontier
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-160238_autoresearch-mar24-night_21af6c2_76defde]
- Parent workflow: overnight experiment loop with post-run reviewer handoff after restart reconstruction
- Trigger: completed run with valid summary metrics after a second bounded unembedding learning-rate increase
- Inputs used: program.md, README.md, current train.py, last commit 76defde, run.log, results.tsv, prepare.py
- Output delivered: keep verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed cleanly, improved val_bpb from 1.384808 to 1.382862, and preserved stable throughput on the current macOS/MPS path
- Friction: memory evidence remains weak because peak_vram_mb is still non-informative on this MPS path
- Uncertainty: low uncertainty on the keep verdict; low-to-medium uncertainty only on memory interpretation
- Reusable pattern: when consecutive bounded increases on the same winning hyperparameter axis continue to improve val_bpb, keep stepping in that direction until the gain flattens or reverses
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-161704_autoresearch-mar24-night_76defde_fb177dc]
- Parent workflow: overnight experiment loop with bounded follow-up probe after a restart-resumed keep
- Trigger: completed run with valid summary metrics after raising unembedding learning rate one more step beyond the new frontier
- Inputs used: program.md, README.md, current train.py, last commit fb177dc, run.log, results.tsv, prepare.py
- Output delivered: discard verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed cleanly and provided a decisive comparison that brackets the local optimum on the tested axis
- Friction: memory evidence remains weak because peak_vram_mb is non-informative on the current MPS path
- Uncertainty: low uncertainty on the discard verdict; the regression from 1.382862 to 1.384670 is materially above noise at this local scale
- Reusable pattern: when a second consecutive increase on a winning scalar axis reverses the gain, treat the prior step as the local frontier and stop pushing further in that direction
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-163646_autoresearch-mar24-night_5fd40db_3a0acbe]
- Parent workflow: overnight experiment loop after bookkeeping cleanup and schedule-axis switch
- Trigger: completed run with valid summary metrics after raising the final learning-rate floor from 0.05 to 0.075
- Inputs used: program.md, README.md, current train.py, last commit 3a0acbe, run.log, results.tsv, prepare.py
- Output delivered: discard verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed cleanly and isolated the schedule-floor effect without any throughput or stability confound
- Friction: memory evidence remains weak because peak_vram_mb is still non-informative on the current MPS path
- Uncertainty: low uncertainty on the discard verdict; the higher late-run floor worsened val_bpb from 1.382862 to 1.385292
- Reusable pattern: when a higher late-run LR floor regresses versus the frontier in a fixed-budget regime, prefer exploring earlier decay rather than preserving more LR late
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-165212_autoresearch-mar24-night_0da0217_88c8ecb]
- Parent workflow: overnight experiment loop continuing along the schedule axis after a failed higher final-lr-floor probe
- Trigger: completed run with valid summary metrics after extending WARMDOWN_RATIO from 0.5 to 0.55
- Inputs used: program.md, README.md, current train.py, last commit 88c8ecb, run.log, results.tsv, prepare.py
- Output delivered: discard verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run completed cleanly and decisively ruled out earlier decay on the current frontier configuration
- Friction: memory evidence remains weak because peak_vram_mb remains non-informative on the current MPS path
- Uncertainty: low uncertainty on the discard verdict; the regression from 1.382862 to 1.392274 is large enough to treat as a clear miss
- Reusable pattern: when both higher late-run floor and earlier decay regress, the current schedule shape is likely already near a local optimum and the next probe should switch away from this schedule family
- Proposed dossier change: none
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-170624_autoresearch-mar24-night_34c3929_c3527f9]
- Parent workflow: overnight experiment loop after restoring the schedule frontier and switching to the largest untouched Adam group
- Trigger: killed run with no final summary after raising EMBEDDING_LR from 0.6 to 0.63
- Inputs used: program.md, README.md, current train.py, last commit c3527f9, run.log, results.tsv, prepare.py
- Output delivered: crash verdict with one strict TSV row and one bounded next-step recommendation
- What worked: the run failed quickly enough to rule out this larger embedding-lr move without wasting a full comparison slot
- Friction: step time exploded immediately on the current macOS/MPS path, so there is no comparable val_bpb and the shell wrapper had to be killed manually
- Uncertainty: low uncertainty that the run is unusable; medium uncertainty on whether the failure is specific to this step size or the embedding-lr direction more broadly
- Reusable pattern: when a single hyperparameter change causes immediate order-of-magnitude step-time inflation and no summary block, log a crash and restore the prior frontier instead of treating it as a normal discard
- Proposed dossier change: note that large Adam-LR moves on the shared embedding/value-embedding group can trigger catastrophic MPS slow paths even without an explicit traceback
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-frontier-repeatability-check-autoresearch-mar24-night]
- Parent workflow: post-crash calibration gate before resuming hyperparameter search
- Trigger: two unchanged frontier reruns after the runtime recovered from the embedding-lr slow-path failure
- Inputs used: current train.py at the confirmed frontier, run.log, archived frontier logs from commits 21af6c2, 76defde, and fb177dc
- Output delivered: repeatability warning and a recommendation to pause new search verdicts
- What worked: runtime recovered from the catastrophic slow path, with early step times back near the prior healthy regime
- Friction: the unchanged frontier did not reproduce its earlier metric or throughput band; the two calibration reruns landed at val_bpb 1.397026 with 329 steps and 1.394373 with 334 steps, versus the trusted 76defde run at 1.382862 with 360 steps
- Uncertainty: medium uncertainty on root cause; low uncertainty that the current measurement surface has shifted enough to make new search verdicts risky
- Reusable pattern: when unchanged-frontier reruns recover from a runtime stall but remain materially worse in both num_steps and val_bpb, treat the system as a repeatability problem first and avoid logging new hyperparameter wins or losses until the frontier band is re-established
- Proposed dossier change: note that a recovered runtime path can still leave the branch on a degraded throughput/metric surface, so calibration must gate on both timing and reproduced frontier quality
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260325-frontier-repeatability-partial-recovery-autoresearch-mar24-night]
- Parent workflow: repeatability diagnosis after identifying a competing external training process
- Trigger: third unchanged frontier rerun after stopping `/private/tmp/autoresearch-execution-baseline/train.py`
- Inputs used: current train.py at the confirmed frontier, `ps`, `top`, `memory_pressure`, `vm_stat`, and archived frontier calibration logs
- Output delivered: partial-cause finding that background load materially affects frontier throughput and quality
- What worked: stopping the competing external trainer improved the unchanged frontier rerun from 329-334 steps and 1.394-1.397 val_bpb up to 342 steps and 1.390871 val_bpb
- Friction: even after removing the external trainer, the run still did not recover the trusted 360-step / 1.382862 band; the active desktop remained under significant CPU and memory pressure from GUI applications and compressed memory
- Uncertainty: medium uncertainty on how much additional recovery is possible without further machine cleanup; low uncertainty that active competing load is a real confounder
- Reusable pattern: on an actively used desktop Mac, repeatability can improve substantially after removing competing training jobs, but lingering browser/app load may still keep the machine below the trusted frontier throughput band
- Proposed dossier change: note that unattended or low-interference sessions are materially safer for frontier comparisons than active-desktop sessions with heavy browser/app load
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-frontier-repeatability-rebaseline-autoresearch-mar24-night]
- Parent workflow: strict calibration gate before resuming post-repeatability search
- Trigger: two quiet unchanged-frontier reruns after removing the known competing trainer
- Inputs used: current train.py at the confirmed frontier, archived quiet rerun logs, and the accepted gate thresholds (`0.003 val_bpb`, `10 steps`) for forming a live baseline cluster
- Output delivered: accepted live baseline for the current machine state without logging a search verdict to `results.tsv`
- What worked: the two quiet repeats landed close enough to form a stable cluster, with the better run at `1.391030` and `341` steps and the second at `1.392260` and `339` steps
- Friction: neither quiet repeat reproduced the historical best `1.382862 @ 360` steps, so the branch now carries both a historical best and a quieter-state live baseline
- Uncertainty: low uncertainty that the current live baseline cluster is real; medium uncertainty on whether a more unattended session could recover the historical best band
- Reusable pattern: when two quiet unchanged-frontier reruns miss the historical best but cluster tightly within predefined tolerances, accept the better run as the live baseline and resume bounded search from there
- Proposed dossier change: note the distinction between historical best and current live baseline on wall-clock-limited desktop runs
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-152320_autoresearch-mar24-night_29f7359_b92a0a3]
- Parent workflow: first bounded optimizer probe after accepting a quiet-state live baseline
- Trigger: completed run with valid summary metrics after lowering `WEIGHT_DECAY` from `0.20` to `0.19`
- Inputs used: program.md, README.md, current train.py, last commit `b92a0a3`, run.log, results.tsv, and the accepted quiet live baseline (`1.391030 @ 341` steps)
- Output delivered: discard verdict with one strict TSV row and one frontier-restore recommendation
- What worked: the run completed cleanly and provided a directly comparable optimizer-axis result against the new quiet-state baseline
- Friction: throughput regressed from the accepted quiet baseline band, finishing at `331` steps instead of `339-341`, which reduced confidence that any metric improvement could have been attributed cleanly to the hyperparameter
- Uncertainty: low uncertainty on the discard verdict because both the metric and step count regressed versus the accepted quiet baseline
- Reusable pattern: after re-baselining a noisy wall-clock environment, discard optimizer changes that lose on both `val_bpb` and `num_steps` relative to the accepted live baseline
- Proposed dossier change: note that lower weight decay on the current Muon frontier degraded both quality and throughput under the accepted quiet-state baseline
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-200410_autoresearch-mar24-night_416c0cd_b697e18]
- Parent workflow: bounded follow-up search after re-baselining and discarding lower weight decay
- Trigger: completed run with valid summary metrics after raising `ADAM_BETAS` from `(0.8, 0.95)` to `(0.85, 0.95)`
- Inputs used: program.md, README.md, current train.py, last commit `b697e18`, run.log, results.tsv, and the accepted quiet live baseline (`1.391030 @ 341` steps)
- Output delivered: keep verdict with one strict TSV row and one bounded continuation recommendation
- What worked: the run improved both quality and throughput, landing at `1.389153` with `348` steps versus the accepted live baseline at `1.391030` with `341` steps
- Friction: host load was visibly elevated before launch, so early cadence had to be monitored to confirm the run remained comparable
- Uncertainty: low uncertainty on the keep verdict because the run won on both `val_bpb` and `num_steps`
- Reusable pattern: after re-baselining a noisy desktop environment, a new optimizer setting that improves both metric and throughput can safely become the new live frontier even if the historical best remains lower
- Proposed dossier change: note that increasing Adam beta1 to `0.85` improved the current frontier under the re-established measurement regime
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-202151_autoresearch-mar24-night_b697e18_5ea108a]
- Parent workflow: bounded continuation on a newly winning beta1 axis
- Trigger: completed run with valid summary metrics after raising `ADAM_BETAS` from `(0.85, 0.95)` to `(0.9, 0.95)`
- Inputs used: program.md, README.md, current train.py, last commit `5ea108a`, run.log, results.tsv, and the new live frontier (`1.389153 @ 348` steps)
- Output delivered: discard verdict with one strict TSV row and one frontier-restore recommendation
- What worked: the run cleanly bracketed the beta1 axis by testing one more bounded increase beyond the new winner
- Friction: throughput slipped to `337` steps and the metric regressed to `1.396688`, making the miss decisive
- Uncertainty: low uncertainty on the discard verdict because both quality and throughput worsened versus the new frontier
- Reusable pattern: once a beta1 increase produces a keep, one additional bounded increase is enough to bracket the local optimum when the follow-up loses on both metric and step count
- Proposed dossier change: note that `ADAM_BETAS=(0.85, 0.95)` is locally superior to both `(0.8, 0.95)` and `(0.9, 0.95)` on the current frontier
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-223722_autoresearch-mar24-night_f73979f_25c1306]
- Parent workflow: run 1 of the queued beta2 and unembedding search from the live frontier
- Trigger: completed run with valid summary metrics after raising `ADAM_BETAS` from `(0.85, 0.95)` to `(0.85, 0.97)`
- Inputs used: program.md, README.md, current train.py, last commit `25c1306`, run.log, results.tsv, and the live frontier (`1.389153 @ 348` steps)
- Output delivered: discard verdict with one strict TSV row and a recommendation to restore the prior beta2 frontier before continuing the queue
- What worked: cadence remained healthy through training and the run completed with a fully comparable summary block
- Friction: the result regressed decisively versus the live frontier, landing at `1.396177` with only `340` steps against `1.389153` with `348` steps
- Uncertainty: low uncertainty on the discard verdict because the run lost on both metric and throughput while staying inside the valid step-count band
- Reusable pattern: after a beta1 improvement, a bounded beta2 increase that loses on both `val_bpb` and `num_steps` should be discarded immediately and the queue should skip the higher beta2 follow-up
- Proposed dossier change: note that `ADAM_BETAS=(0.85, 0.95)` remains superior to `(0.85, 0.97)` on the current live frontier
- Proposed AGENTS or skill change: none
- Confidence: high
