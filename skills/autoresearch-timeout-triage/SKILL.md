---
name: autoresearch-timeout-triage
description: Repo-specific autoresearch log triage skill. Use when a run crashes, times out, or looks suspicious and you need a deterministic classification plus a retry, discard, or queue-adjustment recommendation.
---

# Autoresearch Timeout Triage

Use this skill for:
- failed overnight items
- `RUNNER_TIMEOUT` logs
- suspicious long `total_seconds`
- assertion or OOM diagnosis

## Workflow

1. Run `uv run python scripts/classify_run.py --log <path> --format md`.
2. If a control-state JSON exists, pass `--control-state <path>` to add repeated-timeout context.
3. Use the output fields as the authoritative classification:
   - `status_class`
   - `informative`
   - `issue_scope`
   - `suggested_action`

## Interpretation Rules

- `watchdog-timeout` means the runner limit fired before a usable summary.
- `post-train-overrun` means the model produced usable metrics, but post-train runtime expanded enough to threaten overnight throughput.
- `config-invalid` and `resource-oom` are experiment-specific failures; do not blame the runner.
- `unknown-crash` is unresolved; surface the exact reason string before deciding to rerun.

## Follow-On Skills

- Use `$autoresearch-frontier-guard` before resuming the branch after a failed run.
- Use `$autoresearch-queue-planner` if the recommendation is `queue-adjustment`.
