#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from autoresearch_lib import (
    DEFAULT_CONTROL_ROOT,
    DEFAULT_TARGET_ROOT,
    KEY_TRAIN_CONSTANTS,
    artifact_paths,
    coherence_flags,
    collect_frontier_context,
    count_non_informative,
    format_constant_value,
    top_band_results,
)


def build_handoff_text(context: dict[str, object], branch: str, target_root: Path) -> str:
    best = context["best"]
    best_commit_short = context["best_commit_short"]
    unresolved = context["unresolved_queue"]
    nearest_losses = context["nearest_losses"]
    control_state = context["control_state"]
    control_report = context["control_report"]
    flags = coherence_flags(context, target_root, branch)
    lines = [
        f"# Handoff: `{branch}`",
        "",
        "Derived artifact. Canonical precedence:",
        "1. `results.tsv`",
        "2. control state JSON",
        "3. control report Markdown",
        "4. narrative Markdown",
        "",
        "## Current Frontier",
        "",
        f"- Branch: `{branch}`",
        f"- Best commit: `{best_commit_short}`",
        f"- Best `val_bpb`: `{(best.val_bpb or 0.0):.6f}`",
        f"- Branch HEAD: `{context['head_commit']}`",
        f"- Rollback target: `{best_commit_short}`",
        "",
        "## Canonical Artifacts",
        "",
        "- Ledger: `results.tsv`",
        f"- Control state: `{Path(context['paths']['control_state']).relative_to(target_root)}`",
        f"- Control report: `{Path(context['paths']['control_report']).relative_to(target_root)}`",
        "",
        "## Confirmed Additive Wins",
        "",
    ]
    for row in context["rows"]:
        if row.status == "keep" and row.val_bpb is not None:
            lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description}")
    lines.extend(["", "## Nearest Clean Losses", ""])
    for row in nearest_losses[:5]:
        delta = (row.val_bpb or 0.0) - (best.val_bpb or 0.0)
        lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description} (delta `{delta:+.6f}`)")
    lines.extend(["", "## Remaining Queue", ""])
    if unresolved:
        for item in unresolved[:8]:
            lines.append(f"- `{item['id']}` {item['description']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Operational Blockers", ""])
    if flags:
        for flag in flags:
            lines.append(f"- [{flag['severity']}] {flag['artifact']}: {flag['message']}")
    else:
        lines.append("- none")

    if control_report:
        lines.extend(["", "## Latest Control Window", ""])
        lines.append(f"- attempted: `{control_report.get('attempted', 0)}`")
        lines.append(f"- keeps: `{control_report.get('keeps', 0)}`")
        lines.append(f"- discards: `{control_report.get('discards', 0)}`")
        lines.append(f"- crashes: `{control_report.get('crashes', 0)}`")
        lines.append(f"- stopped because: `{control_report.get('stopped_reason', 'unknown')}`")
    elif control_state:
        counts = count_non_informative(control_state)
        lines.extend(["", "## Latest Control Window", ""])
        lines.append(f"- informative: `{counts['informative']}`")
        lines.append(f"- timeouts: `{counts['timeout']}`")
        lines.append(f"- crashes: `{counts['crash']}`")

    return "\n".join(lines) + "\n"


