# Parallel macOS Ramp-Up Brief — 2026-04-02

## Purpose

Capture the current post-ridge operating picture before the second Mac comes online.

## Current Operating Conclusion

- do not start from scratch
- do not clone a dirty local workspace
- do not let both machines improvise frontier truth from memory
- do not reopen broad search before the second Mac proves a clean bootstrap

## Current Research Truth

- current lead family: plain `WEIGHT_DECAY=0.22`
- canonical frontier branch: `codex/execution-weight-decay-022-unembedding-followup`
- canonical frontier commit: `52769ae`
- canonical frontier `val_bpb`: `1.384010`
- latest bounded closeout: `ridge_closed`

## Current Operational Constraint

The system is still coupled to the current absolute path and local virtualenv layout.

Operational meaning:
- the easiest safe onboarding path is to match `/Users/davidabiera/Projects/team/autoresearch-macos`
- launcher scripts and control plans still assume `.venv/bin/python`
- path refactor is deferred until after the second Mac proves clean bootstrap

## Initial Role Split

- current Mac
  - owner of `codex/overnight-control`
  - owner of `codex/autoresearch-reliability`
  - responsible for durable docs, frontier declaration, and orchestration policy
- second Mac
  - first owner of `codex/execution-baseline-mar10`
  - responsible for bootstrap proof, validation, repeatability, and bounded confirmation work

After bootstrap passes:
- machine A can own one exploratory execution branch
- machine B can own one confirmation or orthogonal queue branch

## Required Durable Surfaces

Before long-running work on the second Mac:
1. pull the committed `control/docs/` packet
2. instantiate local `control/state/frontier.json` from the frontier declaration plus the template
3. create a local handoff packet
4. create a local triage board
5. record explicit machine ownership for each active branch
6. assign one next safe action per machine

## Immediate Next Safe Action

Use the committed files in `control/docs/` to:
- bootstrap the second Mac from the same absolute path
- bring it up under the Business-backed Codex app plus terminal
- keep it in validation scope first
- delay any new experiment until the bootstrap proof passes
