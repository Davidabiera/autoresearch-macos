# mar10 Next-Axis Design Package — 2026-04-01

## Summary

Default for tonight:
- hold the run window
- publish the distilled verdict
- do not create or launch another overnight queue

Reason:
- the confirmed lead is still plain `WEIGHT_DECAY=0.22`
- scalar and unembedding were the nearest adjacent axes
- both have now resolved enough to stop spending overnight budget on them

## Ranked Shortlist

### 1. Low-prior fixed-step weight-decay ridge around `0.22` — Recommended for the next actual run window

Exact future queue shape:
1. baseline `0.22` fixed-step repeat `m`
2. `WEIGHT_DECAY=0.218` fixed-step candidate
3. `WEIGHT_DECAY=0.2225` fixed-step candidate
4. baseline `0.22` fixed-step repeat `n`

Why this is next:
- it stays on the confirmed lead family
- all other nearby adjacent axes have closed or stalled below the promotion bar
- the prior `0.218` and `0.2225` wall-clock results were the least-bad nearby ridge points, so if any residual improvement exists, this is the narrowest remaining place to look

### 2. Stop experimentation and consolidate `0.22` as the current best

Why this is ranked second:
- it is the safest option
- it yields no new information
- use it only if run budget is constrained or the priority shifts from search to reporting

### 3. Reopen broad mixed-axis search

Why this is ranked third:
- attribution would be weak
- no current evidence justifies widening the loop
- it should stay blocked until a new narrow axis is deliberately chosen

## Rejected For Tonight

- scalar reruns: rejected because `0.475` is stable but sub-threshold and `0.48125` is closed
- unembedding reruns: rejected because both `0.0047` and `0.0048` were stable and worse than baseline
- cadence or optimizer-micro: rejected because the planner produced no fresh items
- mixed-axis queues: rejected because they spend budget without solving any current ambiguity

## Operational Default

- tonight: no run
- next actual run window: use the low-prior fixed-step weight-decay ridge bracket above if another bounded experiment is warranted
