#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoresearch_lib import (
    DEFAULT_CONTROL_ROOT,
    DEFAULT_TARGET_ROOT,
    KEY_TRAIN_CONSTANTS,
    artifact_paths,
    coherence_flags,
    collect_frontier_context,
    count_non_informative,
    format_constant_map,
    maybe_short_commit,
    summarize_artifact_status,
)


def build_payload(target_root: Path, branch: str, control_root: Path | None) -> dict[str, object]:
    context = collect_frontier_context(target_root, branch, control_root=control_root)
    best = context["best"]
    best_commit_short = context["best_commit_short"]
    paths = artifact_paths(target_root, branch, control_root=control_root, tag=context["tag"])
    next_candidate = context["fresh_unresolved_queue"][0] if context["fresh_unresolved_queue"] else None
    flags = coherence_flags(context, target_root, branch)
    execution_ready = not any(flag["severity"] == "error" for flag in flags)
    control_counts = count_non_informative(context["control_state"])

    payload: dict[str, object] = {
        "branch": branch,
        "tag": context["tag"],
        "current_best_commit": best_commit_short,
        "current_best_val": round(best.val_bpb or 0.0, 6),
        "head_commit": context["head_commit"],
        "head_matches_frontier": context["head_commit"] == best_commit_short,
        "frontier_constants": format_constant_map(context["best_train_constants"]),
        "current_worktree_constants": format_constant_map(context["current_train_constants"]),
        "rollback_target_commit": best_commit_short,
        "coherence_flags": flags,
        "recommended_next_candidate": next_candidate,
        "remaining_queue_count": len(context["fresh_unresolved_queue"]),
        "gated_result_count": len(context["gated_results"]),
        "execution_ready": execution_ready,
        "artifacts": {
            "results": str(context["results_path"]),
            "handoff": str(paths["handoff"]),
            "run_notes": str(paths["run_notes"]),
            "control_state": str(paths["control_state"]),
            "gated_results": str(paths["gated_results"]),
            "control_report": str(paths["control_report"]),
            "canonical_eval": str(paths["canonical_eval"]),
        },
        "latest_control_counts": control_counts,
        "git_status_lines": context["git_status_lines"],
    }
    return payload


def render_markdown(target_root: Path, context: dict[str, object], payload: dict[str, object]) -> str:
    best = context["best"]
    canonical_value = best.val_bpb or 0.0
    head_row = context["head_row"]
    control_state = context["control_state"]
    control_report = context["control_report"]
    handoff_frontier = context["handoff_frontier"]
    branch = str(payload["branch"])
    best_commit_short = str(payload["current_best_commit"])

    lines = [
        f"# Frontier Status: `{branch}`",
        "",
        "## Canonical Frontier",
        "",
        f"- Best commit: `{best_commit_short}`",
        f"- Best `val_bpb`: `{canonical_value:.6f}`",
        f"- Current `HEAD`: `{context['head_commit']}`",
        f"- Execution ready: `{str(payload['execution_ready']).lower()}`",
        f"- Gated results recorded: `{payload['gated_result_count']}`",
        "",
        "## Frontier Settings",
        "",
    ]
    frontier_constants = payload["frontier_constants"]
    current_constants = payload["current_worktree_constants"]
    for name in KEY_TRAIN_CONSTANTS:
        expected = frontier_constants.get(name)  # type: ignore[union-attr]
        current = current_constants.get(name)  # type: ignore[union-attr]
        suffix = ""
        if expected != current:
            suffix = f" (current worktree: `{current}`)"
        lines.append(f"- `{name}` = `{expected}`{suffix}")

    lines.extend(["", "## Coherence", ""])
    lines.append(summarize_artifact_status("results.tsv", best_commit_short, canonical_value, best_commit_short, canonical_value))
    lines.append(
        summarize_artifact_status(
            "HEAD",
            context["head_commit"],
            head_row.val_bpb if head_row is not None else None,
            best_commit_short,
            canonical_value,
        )
    )
    if control_state:
        lines.append(
            summarize_artifact_status(
                "control state",
                maybe_short_commit(target_root, str(control_state.get("current_best_commit") or "")),
                float(control_state["current_best_val"]) if control_state.get("current_best_val") is not None else None,
                best_commit_short,
                canonical_value,
            )
        )
    else:
        lines.append("- control state: missing")
    if control_report:
        lines.append(
            summarize_artifact_status(
                "control report",
                maybe_short_commit(target_root, str(control_report.get("end_best_commit") or "")),
                float(control_report["end_best_val"]) if control_report.get("end_best_val") is not None else None,
                best_commit_short,
                canonical_value,
            )
        )
    else:
        lines.append("- control report: missing")
    if handoff_frontier and "best_commit" in handoff_frontier:
        lines.append(
            summarize_artifact_status(
                "handoff",
                maybe_short_commit(target_root, handoff_frontier["best_commit"]),
                float(handoff_frontier["best_val"]),
                best_commit_short,
                canonical_value,
            )
        )
    else:
        lines.append("- handoff: missing")

    lines.extend(["", "## Guardrails", ""])
    flags = payload["coherence_flags"]  # type: ignore[assignment]
    if flags:
        for flag in flags:
            lines.append(f"- [{flag['severity']}] {flag['artifact']}: {flag['message']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Next Candidate", ""])
    candidate = payload["recommended_next_candidate"]
    if candidate:
        lines.append(f"- `{candidate['id']}` {candidate['description']}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report canonical frontier state for an autoresearch branch.")
    parser.add_argument("--branch", required=True, help="Branch to inspect, e.g. autoresearch/mar10")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    control_root = Path(args.control_root).resolve()
    context = collect_frontier_context(target_root, args.branch, control_root=control_root)
    payload = build_payload(target_root, args.branch, control_root)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(render_markdown(target_root, context, payload), end="")


if __name__ == "__main__":
    main()
