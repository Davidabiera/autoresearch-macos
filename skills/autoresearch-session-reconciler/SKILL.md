---
name: autoresearch-session-reconciler
description: Repo-specific autoresearch reconciliation skill. Use when handoff notes or run notes may be stale and you need regenerated narrative artifacts derived from results.tsv and control artifacts.
---

# Autoresearch Session Reconciler

Use this skill for:
- stale handoff docs
- stale run notes
- end-of-session synthesis
- preparing a clean resume point after an overnight

## Workflow

1. Run `uv run python scripts/reconcile_session.py --branch <branch> --tag <tag> --format md`.
2. Review the `stale-doc findings` block first.
3. Treat the regenerated handoff and run notes as derived text only.
4. Use `--write` only when you intentionally want to overwrite the tag-specific handoff and run-note files.

## Guardrails

- Never treat narrative Markdown as authoritative over `results.tsv`.
- Surface stale-doc findings before rewriting anything.
- Keep regenerated notes factual: frontier, wins, losses, unresolved queue, blockers.

## Follow-On Skills

- Use `$autoresearch-frontier-guard` before acting on the reconciled docs.
- Use `$autoresearch-timeout-triage` if blockers point to unresolved timeout classes.
