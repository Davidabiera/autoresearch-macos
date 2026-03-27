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

## [20260326-233906_autoresearch-mar24-night_0bdedde_46d335e]
- Parent workflow: queued unembedding-lr search after settling the beta2 axis
- Trigger: completed run with valid summary metrics after raising `UNEMBEDDING_LR` from `0.00525` to `0.005375`
- Inputs used: program.md, README.md, current train.py, last commit `46d335e`, run.log, results.tsv, and the live frontier (`1.389153 @ 348` steps)
- Output delivered: keep verdict with one strict TSV row and a recommendation to continue the queued upper-side unembedding probe
- What worked: the run improved both quality and throughput, finishing at `1.388021` with `354` steps against the prior live frontier at `1.389153` with `348` steps
- Friction: none beyond the normal long eval tail after training completed
- Uncertainty: low uncertainty on the keep verdict because the run won on both `val_bpb` and `num_steps`
- Reusable pattern: once the optimizer frontier is settled, small upward unembedding-lr moves can still buy both better metric and more steps on the current live regime
- Proposed dossier change: note that `UNEMBEDDING_LR=0.005375` outperforms `0.00525` when paired with `ADAM_BETAS=(0.85, 0.95)`
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260326-235828_autoresearch-mar24-night_ce36d62_3fff3e5]
- Parent workflow: queued upper-side follow-up after a new unembedding-lr keep
- Trigger: completed run with valid summary metrics after raising `UNEMBEDDING_LR` from `0.005375` to `0.0055`
- Inputs used: program.md, README.md, current train.py, last commit `3fff3e5`, run.log, results.tsv, and the live frontier (`1.388021 @ 354` steps)
- Output delivered: discard verdict with one strict TSV row and a recommendation to restore the new unembedding frontier before moving to the final queue slot
- What worked: the run completed cleanly and provided a decisive upper-side comparison against the new head-LR winner
- Friction: throughput degraded materially in the back half of training, finishing at only `339` steps and losing the metric at `1.395071`
- Uncertainty: low uncertainty on the discard verdict because both quality and throughput regressed well inside the valid comparison band
- Reusable pattern: once a small unembedding-lr increase keeps, one bounded upper-side follow-up is enough to bracket the axis when the next step loses on both metric and step count
- Proposed dossier change: note that `UNEMBEDDING_LR=0.005375` is locally superior to `0.0055` on the current live frontier
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-000904_autoresearch-mar24-night_c067e50_df61110]
- Parent workflow: final queued schedule-shape probe after settling the optimizer and unembedding axes
- Trigger: completed run with valid summary metrics after raising `FINAL_LR_FRAC` from `0.05` to `0.0625`
- Inputs used: program.md, README.md, current train.py, last commit `df61110`, run.log, results.tsv, and the live frontier (`1.388021 @ 354` steps)
- Output delivered: discard verdict with one strict TSV row and a recommendation to restore the prior schedule frontier
- What worked: the run completed cleanly and gave a decisive read on the final queued schedule probe
- Friction: throughput collapsed relative to the live frontier, finishing at only `315` steps with a much worse metric of `1.406378`
- Uncertainty: low uncertainty on the discard verdict because the run lost hard on both `val_bpb` and `num_steps`
- Reusable pattern: once the optimizer and head-lr frontier are settled, pushing the final LR floor upward can still be strongly harmful if it materially reduces usable steps on a wall-clock-limited run
- Proposed dossier change: note that `FINAL_LR_FRAC=0.0625` is materially worse than `0.05` on the current live frontier
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-094237_autoresearch-mar24-night_d883544_daytime_rebaseline]
- Parent workflow: morning confirmation gate after adopting the overnight winner `d883544` as the provisional live frontier
- Trigger: two unchanged daytime repeats were run from the current code state to test whether the overnight late-band and overnight winner reproduced under active daytime conditions
- Inputs used: overnight report, overnight controller state, current train.py, current HEAD `d883544`, and two unchanged daytime run logs archived from the root worktree
- Output delivered: measurement downgrade, not a new search verdict; the recommendation is to pause mutation search and re-baseline the daytime regime before spending more hyperparameter budget
- What worked: both repeats completed cleanly with valid summary blocks, making the re-baseline conclusion trustworthy
- Friction: the overnight winner did not reproduce in daytime conditions, landing at `1.388404 @ 350` steps and `1.391703 @ 342` steps versus the quiet overnight late-repeat band around `1.379495-1.382189 @ 365-372` steps
- Uncertainty: low uncertainty that the measurement regime shifted back during the day; moderate uncertainty about the true daytime live baseline until more unchanged repeats are collected
- Reusable pattern: when a quiet overnight winner beats the best repeat by only a narrow margin, the next daytime action must be an unchanged confirmation; if two daytime repeats miss the overnight repeat band materially, pause mutation search and treat machine state as the active confounder
- Proposed dossier change: note that `ADAM_BETAS=(0.85, 0.94)` remained the overnight best but was not reproduced in the daytime regime, so daytime search should re-baseline before exploring neighboring Adam settings
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-100442_autoresearch-mar24-night_d883544_daytime_rebaseline_cluster]
- Parent workflow: continuation of the daytime re-baseline after the first two confirmation repeats showed a measurement downgrade
- Trigger: two additional unchanged daytime repeats were run from `d883544` to decide whether the daytime surface was stabilizing or still too noisy for mutation search
- Inputs used: current train.py at `ADAM_BETAS=(0.85, 0.94)`, four unchanged daytime repeat logs, and the overnight repeat cluster for comparison
- Output delivered: accepted provisional daytime live baseline for the current machine state, without changing the code frontier
- What worked: the third and fourth daytime repeats tightened materially to `1.385597 @ 356` and `1.386521 @ 354`, much closer to each other than the first two repeats
- Friction: the recovered daytime band still sat well above the quiet overnight late-repeat band, so cross-regime comparisons remained invalid
- Uncertainty: moderate uncertainty on the exact daytime frontier center, low uncertainty that the current usable daytime band is around `1.38606 @ 355` from the last two repeats
- Reusable pattern: when the first two daytime repeats miss the overnight band but the next two tighten into a narrow local cluster, use the late cluster as the active daytime baseline and compare subsequent probes only against that band
- Proposed dossier change: note that the current daytime measurement regime partially recovered to about `1.38606 @ 355` while still underperforming the overnight late-repeat regime
- Proposed AGENTS or skill change: none
- Confidence: medium-high