def build_run_notes_text(context: dict[str, object], branch: str) -> str:
    best = context["best"]
    best_commit_short = context["best_commit_short"]
    control_state = context["control_state"]
    completed = list(control_state.get("completed", [])) if control_state else []
    top_results = top_band_results(completed)
    reason_counts = Counter(str(item.get("reason") or "unknown") for item in completed if item.get("status") == "crash")
    lines = [
        f"# Run Notes: `{branch}`",
        "",
        "Derived artifact. Treat this file as a narrative summary, not the source of truth.",
        "",
        "## Current State",
        "",
        f"- Baseline commit: `{context['rows'][0].commit}`",
        f"- Baseline `val_bpb`: `{(context['rows'][0].val_bpb or 0.0):.6f}`",
        f"- Current best commit: `{best_commit_short}`",
        f"- Current best `val_bpb`: `{(best.val_bpb or 0.0):.6f}`",
        f"- Current branch HEAD: `{context['head_commit']}`",
        "",
        "## Canonical Precedence",
        "",
        "- `results.tsv`",
        "- control state JSON",
        "- control report Markdown",
        "- narrative Markdown",
        "",
        "## Frontier Settings",
        "",
    ]
    for name in KEY_TRAIN_CONSTANTS:
        if name in context["best_train_constants"]:
            lines.append(f"- `{name}` = `{format_constant_value(context['best_train_constants'][name])}`")

    lines.extend(["", "## Confirmed Additive Wins", ""])
    for row in context["rows"]:
        if row.status == "keep" and row.val_bpb is not None:
            lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description}")

    lines.extend(["", "## Dead Ends", ""])
    for row in context["rows"]:
        if row.status == "discard" and row.val_bpb is not None:
            lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description}")

    lines.extend(["", "## Latest Evaluated Band", ""])
    if top_results:
        for item in top_results:
            lines.append(f"- `{item['commit']}` `{float(item['val_bpb']):.6f}` `{item['status']}` {item['description']}")
    else:
        lines.append("- no control-band detail available")

    lines.extend(["", "## Non-Informative Outcomes", ""])
    if reason_counts:
        for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            lines.append(f"- `{count}` `{reason}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Next Candidate", ""])
    unresolved = context["unresolved_queue"]
    if unresolved:
        lines.append(f"- `{unresolved[0]['id']}` {unresolved[0]['description']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_output(target_root: Path, branch: str, tag: str, control_root: Path | None) -> dict[str, object]:
    context = collect_frontier_context(target_root, branch, control_root=control_root, tag=tag)
    paths = artifact_paths(target_root, branch, control_root=control_root, tag=tag)
    return {
        "branch": branch,
        "tag": tag,
        "canonical_frontier": {
            "best_commit": context["best_commit_short"],
            "best_val": round(context["best"].val_bpb or 0.0, 6),
            "head_commit": context["head_commit"],
        },
        "stale_doc_findings": coherence_flags(context, target_root, branch),
        "handoff_text": build_handoff_text(context, branch, target_root),
        "run_notes_text": build_run_notes_text(context, branch),
        "targets": {
            "handoff": str(paths["handoff"]),
            "run_notes": str(paths["run_notes"]),
        },
    }


def render_markdown(payload: dict[str, object]) -> str:
    frontier = payload["canonical_frontier"]
    lines = [
        f"# Session Reconciliation: `{payload['branch']}`",
        "",
        "## Canonical Frontier",
        "",
        f"- Best commit: `{frontier['best_commit']}`",
        f"- Best `val_bpb`: `{frontier['best_val']:.6f}`",
        f"- Current `HEAD`: `{frontier['head_commit']}`",
        "",
        "## Stale-Doc Findings",
        "",
    ]
    findings = payload["stale_doc_findings"]
    if findings:
        for finding in findings:
            lines.append(f"- [{finding['severity']}] {finding['artifact']}: {finding['message']}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Regenerated Handoff",
            "",
            payload["handoff_text"].rstrip(),
            "",
            "## Regenerated Run Notes",
            "",
            payload["run_notes_text"].rstrip(),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile narrative session docs from canonical artifacts.")
    parser.add_argument("--branch", required=True, help="Branch to inspect, e.g. autoresearch/mar10")
    parser.add_argument("--tag", help="Explicit run tag; defaults to the branch suffix")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--write", action="store_true", help="Overwrite the tag-specific handoff and run notes files")
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    control_root = Path(args.control_root).resolve()
    tag = args.tag or args.branch.split("/", 1)[1]
    payload = build_output(target_root, args.branch, tag, control_root)
    if args.write:
        targets = payload["targets"]
        handoff_path = Path(targets["handoff"])
        run_notes_path = Path(targets["run_notes"])
        handoff_path.write_text(payload["handoff_text"])
        run_notes_path.write_text(payload["run_notes_text"])
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(render_markdown(payload))


if __name__ == "__main__":
    main()
