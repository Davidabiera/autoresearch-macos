---
name: autoresearch-frontier-guard
description: Guardrailed repo-specific autoresearch operator skill. Use when resuming a run, checking where the frontier stands, validating coherence between results.tsv and control artifacts, or before launching the next experiment on this repo.
---

# Autoresearch Frontier Guard

Use this skill for:
- "where do we stand"
- "resume the run"
- "continue the branch"
- "kick off the next experiment"

## Workflow

1. Run `uv run python scripts/frontier_status.py --branch <branch> --format md`.
2. Treat `results.tsv` as the ledger of record.
3. Treat control state and control report as secondary canonical artifacts.
4. Treat handoff and run-note Markdown as derived only.
5. If the output contains any `error` coherence flags, stop and surface the exact mismatches before planning or running another experiment.

## Guardrails

- Require `HEAD` to equal the canonical best commit before queue execution.
- Require the current `train.py` constants to match the frontier constants before queue execution.
- Require remaining queue items to be single-variable changes.
- If the handoff is stale, direct the workflow through `$autoresearch-session-reconciler` before trusting narrative docs.

## Follow-On Skills

- Use `$autoresearch-queue-planner` to generate the next queue once the frontier is coherent.
- Use `$autoresearch-timeout-triage` when a failed or suspicious run log needs classification.