## [20260327-101310_autoresearch-mar24-night_d883544_beta1_084_beta2_094]
- Parent workflow: first bounded mutation after establishing a provisional daytime baseline from the late repeat cluster
- Trigger: completed run with valid summary metrics after lowering `ADAM_BETAS` from `(0.85, 0.94)` to `(0.84, 0.94)`
- Inputs used: program.md, README.md, current train.py, current diff for the one-line beta1 change, run.log, results.tsv, and the accepted daytime baseline (`1.38606 @ 355` from the last two unchanged repeats)
- Output delivered: discard verdict with one TSV row and a frontier-restore recommendation
- What worked: throughput stayed fully comparable at `356` steps and the run completed cleanly with a valid summary block
- Friction: the metric regressed slightly to `1.386792`, missing the daytime baseline despite matching its throughput
- Uncertainty: low uncertainty on the discard verdict because the probe lost on metric while staying in-band on steps
- Reusable pattern: once a provisional daytime baseline exists, a neighboring optimizer probe that matches throughput but loses even modestly on `val_bpb` should be discarded immediately rather than over-interpreted as noise
- Proposed dossier change: note that under the current daytime regime `ADAM_BETAS=(0.85, 0.94)` is preferable to `(0.84, 0.94)`
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-111747_autoresearch-mar24-night_176fe6b_5669cb7]
- Parent workflow: first queued non-Adam daytime probe after committing the re-baselined research memory
- Trigger: completed run with valid summary metrics after lowering `MATRIX_LR` from `0.046` to `0.0455`
- Inputs used: program.md, README.md, current train.py, probe commit `5669cb7`, run.log, results.tsv, and the accepted daytime baseline band (`1.385597-1.386521 @ 354-356`)
- Output delivered: discard verdict with one TSV row and an immediate recommendation to stop the matrix-down axis and switch to `WARMDOWN_RATIO=0.49`
- What worked: the run completed cleanly and produced a decisive comparison against the daytime baseline
- Friction: throughput collapsed to `336` steps and the metric degraded to `1.397090`, making the loss unambiguous rather than merely noisy
- Uncertainty: low uncertainty on the discard verdict because the run lost hard on both `val_bpb` and `num_steps`
- Reusable pattern: when a non-Adam near-miss from a quieter regime loses badly against the current daytime band, stop that axis immediately instead of continuing the local bracket
- Proposed dossier change: note that `MATRIX_LR=0.0455` is materially worse than `0.046` under the current daytime regime, despite looking strong overnight
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-113829_autoresearch-mar24-night_5669cb7_bff1306]
- Parent workflow: daytime queue continuation on the strongest schedule-side near-miss after matrix-down discarded
- Trigger: completed run with valid summary metrics after lowering `WARMDOWN_RATIO` from `0.5` to `0.49`
- Inputs used: program.md, README.md, current train.py, probe commit `bff1306`, run.log, results.tsv, and the accepted daytime baseline band (`1.385597-1.386521 @ 354-356`)
- Output delivered: discard verdict with one TSV row and a recommendation to close the schedule-down branch for the current daytime regime
- What worked: the run completed cleanly and gave a decisive read on the best remaining schedule-side near-miss
- Friction: throughput slipped to `347` steps and the metric worsened to `1.389555`, so the loss was clear rather than marginal
- Uncertainty: low uncertainty on the discard verdict because both `val_bpb` and `num_steps` moved the wrong way
- Reusable pattern: when a schedule-side near-miss from the overnight regime loses on both metric and steps against the daytime band, close that branch and avoid spending more schedule budget in the same regime
- Proposed dossier change: note that `WARMDOWN_RATIO=0.49` is worse than `0.5` under the current daytime regime, even though it looked promising overnight
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-122454_autoresearch-mar24-night_bff1306_d98dbf4]
- Parent workflow: final queued daytime probe after matrix-down and schedule-down both discarded
- Trigger: completed run with valid summary metrics after lowering `EMBEDDING_LR` from `0.6` to `0.59`
- Inputs used: program.md, README.md, current train.py, probe commit `d98dbf4`, run.log, results.tsv, and the accepted daytime baseline band (`1.385597-1.386521 @ 354-356`)
- Output delivered: discard verdict with one TSV row and a recommendation to restore the frontier and stop this queue branch
- What worked: the run completed cleanly and decisively closed the last planned branch in the daytime queue
- Friction: throughput collapsed to `326` steps and the metric degraded sharply to `1.402777`, so the probe was not merely noisy but actively harmful in the daytime regime
- Uncertainty: low uncertainty on the discard verdict because the loss was large on both quality and throughput
- Reusable pattern: optimizer-side near-misses from the overnight regime can fail hard in the daytime regime, so once a re-baselined daytime band exists they should be judged only against that band and discarded immediately on a large two-axis loss
- Proposed dossier change: note that `EMBEDDING_LR=0.59` is materially worse than `0.6` under the current daytime regime
- Proposed AGENTS or skill change: none
- Confidence: high

