# Parallel macOS Ramp-Up Pack

Use this pack when bringing a second Mac and a second Codex into `autoresearch-macos`.

The goal is not "more agents". The goal is more reliable leverage:
- one canonical frontier
- one owner per branch/worktree
- one clean handoff format
- one control surface that survives sleep, reboot, and context loss

## Current local reality

As of `2026-04-02`, the repo already has durable remote-tracked branches for the main operating lanes:
- `codex/overnight-control`
- `codex/autoresearch-reliability`
- `codex/execution-baseline-mar10`
- `codex/execution-weight-decay-022-ridge`
- `codex/execution-weight-decay-022-scalar`
- `codex/execution-weight-decay-022-scalar-confirmation`
- `codex/execution-weight-decay-022-scalar-048125-confirmation`
- `codex/execution-weight-decay-022-unembedding-followup`

The current durable frontier declaration is:
- branch: `codex/execution-weight-decay-022-unembedding-followup`
- commit: `52769ae`
- `val_bpb`: `1.384010`
- next safe action: `do not rerun the ridge bracket; consolidate first`

This means:
- do not restart from scratch
- do not copy a dirty local workspace to the new Mac
- do not collapse everything back into one branch
- do not infer current frontier truth from chat or stale local notes

## Non-negotiables

1. Clean clone, not dirty workspace copy.
   - The second Mac should start from a fresh clone or fetch of the remote branches.
2. Control branch is the coordination authority.
   - Plans, queues, reports, ledger state, and handoff material belong here.
3. Runtime artifacts stay local unless distilled.
   - Raw logs, ad hoc notes, and transient state are evidence, not durable truth.
4. One canonical frontier at a time.
   - Frontier truth should live in `control/state/frontier.json`, not in chat memory.
5. One owner per branch/worktree.
   - No concurrent mutation of the same execution branch from two machines.
6. Match the same absolute path first.
   - The current launcher and control plan surfaces are coupled to `/Users/davidabiera/Projects/team/autoresearch-macos` and `.venv/bin/python`.
7. Validation first, then wider search.
   - Even though trust is currently passed, the second Mac still starts as a validation node until the machine bootstrap is proven clean.

## Branch role map

- `codex/overnight-control`
  - coordination authority
  - plans, queues, reports, triage, frontier ledger
- `codex/autoresearch-reliability`
  - orchestration, reboot safety, runtime forensics, stability tooling
- `codex/execution-baseline-mar10`
  - trust-path and fixed-step validation lane
- `codex/execution-*`
  - bounded execution lanes for exploration or confirmation
- `autoresearch/*`
  - broader research narrative and closeout/handoff material

## Default machine roles

Current bootstrap phase:
- current Mac: control plus reliability owner
- second Mac: validation and confirmation node

After the second Mac proves a clean bootstrap:
- machine A: frontier exploration on exactly one execution branch
- machine B: confirmation or bounded orthogonal queue from the same validated base commit

Do not run two independent frontier-mutating loops against the same branch.

## Bring-up sequence for the second Mac

1. Clone the repo cleanly at `/Users/davidabiera/Projects/team/autoresearch-macos` and fetch all remote branches.
2. Check out `codex/overnight-control` first.
3. Read:
   - `AGENTS.md`
   - `README.md`
   - `program.md`
   - `control/docs/parallel_macos_bootstrap.md`
   - `control/docs/mar10_frontier_declaration_20260402.md`
   - `control/docs/mar10_second_mac_bootstrap_focus_20260403.md`
   - `control/docs/parallel_macos_ramp_up_brief_20260402.md`
   - `control/docs/second_mac_bootstrap_checklist_20260402.md`
   - `control/docs/second_mac_kickoff_prompt.md`
4. Copy `control/docs/frontier_ledger_template.json` to `control/state/frontier.json` if the real ledger does not exist yet.
5. Fill `frontier.json` from the frontier declaration plus the latest trusted report and branch state.
6. Create or update a handoff packet from `control/docs/handoff_packet_template.md`.
7. Create or update a triage board from `control/docs/triage_board_template.md`.
8. Only then assign the second Mac a role, branch, and queue.

## What the second AI must know

It must enter with these assumptions:
- the repo is already multi-lane
- current truth is not inferred from chat history
- branch ownership is explicit
- the second Mac must prove setup cleanliness before it earns exploration work
- support branches do not get merged into research branches just to "simplify"

It must not assume:
- the most recent attractive number is trusted
- local runtime logs are authoritative by themselves
- the current frontier can be guessed from a stale handoff note
- a second machine should immediately start free exploration

## Shared coordination files

These are the minimum shared surfaces:
- `control/state/frontier.json`
  - canonical frontier truth
- `control/reports/<handoff>.md`
  - human-readable handoff packet
- `control/reports/<triage>.md`
  - task board for `Blocked`, `Ready`, `Running`, `Needs Review`, `Closed`
- `control/queues/*.jsonl`
  - bounded experiment queues
- `control/plans/*.json`
  - machine-readable control plans

## Decision rules

Use these rules before assigning work:

If the second Mac has not yet passed bootstrap validation:
- second Mac works trust-path, repeatability, fixed-step confirmation, or resume/reboot validation
- do not widen exploratory search

If `trust_status == "passed"` and frontier ownership is clear and the second Mac bootstrap is proven:
- assign one machine to exploration
- assign the other to confirmation or one bounded orthogonal queue

If frontier ownership is ambiguous:
- stop assigning new work
- repair `frontier.json` and handoff first

If both machines need the same branch:
- they are over-coupled
- split the work by branch or by role before proceeding

## Failure modes to avoid

- frontier truth living only in conversation memory
- two machines editing the same execution branch
- using raw local logs as the main source of truth
- letting ad hoc handoff files replace tracked control surfaces
- starting the second Mac without an owner map, frontier ledger, and next-safe-action field

## Companion files in this pack

- `control/docs/mar10_frontier_declaration_20260402.md`
- `control/docs/mar10_second_mac_bootstrap_focus_20260403.md`
- `control/docs/parallel_macos_ramp_up_brief_20260402.md`
- `control/docs/second_mac_bootstrap_checklist_20260402.md`
- `control/docs/second_mac_kickoff_prompt.md`
- `control/docs/handoff_packet_template.md`
- `control/docs/triage_board_template.md`
- `control/docs/frontier_ledger_template.json`
- `control/docs/parallel_macos_ramp_up_brief_20260401.md`
