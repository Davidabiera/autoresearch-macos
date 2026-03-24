---
name: autoresearch-queue-planner
description: Repo-specific autoresearch queue planning skill. Use when you need the next safe experiment band, deduped against results.tsv and current queue state, without reopening broad search.
---

# Autoresearch Queue Planner

Use this skill for:
- "what should we run next"
- building the next micro-band
- resuming an unfinished overnight queue

## Workflow

1. Run `uv run python scripts/build_queue.py --branch <branch> --band optimizer-micro --format md`.
2. If needed, switch bands:
   - `optimizer-micro`
   - `cadence`
   - `stability`
3. Use `--out <jsonl>` when you want a fresh queue file.

## Guardrails

- Prefer unresolved queue items from control state before inventing new experiments.
- Do not emit duplicate descriptions that already exist in `results.tsv`.
- Do not emit duplicate ids that already exist in the current queue or control state.
- Keep every queue item to a single assignment only.
- Stay optimizer- and schedule-local unless explicitly told to widen scope.

## Follow-On Skills

- Run `$autoresearch-frontier-guard` first if branch/head coherence is unknown.
- Run `$autoresearch-session-reconciler` after a queue finishes and the narrative docs need rebuilding.
