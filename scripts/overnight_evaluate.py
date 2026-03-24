#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_ROOT = ROOT
DEFAULT_CONTROL_ROOT = ROOT / "worktrees" / "control" / "control"
OUTPUT_DIR = ROOT / "reports"
KEY_TRAIN_CONSTANTS = (
    "TOTAL_BATCH_SIZE",
    "DEVICE_BATCH_SIZE",
    "EMBEDDING_LR",
    "UNEMBEDDING_LR",
    "MATRIX_LR",
    "SCALAR_LR",
    "WEIGHT_DECAY",
    "ADAM_BETAS",
    "WARMUP_RATIO",
    "WARMDOWN_RATIO",
    "FINAL_LR_FRAC",
    "DEPTH",
)
HANDOFF_FRONTIER_PATTERNS = {
    "best_commit": re.compile(r"^- Best commit: `([^`]+)`$", re.MULTILINE),
    "best_val": re.compile(r"^- Best `val_bpb`: `([0-9.]+)`$", re.MULTILINE),
}
CONTROL_REPORT_PATTERNS = {
    "start_best_commit": re.compile(r"^- start best: `([^`]+)` / `([0-9.]+)`$", re.MULTILINE),
    "end_best_commit": re.compile(r"^- end best: `([^`]+)` / `([0-9.]+)`$", re.MULTILINE),
    "attempted": re.compile(r"^- experiments attempted: `([0-9]+)`$", re.MULTILINE),
    "keeps": re.compile(r"^- keeps: `([0-9]+)`$", re.MULTILINE),
    "discards": re.compile(r"^- discards: `([0-9]+)`$", re.MULTILINE),
    "crashes": re.compile(r"^- crashes: `([0-9]+)`$", re.MULTILINE),
    "timeouts": re.compile(r"^- timeouts: `([0-9]+)`$", re.MULTILINE),
    "stopped_reason": re.compile(r"^- stopped because: `([^`]+)`$", re.MULTILINE),
}


class EvaluationError(RuntimeError):
    pass


@dataclass
class ResultRow:
    line_number: int
    commit: str
    description: str
    status: str
    val_bpb: float | None
    memory_gb: float | None


def branch_tag(branch: str) -> str:
    return branch.split("/", 1)[1] if "/" in branch else branch


