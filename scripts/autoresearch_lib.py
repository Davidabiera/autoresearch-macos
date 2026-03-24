#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
import json
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_ROOT = ROOT
DEFAULT_CONTROL_ROOT = ROOT / "worktrees" / "control" / "control"
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
ALLOWED_ASSIGNMENTS = set(KEY_TRAIN_CONSTANTS) | {
    "ASPECT_RATIO",
    "HEAD_DIM",
    "WINDOW_PATTERN",
}
SUMMARY_PATTERNS = {
    "val_bpb": re.compile(r"^val_bpb:\s+([0-9.]+)$", re.MULTILINE),
    "peak_vram_mb": re.compile(r"^peak_vram_mb:\s+([0-9.]+)$", re.MULTILINE),
    "training_seconds": re.compile(r"^training_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "total_seconds": re.compile(r"^total_seconds:\s+([0-9.]+)$", re.MULTILINE),
}
RUNNER_TIMEOUT_RE = re.compile(r"RUNNER_TIMEOUT: exceeded ([0-9]+) seconds")
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
OOM_MARKERS = (
    "out of memory",
    "cuda out of memory",
    "mps backend out of memory",
    "resourceexhausted",
)
CONFIG_MARKERS = (
    "assertionerror",
    "invalid batch divisibility",
    "unsupported assignment key",
    "assignments must be a non-empty object",
    "must be divisible",
)


class AutoresearchError(RuntimeError):
    pass


@dataclass
class ResultRow:
    line_number: int
    commit: str
    description: str
    status: str
    val_bpb: float | None
    memory_gb: float | None


@dataclass
class QueueItem:
    id: str
    description: str
    assignments: dict[str, str]


def branch_tag(branch: str) -> str:
    return branch.split("/", 1)[1] if "/" in branch else branch


def artifact_paths(
    target_root: Path,
    branch: str,
    control_root: Path | None = None,
    tag: str | None = None,
) -> dict[str, Path | str]:
    resolved_control_root = (control_root or DEFAULT_CONTROL_ROOT).resolve()
    resolved_tag = tag or branch_tag(branch)
    return {
        "tag": resolved_tag,
        "results": target_root / "results.tsv",
        "handoff": target_root / f"HANDOFF_{resolved_tag}.md",
        "run_notes": target_root / f"RUN_NOTES_{resolved_tag}.md",
        "beta_report": target_root / f"BETA_REPORT_{resolved_tag}.md",
        "canonical_eval": target_root / "reports" / f"overnight_eval_{resolved_tag}.md",
        "control_root": resolved_control_root,
        "control_state": resolved_control_root / "state" / f"overnight_{resolved_tag}.json",
        "control_report": resolved_control_root / "reports" / f"overnight_{resolved_tag}.md",
        "control_queue": resolved_control_root / "queues" / f"{resolved_tag}_overnight.jsonl",
    }


def run_git(target_root: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=target_root,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AutoresearchError(
            f"git {' '.join(args)} failed in {target_root}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout.strip()


def current_branch(target_root: Path) -> str:
    return run_git(target_root, ["rev-parse", "--abbrev-ref", "HEAD"])


def current_head(target_root: Path) -> str:
    return run_git(target_root, ["rev-parse", "--short", "HEAD"])


def short_commit(target_root: Path, commit: str) -> str:
    return run_git(target_root, ["rev-parse", "--short", commit])


def maybe_short_commit(target_root: Path, commit: str | None) -> str | None:
    if not commit:
        return None
    try:
        return short_commit(target_root, commit)
    except AutoresearchError:
        return None


def resolve_branch_contains(target_root: Path, commit: str, branch: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, branch],
        cwd=target_root,
        text=True,
        capture_output=True,
    )
    return proc.returncode == 0


def git_status_lines(target_root: Path) -> list[str]:
    output = run_git(target_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    return [line for line in output.splitlines() if line.strip()]


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


def read_commit_train_constants(target_root: Path, commit: str) -> dict[str, Any]:
    source = run_git(target_root, ["show", f"{commit}:train.py"])
    return parse_python_constants_from_text(source)


def format_constant_value(value: Any) -> str:
    if isinstance(value, tuple):
        return "(" + ", ".join(format_constant_value(item) for item in value) + ")"
    return str(value)


def format_constant_map(constants: dict[str, Any]) -> dict[str, str]:
    return {name: format_constant_value(constants[name]) for name in KEY_TRAIN_CONSTANTS if name in constants}


def parse_results(results_path: Path) -> list[ResultRow]:
    if not results_path.exists():
        raise AutoresearchError(f"results file not found: {results_path}")
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
        raise AutoresearchError("results.tsv does not contain any informative results")
    return min(informative, key=lambda row: row.val_bpb)


def find_result_by_commit(rows: list[ResultRow], commit: str) -> ResultRow | None:
    for row in rows:
        if row.commit == commit:
            return row
    return None


def previous_keep(rows: list[ResultRow], line_number: int) -> ResultRow | None:
    prior_keeps = [row for row in rows if row.status == "keep" and row.val_bpb is not None and row.line_number < line_number]
    if not prior_keeps:
        return None
    return prior_keeps[-1]


def nearest_clean_losses(rows: list[ResultRow], best_val: float, limit: int = 5) -> list[ResultRow]:
    discards = [row for row in rows if row.status == "discard" and row.val_bpb is not None]
    return sorted(discards, key=lambda row: (row.val_bpb - best_val, row.val_bpb))[:limit]


def keep_rows(rows: list[ResultRow]) -> list[ResultRow]:
    return [row for row in rows if row.status == "keep" and row.val_bpb is not None]


def discard_rows(rows: list[ResultRow]) -> list[ResultRow]:
    return [row for row in rows if row.status == "discard" and row.val_bpb is not None]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def parse_handoff_frontier(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    best_commit_match = HANDOFF_FRONTIER_PATTERNS["best_commit"].search(text)
    best_val_match = HANDOFF_FRONTIER_PATTERNS["best_val"].search(text)
    if not best_commit_match or not best_val_match:
        return {"path": str(path), "status": "missing frontier summary"}
    return {
        "path": str(path),
        "best_commit": best_commit_match.group(1),
        "best_val": float(best_val_match.group(1)),
    }


def parse_control_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text()
    payload: dict[str, Any] = {"path": str(path)}
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


def parse_queue_file(path: Path) -> list[QueueItem]:
    if not path.exists():
        return []
    items: list[QueueItem] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        assignments = {str(key): str(value) for key, value in dict(data["assignments"]).items()}
        items.append(
            QueueItem(
                id=str(data["id"]),
                description=str(data["description"]),
                assignments=assignments,
            )
        )
    return items


def parse_log_metrics(text: str) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {key: None for key in SUMMARY_PATTERNS}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = pattern.search(text)
        if match:
            metrics[key] = float(match.group(1))
    return metrics


def classify_log(
    text: str,
    control_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = parse_log_metrics(text)
    timeout_match = RUNNER_TIMEOUT_RE.search(text)
    informative = metrics["val_bpb"] is not None
    status_class = "unknown-crash"
    issue_scope = "unknown"
    suggested_action = "retry"
    reason = "log did not match any known completion or failure pattern"

    if informative:
        training_seconds = metrics["training_seconds"]
        total_seconds = metrics["total_seconds"]
        has_large_overrun = (
            training_seconds is not None
            and total_seconds is not None
            and total_seconds > max(training_seconds + 120.0, training_seconds * 1.25)
        )
        if timeout_match or has_large_overrun:
            status_class = "post-train-overrun"
            issue_scope = "runner-specific"
            suggested_action = "queue-adjustment"
            if timeout_match:
                reason = f"summary fields are present, but the runner still recorded a timeout after {timeout_match.group(1)} seconds"
            else:
                reason = (
                    f"training completed in {training_seconds:.1f}s, but total runtime expanded to "
                    f"{total_seconds:.1f}s"
                )
        else:
            status_class = "completed"
            issue_scope = "experiment-specific"
            suggested_action = "retry"
            reason = "summary fields are present and no timeout markers were found"
    elif timeout_match:
        timeout_count = 0
        if control_state:
            timeout_count = sum(
                1 for item in control_state.get("completed", []) if classify_completed_item(item) == "timeout"
            )
        if timeout_count >= 3:
            issue_scope = "runner-specific"
            suggested_action = "queue-adjustment"
        else:
            issue_scope = "unknown"
            suggested_action = "retry"
        status_class = "watchdog-timeout"
        reason = f"runner timeout marker found without summary fields ({timeout_match.group(1)} second limit)"
    else:
        lowered = text.lower()
        if any(marker in lowered for marker in OOM_MARKERS):
            status_class = "resource-oom"
            issue_scope = "experiment-specific"
            suggested_action = "discard"
            reason = "log includes an out-of-memory marker"
        elif any(marker in lowered for marker in CONFIG_MARKERS):
            status_class = "config-invalid"
            issue_scope = "experiment-specific"
            suggested_action = "discard"
            reason = "log includes an assertion or invalid configuration marker"
        elif "traceback" in lowered or "exception" in lowered:
            status_class = "unknown-crash"
            issue_scope = "unknown"
            suggested_action = "retry"
            reason = "log contains a traceback or exception without a recognized root cause"

    payload = {
        "status_class": status_class,
        "informative": informative,
        "val_bpb": metrics["val_bpb"],
        "training_seconds": metrics["training_seconds"],
        "total_seconds": metrics["total_seconds"],
        "reason": reason,
        "suggested_action": suggested_action,
        "issue_scope": issue_scope,
    }
    if metrics["peak_vram_mb"] is not None:
        payload["peak_vram_mb"] = metrics["peak_vram_mb"]
        payload["memory_gb"] = round(metrics["peak_vram_mb"] / 1024.0, 1)
    if timeout_match:
        payload["runner_timeout_seconds"] = int(timeout_match.group(1))
    return payload


def existing_queue_metadata(control_state: dict[str, Any] | None, queue_path: Path | None = None) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    descriptions: set[str] = set()
    if queue_path is not None and queue_path.exists():
        for item in parse_queue_file(queue_path):
            ids.add(item.id)
            descriptions.add(item.description)
    if control_state:
        for item in control_state.get("resolved_queue", []):
            if item.get("id"):
                ids.add(str(item["id"]))
            if item.get("description"):
                descriptions.add(str(item["description"]))
        for item in control_state.get("completed", []):
            if item.get("id"):
                ids.add(str(item["id"]))
            if item.get("description"):
                descriptions.add(str(item["description"]))
    return ids, descriptions


def slugify_value(value: str) -> str:
    cleaned = value.replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", cleaned)
    return cleaned.replace(".", "")


def make_queue_item(name: str, value: str, description: str) -> QueueItem:
    prefix = name.lower()
    return QueueItem(
        id=f"{prefix}_{slugify_value(value)}",
        description=description,
        assignments={name: value},
    )


def queue_item_to_dict(item: QueueItem | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, QueueItem):
        return asdict(item)
    return {
        "id": str(item["id"]),
        "description": str(item["description"]),
        "assignments": {str(key): str(value) for key, value in dict(item["assignments"]).items()},
    }


def collect_frontier_context(
    target_root: Path,
    branch: str,
    control_root: Path | None = None,
    tag: str | None = None,
) -> dict[str, Any]:
    paths = artifact_paths(target_root.resolve(), branch, control_root=control_root, tag=tag)
    rows = parse_results(paths["results"])
    best = best_result(rows)
    best_commit_short = maybe_short_commit(target_root, best.commit) or best.commit
    repo_branch = current_branch(target_root)
    head_commit = current_head(target_root)
    head_row = find_result_by_commit(rows, head_commit)
    control_state = load_json(paths["control_state"])
    control_report = parse_control_report(paths["control_report"])
    handoff_frontier = parse_handoff_frontier(paths["handoff"])
    best_train_constants = read_commit_train_constants(target_root, best.commit)
    current_train_constants = parse_python_constants(target_root / "train.py")
    unresolved_queue: list[dict[str, Any]] = []
    if control_state:
        queue_index = int(control_state.get("queue_index", 0))
        unresolved_queue = [queue_item_to_dict(item) for item in control_state.get("resolved_queue", [])[queue_index:]]
    return {
        "paths": {key: str(value) if isinstance(value, Path) else value for key, value in paths.items()},
        "tag": str(paths["tag"]),
        "rows": rows,
        "best": best,
        "best_commit_short": best_commit_short,
        "prior_frontier": previous_keep(rows, best.line_number),
        "repo_branch": repo_branch,
        "head_commit": head_commit,
        "head_row": head_row,
        "control_state": control_state,
        "control_report": control_report,
        "handoff_frontier": handoff_frontier,
        "best_train_constants": best_train_constants,
        "current_train_constants": current_train_constants,
        "unresolved_queue": unresolved_queue,
        "nearest_losses": nearest_clean_losses(rows, best.val_bpb or 0.0),
        "git_status_lines": git_status_lines(target_root),
    }


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


def coherence_flags(context: dict[str, Any], target_root: Path, branch: str) -> list[dict[str, str]]:
    best = context["best"]
    best_commit_short = context["best_commit_short"]
    flags: list[dict[str, str]] = []

    if context["repo_branch"] != branch:
        flags.append(
            {
                "severity": "error",
                "artifact": "branch",
                "message": f"current branch is `{context['repo_branch']}` but expected `{branch}`",
            }
        )
    if context["head_commit"] != best_commit_short:
        flags.append(
            {
                "severity": "error",
                "artifact": "HEAD",
                "message": f"HEAD `{context['head_commit']}` does not match canonical best `{best_commit_short}`",
            }
        )
    if not resolve_branch_contains(target_root, best.commit, branch):
        flags.append(
            {
                "severity": "error",
                "artifact": "branch-history",
                "message": f"canonical best `{best.commit}` is not clearly contained in `{branch}`",
            }
        )

    drift_keys = [
        name
        for name in KEY_TRAIN_CONSTANTS
        if context["current_train_constants"].get(name) != context["best_train_constants"].get(name)
    ]
    if drift_keys:
        joined = ", ".join(drift_keys)
        flags.append(
            {
                "severity": "error",
                "artifact": "train.py",
                "message": f"current worktree constants drift from the frontier on: {joined}",
            }
        )

    control_state = context["control_state"]
    if control_state:
        state_commit = maybe_short_commit(target_root, str(control_state.get("current_best_commit") or ""))
        state_val = control_state.get("current_best_val")
        if state_commit != best_commit_short or state_val is None or abs(float(state_val) - (best.val_bpb or 0.0)) > 1e-9:
            flags.append(
                {
                    "severity": "warning",
                    "artifact": "control-state",
                    "message": f"control state frontier is stale relative to ledger (`{state_commit}` / `{state_val}`)",
                }
            )
    else:
        flags.append(
            {
                "severity": "warning",
                "artifact": "control-state",
                "message": "control state is missing",
            }
        )

    control_report = context["control_report"]
    if control_report:
        report_commit = maybe_short_commit(target_root, str(control_report.get("end_best_commit") or ""))
        report_val = control_report.get("end_best_val")
        if report_commit != best_commit_short or report_val is None or abs(float(report_val) - (best.val_bpb or 0.0)) > 1e-9:
            flags.append(
                {
                    "severity": "warning",
                    "artifact": "control-report",
                    "message": f"control report frontier is stale relative to ledger (`{report_commit}` / `{report_val}`)",
                }
            )
    else:
        flags.append(
            {
                "severity": "warning",
                "artifact": "control-report",
                "message": "control report is missing",
            }
        )

    handoff_frontier = context["handoff_frontier"]
    if handoff_frontier and "best_commit" in handoff_frontier:
        handoff_commit = maybe_short_commit(target_root, handoff_frontier["best_commit"])
        handoff_val = handoff_frontier["best_val"]
        if handoff_commit != best_commit_short or abs(float(handoff_val) - (best.val_bpb or 0.0)) > 1e-9:
            flags.append(
                {
                    "severity": "warning",
                    "artifact": "handoff",
                    "message": f"handoff frontier is stale (`{handoff_commit}` / `{handoff_val:.6f}`)",
                }
            )
    else:
        flags.append(
            {
                "severity": "warning",
                "artifact": "handoff",
                "message": "handoff file is missing or does not expose a frontier summary",
            }
        )

    if context["git_status_lines"]:
        flags.append(
            {
                "severity": "warning",
                "artifact": "git-status",
                "message": f"worktree is not clean ({len(context['git_status_lines'])} pending entries)",
            }
        )

    remaining = context["unresolved_queue"]
    seen_descriptions: set[str] = set()
    for item in remaining:
        assignments = item.get("assignments", {})
        if len(assignments) != 1:
            flags.append(
                {
                    "severity": "error",
                    "artifact": "queue",
                    "message": f"queue item `{item.get('id')}` is not a single-variable experiment",
                }
            )
        description = str(item.get("description") or "")
        if description in seen_descriptions:
            flags.append(
                {
                    "severity": "error",
                    "artifact": "queue",
                    "message": f"remaining queue contains a duplicate description: `{description}`",
                }
            )
        seen_descriptions.add(description)
    return flags


def count_non_informative(control_state: dict[str, Any] | None) -> dict[str, int]:
    completed = list(control_state.get("completed", [])) if control_state else []
    counts = Counter(classify_completed_item(item) for item in completed)
    return {
        "informative": counts.get("informative", 0),
        "timeout": counts.get("timeout", 0),
        "crash": counts.get("crash", 0),
    }