## [20260327-135312_autoresearch-mar24-night_5c73708_7c82ce7]
- Parent workflow: first post-queue daytime probe after shifting from Adam-local tuning to the strongest remaining orthogonal schedule lever
- Trigger: completed rerun with valid summary metrics after lowering `FINAL_LR_FRAC` from `0.05` to `0.04`
- Inputs used: program.md, README.md, current train.py, probe commit `7c82ce7`, run.log, results.tsv, the overnight controller ledger showing strong quiet-regime near-misses for lower final-LR floor, and the accepted daytime baseline band (`1.385597-1.386521 @ 354-356`)
- Output delivered: discard verdict with one TSV row and an immediate recommendation to stop daytime mutation search rather than continue probing neighboring schedule-floor values
- What worked: the rerun completed cleanly end-to-end after allowing the full post-training evaluation tail, so the result is trustworthy
- Friction: the probe regressed catastrophically to `1.411985` with only `304` steps, far outside the daytime comparison band and substantially worse than even the recent daytime discards
- Uncertainty: low uncertainty on the discard verdict because both quality and throughput collapsed hard
- Reusable pattern: schedule-floor settings that look strong in the quiet overnight regime can fail outright in the daytime regime, so broad schedule exploration should be reserved for quiet windows once a daytime ruler is established
- Proposed dossier change: note that `FINAL_LR_FRAC=0.04` is materially worse than `0.05` under the current daytime regime and should not be revisited in daytime search
- Proposed AGENTS or skill change: none
- Confidence: high