def run_git(target_root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=target_root,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise EvaluationError(
            f"git {' '.join(args)} failed in {target_root}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def short_commit(target_root: Path, commit: str) -> str:
    return run_git(target_root, ["rev-parse", "--short", commit])


def maybe_short_commit(target_root: Path, commit: str) -> str | None:
    if not commit:
        return None
    try:
        return short_commit(target_root, commit)
    except EvaluationError:
        return None


def parse_python_constants_from_text(source: str) -> dict[str, Any]:
    module = ast.parse(source)
    values: dict[str, Any] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        try:
            expr = ast.Expression(node.value)
            values[node.targets[0].id] = eval(compile(expr, "<constants>", "eval"), {"__builtins__": {}}, {})
        except Exception:
            continue
    return values


def parse_python_constants(path: Path) -> dict[str, Any]:
    return parse_python_constants_from_text(path.read_text())


def format_constant_value(value: Any) -> str:
    if isinstance(value, tuple):
        return "(" + ", ".join(format_constant_value(item) for item in value) + ")"
    return str(value)


def read_commit_train_constants(target_root: Path, commit: str) -> dict[str, Any]:
    source = run_git(target_root, ["show", f"{commit}:train.py"])
    return parse_python_constants_from_text(source)


def parse_results(results_path: Path) -> list[ResultRow]:
    if not results_path.exists():
        raise EvaluationError(f"results file not found: {results_path}")
    rows: list[ResultRow] = []
    with results_path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for index, row in enumerate(reader, start=2):
            raw_val = (row.get("val_bpb") or "").strip()
            raw_mem = (row.get("memory_gb") or "").strip()
            status = (row.get("status") or "").strip()
            if raw_val in {"", "NA", "0.000000"} or status == "crash":
                val_bpb = None
            else:
                val_bpb = float(raw_val)
            memory_gb = None if raw_mem in {"", "NA"} else float(raw_mem)
            rows.append(
                ResultRow(
                    line_number=index,
                    commit=(row.get("commit") or "").strip(),
                    description=(row.get("description") or "").strip(),
                    status=status,
                    val_bpb=val_bpb,
                    memory_gb=memory_gb,
                )
            )
    return rows


def best_result(rows: list[ResultRow]) -> ResultRow:
    informative = [row for row in rows if row.val_bpb is not None]
    if not informative:
        raise EvaluationError("results.tsv does not contain any informative results")
    return min(informative, key=lambda row: row.val_bpb)


def find_result_by_commit(rows: list[ResultRow], commit: str) -> ResultRow | None:
    for row in rows:
        if row.commit == commit:
            return row
    return None


def previous_keep(rows: list[ResultRow], line_number: int) -> ResultRow | None:
    candidates = [row for row in rows if row.status == "keep" and row.val_bpb is not None and row.line_number < line_number]
    if not candidates:
        return None
    return candidates[-1]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def parse_handoff_frontier(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    best_commit_match = HANDOFF_FRONTIER_PATTERNS["best_commit"].search(text)
    best_val_match = HANDOFF_FRONTIER_PATTERNS["best_val"].search(text)
    if not best_commit_match or not best_val_match:
        return {"path": path, "status": "missing frontier summary"}
    return {
        "path": path,
        "best_commit": best_commit_match.group(1),
        "best_val": float(best_val_match.group(1)),
    }


def parse_control_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    payload: dict[str, Any] = {"path": path}
    for key, pattern in CONTROL_REPORT_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        if key == "start_best_commit":
            payload["start_best_commit"] = match.group(1)
            payload["start_best_val"] = float(match.group(2))
        elif key == "end_best_commit":
            payload["end_best_commit"] = match.group(1)
            payload["end_best_val"] = float(match.group(2))
        elif key == "stopped_reason":
            payload["stopped_reason"] = match.group(1)
        else:
            payload[key] = int(match.group(1))
    return payload


def classify_completed_item(item: dict[str, Any]) -> str:
    reason = str(item.get("reason") or "").lower()
    if item.get("status") == "crash" and "timeout" in reason:
        return "timeout"
    if item.get("status") == "crash":
        return "crash"
    return "informative"


def nearest_clean_losses(rows: list[ResultRow], best_val: float, limit: int = 5) -> list[ResultRow]:
    discards = [row for row in rows if row.status == "discard" and row.val_bpb is not None]
    return sorted(discards, key=lambda row: (row.val_bpb - best_val, row.val_bpb))[:limit]


def top_band_results(completed: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    informative = [item for item in completed if item.get("status") in {"keep", "discard"} and item.get("val_bpb") is not None]
    return sorted(informative, key=lambda item: float(item["val_bpb"]))[:limit]


def describe_remaining_band(items: list[dict[str, Any]]) -> str | None:
    if not items:
        return None
    buckets: dict[str, list[str]] = {}
    for item in items[:6]:
        assignments = item.get("assignments") or {}
        if not assignments:
            continue
        name, value = next(iter(assignments.items()))
        buckets.setdefault(name, []).append(str(value))
    if not buckets:
        return None
    parts = [f"{name}: {', '.join(values)}" for name, values in buckets.items()]
    return "; ".join(parts)


def resolve_branch_contains(target_root: Path, commit: str, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, branch],
        cwd=target_root,
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def format_metric_delta(previous: float, current: float) -> str:
    delta = previous - current
    sign = "+" if delta >= 0 else "-"
    return f"{sign}{abs(delta):.6f}"


def summarize_artifact_status(
    label: str,
    commit: str | None,
    value: float | None,
    canonical_commit: str,
    canonical_value: float,
) -> str:
    if commit is None:
        return f"- {label}: missing"
    if value is None:
        if commit == canonical_commit:
            return f"- {label}: current (`{commit}` / metric unavailable)"
        return f"- {label}: stale (`{commit}` / metric unavailable vs canonical `{canonical_commit}` / `{canonical_value:.6f}`)"
    if commit == canonical_commit and abs(value - canonical_value) < 1e-9:
        return f"- {label}: current (`{commit}` / `{value:.6f}`)"
    return f"- {label}: stale (`{commit}` / `{value:.6f}` vs canonical `{canonical_commit}` / `{canonical_value:.6f}`)"


def build_report(args: argparse.Namespace) -> tuple[Path, str]:
    target_root = Path(args.target_worktree).resolve()
    control_root = Path(args.control_root).resolve()
    tag = branch_tag(args.branch)
    results_path = target_root / "results.tsv"
    handoff_path = target_root / "HANDOFF_mar10.md"
    run_notes_path = target_root / "RUN_NOTES_mar10.md"
    beta_report_path = target_root / "BETA_REPORT_mar10.md"
    state_path = control_root / "state" / f"overnight_{tag}.json"
    control_report_path = control_root / "reports" / f"overnight_{tag}.md"

    rows = parse_results(results_path)
    best = best_result(rows)
    prior_frontier = previous_keep(rows, best.line_number)
    current_branch = run_git(target_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    current_head = run_git(target_root, ["rev-parse", "--short", "HEAD"])
    best_commit_short = maybe_short_commit(target_root, best.commit) or best.commit
    current_head_row = find_result_by_commit(rows, current_head)
    current_train_constants = parse_python_constants(target_root / "train.py")
    best_train_constants = read_commit_train_constants(target_root, best.commit)
    control_state = load_json(state_path)
    control_report = parse_control_report(control_report_path)
    handoff_frontier = parse_handoff_frontier(handoff_path)

    completed = list(control_state.get("completed", [])) if control_state else []
    top_results = top_band_results(completed)
    timeout_items = [item for item in completed if classify_completed_item(item) == "timeout"]
    crash_items = [item for item in completed if classify_completed_item(item) == "crash"]
    informative_items = [item for item in completed if classify_completed_item(item) == "informative"]
    nearest_losses = nearest_clean_losses(rows, best.val_bpb or 0.0)

    next_candidate = None
    next_band_summary = None
    if control_state:
        queue_index = int(control_state.get("queue_index", 0))
        resolved_queue = list(control_state.get("resolved_queue", []))
        if queue_index < len(resolved_queue):
            next_candidate = resolved_queue[queue_index]
            next_band_summary = describe_remaining_band(resolved_queue[queue_index:])

    head_matches_best = current_head == best_commit_short
    branch_contains_best = resolve_branch_contains(target_root, best.commit, args.branch)
    prioritize_process = len(timeout_items) >= max(3, len(informative_items))

    recommendation_lines: list[str] = []
    if current_branch != args.branch:
        recommendation_lines.append(
            f"- Branch position: check out `{args.branch}` before continuing; current branch is `{current_branch}`."
        )
    elif head_matches_best:
        recommendation_lines.append(
            f"- Branch position: stay on `{args.branch}` at `HEAD`; it already matches the canonical best commit `{best_commit_short}`."
        )
    elif branch_contains_best:
        recommendation_lines.append(
            f"- Branch position: stay on `{args.branch}`, but reset or checkout `{best_commit_short}` before the next run because `HEAD` is `{current_head}`."
        )
    else:
        recommendation_lines.append(
            f"- Branch position: reconcile branch history before continuing; canonical best `{best_commit_short}` is not clearly contained in `{args.branch}`."
        )

    if prioritize_process:
        recommendation_lines.append(
            f"- Process priority: fix timeout/coherence issues before another long overnight; {len(timeout_items)} of {len(completed) or 0} completed items were watchdog timeouts."
        )
    else:
        recommendation_lines.append("- Process priority: runner fixes are secondary; the last overnight produced enough informative signal to continue the experiment band directly.")

    if next_candidate:
        recommendation = f"`{next_candidate['id']}` {next_candidate['description']}"
        if next_band_summary:
            recommendation += f" (remaining band: {next_band_summary})"
        recommendation_lines.append(f"- Next experiment band: resume with {recommendation}.")
    elif nearest_losses:
        fallback_band = "; ".join(f"`{row.commit}` {row.description}" for row in nearest_losses[:3])
        recommendation_lines.append(f"- Next experiment band: derive the next queue from the nearest clean losses around the frontier, starting with {fallback_band}.")
    else:
        recommendation_lines.append("- Next experiment band: no pending queue candidate was found; synthesize a fresh micro-band around the current best settings.")

    coherence_lines = [
        summarize_artifact_status("results.tsv", best_commit_short, best.val_bpb, best_commit_short, best.val_bpb or 0.0),
        summarize_artifact_status(
            "HEAD",
            current_head,
            current_head_row.val_bpb if current_head_row is not None else None,
            best_commit_short,
            best.val_bpb or 0.0,
        ),
    ]
    if control_state:
        coherence_lines.append(
            summarize_artifact_status(
                "control state",
                maybe_short_commit(target_root, str(control_state.get("current_best_commit") or "")),
                float(control_state["current_best_val"]) if control_state.get("current_best_val") is not None else None,
                best_commit_short,
                best.val_bpb or 0.0,
            )
        )
    else:
        coherence_lines.append("- control state: missing")
    if control_report:
        coherence_lines.append(
            summarize_artifact_status(
                "control report",
                maybe_short_commit(target_root, str(control_report.get("end_best_commit") or "")),
                float(control_report["end_best_val"]) if control_report.get("end_best_val") is not None else None,
                best_commit_short,
                best.val_bpb or 0.0,
            )
        )
    else:
        coherence_lines.append("- control report: missing")
    if handoff_frontier and "best_commit" in handoff_frontier and "best_val" in handoff_frontier:
        coherence_lines.append(
            summarize_artifact_status(
                "handoff current frontier",
                maybe_short_commit(target_root, handoff_frontier["best_commit"]),
                float(handoff_frontier["best_val"]),
                best_commit_short,
                best.val_bpb or 0.0,
            )
        )
    else:
        coherence_lines.append("- handoff current frontier: missing")

    lines: list[str] = [
        f"# Canonical Overnight Evaluation: `{tag}`",
        "",
        "## Summary",
        "",
        f"- evaluated branch: `{args.branch}`",
        f"- canonical best: `{best_commit_short}` / `{best.val_bpb:.6f}` from `{best.description}`",
        f"- current git position: branch `{current_branch}`, `HEAD` `{current_head}`",
        f"- ledger rows: `{len(rows)}` total, `{sum(1 for row in rows if row.status == 'keep')}` keeps, `{sum(1 for row in rows if row.status == 'discard')}` discards, `{sum(1 for row in rows if row.status == 'crash')}` crashes",
    ]
    if prior_frontier and prior_frontier.val_bpb is not None:
        lines.append(
            f"- prior frontier: `{prior_frontier.commit}` / `{prior_frontier.val_bpb:.6f}` from `{prior_frontier.description}`; improvement to current frontier: `{format_metric_delta(prior_frontier.val_bpb, best.val_bpb or 0.0)}`"
        )
    else:
        lines.append("- prior frontier: unavailable")
    if control_report:
        lines.append(
            f"- latest overnight control run: `{control_report.get('attempted', 0)}` attempted, `{control_report.get('keeps', 0)}` keeps, `{control_report.get('discards', 0)}` discards, `{control_report.get('crashes', 0)}` crashes, stopped because `{control_report.get('stopped_reason', 'unknown')}`"
        )
    else:
        lines.append("- latest overnight control run: unavailable")
    lines.extend(
        [
            "",
            "## Current Frontier Settings",
            "",
        ]
    )
    for name in KEY_TRAIN_CONSTANTS:
        if name in best_train_constants:
            suffix = ""
            if current_train_constants.get(name) != best_train_constants.get(name):
                suffix = f" (current worktree: {format_constant_value(current_train_constants.get(name))})"
            lines.append(f"- `{name}` = `{format_constant_value(best_train_constants[name])}`{suffix}")

    lines.extend(["", "## What Happened", ""])
    keep_rows = [row for row in rows if row.status == "keep" and row.val_bpb is not None]
    if keep_rows:
        lines.append("### Confirmed Additive Wins")
        lines.append("")
        for row in keep_rows:
            lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description}")
        lines.append("")
    if top_results:
        lines.append("### Ranked Top Results From Latest Evaluated Band")
        lines.append("")
        for item in top_results:
            delta = float(item["val_bpb"]) - float(best.val_bpb or 0.0)
            lines.append(
                f"- `{item['commit']}` `{float(item['val_bpb']):.6f}` `{item['status']}` {item['description']} (delta to best: `{delta:+.6f}`)"
            )
        lines.append("")
    if nearest_losses:
        lines.append("### Nearest Clean Losses")
        lines.append("")
        for row in nearest_losses:
            delta = (row.val_bpb or 0.0) - float(best.val_bpb or 0.0)
            lines.append(f"- `{row.commit}` `{row.val_bpb:.6f}` {row.description} (delta to best: `{delta:+.6f}`)")
        lines.append("")
    lines.append("### Non-Informative Outcomes")
    lines.append("")
    if timeout_items:
        reason_counts = Counter(str(item.get("reason") or "timeout") for item in timeout_items)
        for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            lines.append(f"- timeout: `{count}` runs ({reason})")
    if crash_items:
        reason_counts = Counter(str(item.get("reason") or "crash") for item in crash_items)
        for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0])):
            lines.append(f"- crash: `{count}` runs ({reason})")
    if not timeout_items and not crash_items:
        lines.append("- none")

    lines.extend(["", "## Coherence Status", ""])
    lines.extend(coherence_lines)
    lines.append("")
    lines.append("## What We Know Now")
    lines.append("")
    if top_results:
        lines.append(f"- The best observed configuration remains `{best_commit_short}` / `{best.val_bpb:.6f}`.")
        lines.append(f"- The latest evaluated band produced `{len(informative_items)}` informative outcomes and `{len(timeout_items) + len(crash_items)}` non-informative outcomes.")
    else:
        lines.append(f"- The ledger frontier is `{best_commit_short}` / `{best.val_bpb:.6f}`; no latest-band detail was available beyond the ledger.")
    if handoff_frontier and "best_commit" in handoff_frontier:
        lines.append("- Narrative docs are not canonical; they can lag the ledger and control state.")
    else:
        lines.append("- Narrative docs are missing or incomplete; the ledger and control state are carrying the canonical context.")

    lines.extend(["", "## Recommended Next Steps", ""])
    lines.extend(recommendation_lines)
    lines.extend(
        [
            "",
            "## Inputs Used",
            "",
            f"- ledger: `{results_path.relative_to(target_root)}`",
            f"- control state: `{state_path.relative_to(target_root) if state_path.exists() else state_path}`",
            f"- control report: `{control_report_path.relative_to(target_root) if control_report_path.exists() else control_report_path}`",
            f"- handoff: `{handoff_path.relative_to(target_root) if handoff_path.exists() else handoff_path}`",
            f"- run notes: `{run_notes_path.relative_to(target_root) if run_notes_path.exists() else run_notes_path}`",
            f"- beta report: `{beta_report_path.relative_to(target_root) if beta_report_path.exists() else beta_report_path}`",
        ]
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"overnight_eval_{tag}.md"
    return output_path, "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a canonical overnight evaluation report.")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--target-worktree", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path, report = build_report(args)
    output_path.write_text(report)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
