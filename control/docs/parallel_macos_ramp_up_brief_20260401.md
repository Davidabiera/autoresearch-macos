# Parallel macOS Ramp-Up Brief

Date: `2026-04-01`

## Purpose

Capture the current local operating picture before bringing a second Mac and second Codex into the system.

## Durable branch map

- control branch: `codex/overnight-control` at `22787a1`
- reliability branch: `codex/autoresearch-reliability` at `91c323e`
- execution baseline branch: `codex/execution-baseline-mar10` at `c7f7325`
- execution lane: `codex/execution-weight-decay-022-scalar` at `52769ae`
- execution lane: `codex/execution-weight-decay-022-scalar-confirmation` at `a6a97d3`
- execution lane: `codex/execution-weight-decay-022-scalar-048125-confirmation` at `a8337e1`
- execution lane: `codex/execution-weight-decay-022-unembedding-followup` at `52769ae`

## Current operating conclusion

- do not start from scratch
- do not clone a dirty local workspace
- do not let both machines improvise the frontier from memory
- do not widen exploration until trust status is made explicit

## Current constraint

The system still has an unresolved trust-path problem.

Operational meaning:
- attractive numbers are not enough by themselves
- the second Mac should start as a validation and confirmation node
- the first Mac should continue to own control and reliability surfaces until the trust path is clear

## Initial role split

- current Mac
  - owner of `codex/overnight-control`
  - owner of `codex/autoresearch-reliability`
  - responsible for frontier ledger, handoff packet, triage board, and orchestration policy
- second Mac
  - first owner of `codex/execution-baseline-mar10`
  - responsible for trust-path validation, repeatability, and bounded confirmation work

After trust passes:
- machine A can own one exploratory execution branch
- machine B can own one confirmation or orthogonal queue branch

## Required control surfaces before long-running work

1. instantiate `control/state/frontier.json` from `control/docs/frontier_ledger_template.json`
2. create a current handoff packet from `control/docs/handoff_packet_template.md`
3. create a current triage board from `control/docs/triage_board_template.md`
4. record explicit machine ownership for each active branch
5. assign one next safe action per machine

## What remains local-only

- raw runtime logs
- transient state bundles
- ad hoc notes
- temporary investigation artifacts

These should be distilled into:
- control reports
- control queues
- frontier ledger updates
- reviewer-backed conclusions

## Do not do

- do not let two machines edit the same execution branch
- do not let the second Mac enter open-ended search before trust status is explicit
- do not treat a stale handoff note as canonical truth
- do not merge support branches into the research branch just to simplify the picture

## Next safe action

Use the files in `control/docs/` to stand up:
- one frontier ledger
- one handoff packet
- one triage board
- one kickoff prompt for the second Mac

Then onboard the second Mac against the clean remote branches and keep it in trust-path scope first.
