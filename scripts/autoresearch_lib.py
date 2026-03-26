#!/usr/bin/env python3
from __future__ import annotations

import ast
import csv
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_ROOT = Path(os.environ.get("AUTORESEARCH_TARGET_ROOT", str(ROOT))).resolve()
DEFAULT_CONTROL_ROOT = Path(
    os.environ.get("AUTORESEARCH_CONTROL_ROOT", str(DEFAULT_TARGET_ROOT / "worktrees" / "control" / "control"))
).resolve()
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
    "startup_seconds": re.compile(r"^startup_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "warmup_seconds": re.compile(r"^warmup_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "training_seconds": re.compile(r"^training_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "eval_seconds": re.compile(r"^eval_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "total_seconds": re.compile(r"^total_seconds:\s+([0-9.]+)$", re.MULTILINE),
    "num_steps": re.compile(r"^num_steps:\s+([0-9]+)$", re.MULTILINE),
}
RESULT_FLOAT_FIELDS = (
    "val_bpb",
    "memory_gb",
    "startup_seconds",
    "warmup_seconds",
    "training_seconds",
    "eval_seconds",
    "total_seconds",
)
RUNNER_TIMEOUT_RE = re.compile(r"RUNNER_TIMEOUT: exceeded ([0-9]+) seconds")
RUNNER_ABORT_RE = re.compile(r"RUNNER_ABORT:\s+(.+)")
STEP_PROGRESS_RE = re.compile(
    r"step\s+(\d{5}).*?dt:\s+([0-9]+)ms.*?remaining:\s*([0-9]+)s"
)
STARTUP_MARKERS = (
    "Environment verified:",
    "Vocab size:",
    "Model config:",
    "Time budget:",
    "Gradient accumulation steps:",
)
EARLY_STALL_MS = 30_000
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
STALL_FAILURE_CLASSES = {"startup-hang", "early-step-stall", "late-timeout", "watchdog-timeout", "runner-abort"}
REPEATABILITY_SPREAD_THRESHOLD = 0.0010
MATERIAL_WIN_THRESHOLD = 0.0010
FRONTIER_ANCHOR_DRIFT_THRESHOLD = 0.0010
MIN_CLEAN_NUM_STEPS = 300
RESEARCH_PROCESS_MARKERS = ("train.py", "overnight_runner.py", "session_orchestrator.py", "uv run train.py")


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
    default_plan = default_plan_path(resolved_control_root, resolved_tag)
    return {
        "tag": resolved_tag,
        "results": target_root / "results.tsv",
        "results_snapshot": resolved_control_root / "state" / f"results_{resolved_tag}.tsv",
        "handoff": target_root / f"HANDOFF_{resolved_tag}.md",
        "run_notes": target_root / f"RUN_NOTES_{resolved_tag}.md",
        "beta_report": target_root / f"BETA_REPORT_{resolved_tag}.md",
        "canonical_eval": target_root / "reports" / f"overnight_eval_{resolved_tag}.md",
        "control_root": resolved_control_root,
        "control_state": resolved_control_root / "state" / f"overnight_{resolved_tag}.json",
        "gated_results": resolved_control_root / "state" / f"gated_results_{resolved_tag}.jsonl",
        "repeatability_results": resolved_control_root / "state" / f"repeatability_{resolved_tag}.jsonl",
        "noncanonical_signals": resolved_control_root / "state" / f"noncanonical_signals_{resolved_tag}.jsonl",
        "active_run": resolved_control_root / "state" / f"active_run_{resolved_tag}.json",
        "orchestrator_state": resolved_control_root / "state" / f"orchestrator_{resolved_tag}.json",
        "control_report": resolved_control_root / "reports" / f"overnight_{resolved_tag}.md",
        "control_queue": resolved_control_root / "queues" / f"{resolved_tag}_overnight.jsonl",
        "default_plan": default_plan,
        "runtime_forensics_root": runtime_forensics_root(resolved_control_root, resolved_tag),
    }


def result_ledger_path(control_root: Path, tag: str, session_kind: str) -> Path:
    if session_kind == "repeatability":
        name = "repeatability"
    elif session_kind == "noncanonical":
        name = "noncanonical_signals"
    else:
        name = "gated_results"
    return control_root / "state" / f"{name}_{tag}.jsonl"


def active_run_path(control_root: Path, tag: str) -> Path:
    return control_root / "state" / f"active_run_{tag}.json"


def orchestrator_state_path(control_root: Path, tag: str) -> Path:
    return control_root / "state" / f"orchestrator_{tag}.json"


def default_plan_path(control_root: Path, tag: str) -> Path:
    plans_root = control_root / "plans"
    preferred = plans_root / f"{tag}_backend_isolation_then_repeatability.json"
    if preferred.exists():
        return preferred
    return plans_root / f"{tag}_stability_then_next_axis.json"


def runtime_forensics_root(control_root: Path, tag: str) -> Path:
    return control_root / "state" / "runtime_forensics"


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


def resolve_results_source(primary_path: Path, snapshot_path: Path) -> tuple[Path, list[ResultRow]]:
    candidates: list[Path] = []
    if primary_path.exists():
        candidates.append(primary_path)
    if snapshot_path.exists() and snapshot_path not in candidates:
        candidates.append(snapshot_path)
    if not candidates:
        raise AutoresearchError(f"results file not found: {primary_path} or {snapshot_path}")

    first_error: AutoresearchError | None = None
    for path in candidates:
        try:
            rows = parse_results(path)
            best_result(rows)
            return path, rows
        except AutoresearchError as exc:
            if first_error is None:
                first_error = exc
            continue
    assert first_error is not None
    raise first_error


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


def parse_queue_file(path: Path) -> list[QueueItem]:
    if not path.exists():
        return []
    items: list[QueueItem] = []
    for line in path.read_text().splitlines():
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


def _maybe_float(value: Any) -> float | None:
    if value in {None, "", "NA"}:
        return None
    return float(value)


def parse_result_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text().splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        payload = {
            "id": str(data.get("id") or ""),
            "description": str(data.get("description") or ""),
            "commit": str(data.get("commit") or ""),
            "status": str(data.get("status") or ""),
            "status_class": str(data.get("status_class") or ""),
            "session_kind": str(data.get("session_kind") or ""),
            "issue_scope": str(data.get("issue_scope") or ""),
            "reason": data.get("reason"),
            "log_path": data.get("log_path"),
            "source_branch": data.get("source_branch"),
            "informative": bool(data.get("informative"))
            or data.get("val_bpb") not in {None, "", "NA"}
            or str(data.get("status") or "") in {"keep", "discard"},
            "suppress_planner": data.get("suppress_planner"),
        }
        for key in RESULT_FLOAT_FIELDS:
            payload[key] = _maybe_float(data.get(key))
        if data.get("num_steps") is not None:
            payload["num_steps"] = int(data["num_steps"])
        if data.get("runner_timeout_seconds") is not None:
            payload["runner_timeout_seconds"] = int(data["runner_timeout_seconds"])
        rows.append(payload)
    return rows


def parse_gated_results(path: Path) -> list[dict[str, Any]]:
    return parse_result_ledger(path)


def parse_repeatability_results(path: Path) -> list[dict[str, Any]]:
    return parse_result_ledger(path)


def parse_noncanonical_signals(path: Path) -> list[dict[str, Any]]:
    return parse_result_ledger(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def gated_result_is_final(item: dict[str, Any]) -> bool:
    if item.get("suppress_planner") is not None:
        return bool(item["suppress_planner"])
    if bool(item.get("informative")):
        return True
    return str(item.get("status_class") or "") in {"config-invalid", "resource-oom"}


def gated_result_metadata(gated_results: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    descriptions: set[str] = set()
    for item in gated_results:
        if not gated_result_is_final(item):
            continue
        if item.get("id"):
            ids.add(str(item["id"]))
        if item.get("description"):
            descriptions.add(str(item["description"]))
    return ids, descriptions


def filter_queue_items(
    queue_items: list[dict[str, Any]],
    blocked_ids: set[str],
    blocked_descriptions: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in queue_items:
        item_id = str(item.get("id") or "")
        description = str(item.get("description") or "")
        if item_id in blocked_ids or description in blocked_descriptions:
            continue
        filtered.append(queue_item_to_dict(item))
    return filtered


def parse_log_metrics(text: str) -> dict[str, float | None]:
    metrics: dict[str, float | None] = {key: None for key in SUMMARY_PATTERNS}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = pattern.search(text)
        if match:
            metrics[key] = float(match.group(1))
    return metrics


def parse_step_progress(text: str) -> list[dict[str, int]]:
    progress: list[dict[str, int]] = []
    for step, dt_ms, remaining in STEP_PROGRESS_RE.findall(text):
        progress.append(
            {
                "step": int(step),
                "dt_ms": int(dt_ms),
                "remaining_seconds": int(remaining),
            }
        )
    return progress


def process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_cwd(pid: int) -> str | None:
    try:
        proc = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True,
            capture_output=True,
        )
    except PermissionError:
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def live_research_processes() -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid,ppid,command"],
            text=True,
            capture_output=True,
        )
    except PermissionError:
        return []
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        if "operation not permitted" in detail.lower():
            return []
        raise AutoresearchError(f"ps failed: {detail}")
    items: list[dict[str, Any]] = []
    for raw_line in proc.stdout.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid = int(parts[0])
        ppid = int(parts[1])
        command = parts[2]
        if not any(marker in command for marker in RESEARCH_PROCESS_MARKERS):
            continue
        if "rg " in command and "train.py" in command:
            continue
        items.append(
            {
                "pid": pid,
                "ppid": ppid,
                "command": command,
                "cwd": process_cwd(pid),
            }
        )
    return items


def foreign_research_processes(execution_root: Path, allowed_pids: set[int] | None = None) -> list[dict[str, Any]]:
    allowed = allowed_pids or set()
    resolved_root = execution_root.resolve()
    blockers: list[dict[str, Any]] = []
    for item in live_research_processes():
        if int(item["pid"]) in allowed:
            continue
        cwd = item.get("cwd")
        if cwd and Path(cwd).resolve() == resolved_root:
            continue
        blockers.append(item)
    return blockers


def classify_log(
    text: str,
    control_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = parse_log_metrics(text)
    step_progress = parse_step_progress(text)
    timeout_match = RUNNER_TIMEOUT_RE.search(text)
    abort_match = RUNNER_ABORT_RE.search(text)
    informative = metrics["val_bpb"] is not None
    status_class = "unknown-crash"
    issue_scope = "unknown"
    suggested_action = "retry"
    reason = "log did not match any known completion or failure pattern"

    if informative:
        startup_seconds = metrics["startup_seconds"]
        warmup_seconds = metrics["warmup_seconds"]
        training_seconds = metrics["training_seconds"]
        eval_seconds = metrics["eval_seconds"]
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
                phase_bits: list[str] = []
                if startup_seconds is not None:
                    phase_bits.append(f"startup {startup_seconds:.1f}s")
                if warmup_seconds is not None:
                    phase_bits.append(f"warmup {warmup_seconds:.1f}s")
                if eval_seconds is not None:
                    phase_bits.append(f"eval {eval_seconds:.1f}s")
                detail = f" ({', '.join(phase_bits)})" if phase_bits else ""
                reason = f"training completed in {training_seconds:.1f}s, but total runtime expanded to {total_seconds:.1f}s{detail}"
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
        repeated_timeout = timeout_count >= 3
        if step_progress:
            last = step_progress[-1]
            max_dt_ms = max(item["dt_ms"] for item in step_progress)
            if last["remaining_seconds"] <= 1:
                status_class = "late-timeout"
                issue_scope = "runner-specific"
                suggested_action = "queue-adjustment"
                reason = (
                    f"runner timeout fired after the training budget was exhausted; "
                    f"last observed step {last['step']} ended with remaining={last['remaining_seconds']}s"
                )
            elif last["step"] <= 5 and max_dt_ms >= EARLY_STALL_MS:
                status_class = "early-step-stall"
                issue_scope = "runner-specific" if repeated_timeout else "unknown"
                suggested_action = "queue-adjustment" if repeated_timeout else "retry"
                reason = (
                    f"runner timeout followed an early training stall; "
                    f"max observed step time was {max_dt_ms / 1000.0:.1f}s by step {last['step']}"
                )
            else:
                status_class = "watchdog-timeout"
                issue_scope = "runner-specific" if repeated_timeout else "unknown"
                suggested_action = "queue-adjustment" if repeated_timeout else "retry"
                reason = (
                    f"runner timeout marker found without summary fields ({timeout_match.group(1)} second limit); "
                    f"last observed step {last['step']} still had remaining={last['remaining_seconds']}s"
                )
        else:
            if any(marker in text for marker in STARTUP_MARKERS):
                status_class = "startup-hang"
                reason = "runner timeout fired after startup output appeared, but the training loop never logged a step"
            else:
                status_class = "startup-hang"
                reason = "runner timeout fired before the training loop produced any observable progress"
            issue_scope = "runner-specific" if repeated_timeout else "unknown"
            suggested_action = "queue-adjustment" if repeated_timeout else "retry"
    elif abort_match:
        lowered_reason = abort_match.group(1).lower()
        if step_progress and any(item["step"] <= 20 and item["dt_ms"] >= EARLY_STALL_MS for item in step_progress):
            status_class = "early-step-stall"
            issue_scope = "runner-specific"
            suggested_action = "queue-adjustment"
            reason = f"runner aborted after early-step stall threshold: {abort_match.group(1)}"
        else:
            status_class = "runner-abort"
            issue_scope = "runner-specific"
            suggested_action = "queue-adjustment"
            reason = f"runner aborted: {abort_match.group(1)}"
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

    payload: dict[str, Any] = {
        "status_class": status_class,
        "informative": informative,
        "val_bpb": metrics["val_bpb"],
        "training_seconds": metrics["training_seconds"],
        "total_seconds": metrics["total_seconds"],
        "reason": reason,
        "suggested_action": suggested_action,
        "issue_scope": issue_scope,
    }
    if metrics["num_steps"] is not None:
        payload["num_steps"] = int(metrics["num_steps"])
    for key in ("startup_seconds", "warmup_seconds", "eval_seconds"):
        if metrics[key] is not None:
            payload[key] = metrics[key]
    if step_progress:
        payload["step_count"] = len(step_progress)
        if payload.get("num_steps") is None:
            payload["num_steps"] = len(step_progress)
        payload["last_step"] = step_progress[-1]["step"]
        payload["last_step_dt_ms"] = step_progress[-1]["dt_ms"]
        payload["last_remaining_seconds"] = step_progress[-1]["remaining_seconds"]
        payload["max_step_dt_ms"] = max(item["dt_ms"] for item in step_progress)
    if metrics["peak_vram_mb"] is not None:
        payload["peak_vram_mb"] = metrics["peak_vram_mb"]
        payload["memory_gb"] = round(metrics["peak_vram_mb"] / 1024.0, 1)
    if timeout_match:
        payload["runner_timeout_seconds"] = int(timeout_match.group(1))
    if abort_match:
        payload["runner_abort_reason"] = abort_match.group(1)
    return payload


def existing_queue_metadata(
    control_state: dict[str, Any] | None,
    queue_path: Path | None = None,
    gated_results: list[dict[str, Any]] | None = None,
) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    descriptions: set[str] = set()
    if queue_path is not None and queue_path.exists():
        for item in parse_queue_file(queue_path):
            ids.add(item.id)
            descriptions.add(item.description)
    if gated_results:
        gated_ids, gated_descriptions = gated_result_metadata(gated_results)
        ids.update(gated_ids)
        descriptions.update(gated_descriptions)
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
    repo_branch = current_branch(target_root)
    if repo_branch != branch and Path(paths["results_snapshot"]).exists():
        results_path, rows = resolve_results_source(Path(paths["results_snapshot"]), Path(paths["results"]))
    else:
        results_path, rows = resolve_results_source(Path(paths["results"]), Path(paths["results_snapshot"]))
    best = best_result(rows)
    best_commit_short = maybe_short_commit(target_root, best.commit) or best.commit
    head_commit = current_head(target_root)
    head_row = find_result_by_commit(rows, head_commit)
    control_state = load_json(paths["control_state"])
    control_report = parse_control_report(paths["control_report"])
    handoff_frontier = parse_handoff_frontier(paths["handoff"])
    gated_results = parse_gated_results(paths["gated_results"])
    repeatability_results = parse_repeatability_results(paths["repeatability_results"])
    noncanonical_signals = parse_noncanonical_signals(paths["noncanonical_signals"])
    gated_ids, gated_descriptions = gated_result_metadata(gated_results)
    best_train_constants = read_commit_train_constants(target_root, best.commit)
    current_train_constants = parse_python_constants(target_root / "train.py")
    unresolved_queue: list[dict[str, Any]] = []
    if control_state:
        queue_index = int(control_state.get("queue_index", 0))
        unresolved_queue = [queue_item_to_dict(item) for item in control_state.get("resolved_queue", [])[queue_index:]]
    fresh_unresolved_queue = filter_queue_items(unresolved_queue, gated_ids, gated_descriptions)
    return {
        "paths": {key: str(value) if isinstance(value, Path) else value for key, value in paths.items()},
        "results_path": str(results_path),
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
        "gated_results": gated_results,
        "repeatability_results": repeatability_results,
        "noncanonical_signals": noncanonical_signals,
        "gated_suppressed_ids": gated_ids,
        "gated_suppressed_descriptions": gated_descriptions,
        "best_train_constants": best_train_constants,
        "current_train_constants": current_train_constants,
        "unresolved_queue": unresolved_queue,
        "fresh_unresolved_queue": fresh_unresolved_queue,
        "nearest_losses": nearest_clean_losses(rows, best.val_bpb or 0.0),
        "git_status_lines": git_status_lines(target_root),
    }


def control_frontier_is_current(context: dict[str, Any], target_root: Path) -> bool:
    best_commit_short = context["best_commit_short"]
    best_val = context["best"].val_bpb or 0.0
    control_state = context["control_state"]
    control_report = context["control_report"]
    if not control_state or not control_report:
        return False
    state_commit = maybe_short_commit(target_root, str(control_state.get("current_best_commit") or ""))
    report_commit = maybe_short_commit(target_root, str(control_report.get("end_best_commit") or ""))
    state_val = control_state.get("current_best_val")
    report_val = control_report.get("end_best_val")
    if state_commit != best_commit_short or report_commit != best_commit_short:
        return False
    if state_val is None or report_val is None:
        return False
    return abs(float(state_val) - best_val) < 1e-9 and abs(float(report_val) - best_val) < 1e-9


def missing_handoff_is_non_blocking(context: dict[str, Any], target_root: Path) -> bool:
    results_path = Path(str(context["results_path"]))
    using_snapshot = results_path.name.startswith("results_")
    return using_snapshot and control_frontier_is_current(context, target_root)


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
    elif not missing_handoff_is_non_blocking(context, target_root):
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

    remaining = context["fresh_unresolved_queue"]
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


def axis_from_item_id(item_id: str) -> str:
    lowered = item_id.lower()
    prefixes = sorted((name.lower() for name in ALLOWED_ASSIGNMENTS), key=len, reverse=True)
    for prefix in prefixes:
        marker = prefix + "_"
        if lowered.startswith(marker):
            return prefix
    return lowered.split("_", 1)[0]


def best_nonkeep_by_axis(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best_by_axis: dict[str, dict[str, Any]] = {}
    for item in rows:
        if item.get("status") != "discard" or item.get("val_bpb") is None:
            continue
        axis = axis_from_item_id(str(item.get("id") or ""))
        current = best_by_axis.get(axis)
        if current is None or float(item["val_bpb"]) < float(current["val_bpb"]):
            best_by_axis[axis] = item
    return best_by_axis


def count_non_informative(control_state: dict[str, Any] | None) -> dict[str, int]:
    completed = list(control_state.get("completed", [])) if control_state else []
    counts = Counter(classify_completed_item(item) for item in completed)
    return {
        "informative": counts.get("informative", 0),
        "timeout": counts.get("timeout", 0),
        "crash": counts.get("crash", 0),
    }


def repeatability_failure_reason(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        status_class = str(item.get("status_class") or "")
        if status_class in STALL_FAILURE_CLASSES:
            return f"repeatability session recorded `{status_class}` on `{item.get('id')}`"
        num_steps = item.get("num_steps")
        if num_steps is not None and int(num_steps) < MIN_CLEAN_NUM_STEPS:
            return (
                f"repeatability session produced a truncated run on `{item.get('id')}` "
                f"with only {int(num_steps)} steps"
            )
    return None


def evaluate_repeatability_gate(
    items: list[dict[str, Any]],
    frontier_anchor_val: float | None = None,
) -> dict[str, Any]:
    failure = repeatability_failure_reason(items)
    frontier_repeats = [item for item in items if str(item.get("id") or "").startswith("frontier_repeat")]
    weight_decay_repeats = [item for item in items if str(item.get("id") or "").startswith("weight_decay_repeat_022")]
    frontier_vals = [float(item["val_bpb"]) for item in frontier_repeats if item.get("val_bpb") is not None]
    weight_decay_vals = [float(item["val_bpb"]) for item in weight_decay_repeats if item.get("val_bpb") is not None]
    frontier_mean = sum(frontier_vals) / len(frontier_vals) if frontier_vals else None
    weight_decay_mean = sum(weight_decay_vals) / len(weight_decay_vals) if weight_decay_vals else None
    frontier_spread = max(frontier_vals) - min(frontier_vals) if len(frontier_vals) >= 2 else None
    weight_decay_spread = max(weight_decay_vals) - min(weight_decay_vals) if len(weight_decay_vals) >= 2 else None
    frontier_anchor_delta = (
        frontier_mean - frontier_anchor_val
        if frontier_mean is not None and frontier_anchor_val is not None
        else None
    )

    result: dict[str, Any] = {
        "passed": False,
        "failure_reason": failure,
        "frontier_count": len(frontier_vals),
        "weight_decay_count": len(weight_decay_vals),
        "frontier_mean": frontier_mean,
        "weight_decay_mean": weight_decay_mean,
        "frontier_spread": frontier_spread,
        "weight_decay_spread": weight_decay_spread,
        "frontier_anchor_val": frontier_anchor_val,
        "frontier_anchor_delta": frontier_anchor_delta,
        "material_winner": None,
        "next_stage": None,
    }
    if failure:
        result["reason"] = failure
        return result
    if frontier_spread is not None and frontier_spread > REPEATABILITY_SPREAD_THRESHOLD:
        result["reason"] = f"frontier repeatability spread is {frontier_spread:.6f}"
        return result
    if len(frontier_vals) < 2 or len(weight_decay_vals) < 2:
        result["reason"] = "repeatability session does not yet have enough completed results"
        return result
    if frontier_anchor_delta is not None and frontier_anchor_delta > FRONTIER_ANCHOR_DRIFT_THRESHOLD:
        result["reason"] = (
            f"frontier repeat mean is {frontier_mean:.6f}, which is {frontier_anchor_delta:.6f} "
            f"worse than the canonical anchor {frontier_anchor_val:.6f}"
        )
        return result

    result["passed"] = True
    if weight_decay_mean is not None and frontier_mean is not None and weight_decay_mean < frontier_mean - MATERIAL_WIN_THRESHOLD:
        result["material_winner"] = "weight_decay"
        result["next_stage"] = "weight_decay_confirmation"
        result["reason"] = "environment is stable and weight decay materially wins"
    else:
        result["next_stage"] = "scalar_first_canary"
        result["reason"] = "environment is stable and weight decay does not materially win"
    return result


def evaluate_frontier_isolation_gate(
    items: list[dict[str, Any]],
    frontier_anchor_val: float | None = None,
) -> dict[str, Any]:
    failure = repeatability_failure_reason(items)
    frontier_repeats = [item for item in items if str(item.get("id") or "").startswith("frontier_repeat")]
    frontier_vals = [float(item["val_bpb"]) for item in frontier_repeats if item.get("val_bpb") is not None]
    frontier_mean = sum(frontier_vals) / len(frontier_vals) if frontier_vals else None
    frontier_spread = max(frontier_vals) - min(frontier_vals) if len(frontier_vals) >= 2 else None
    frontier_anchor_delta = (
        frontier_mean - frontier_anchor_val
        if frontier_mean is not None and frontier_anchor_val is not None
        else None
    )
    result: dict[str, Any] = {
        "passed": False,
        "failure_reason": failure,
        "frontier_count": len(frontier_vals),
        "frontier_mean": frontier_mean,
        "frontier_spread": frontier_spread,
        "frontier_anchor_val": frontier_anchor_val,
        "frontier_anchor_delta": frontier_anchor_delta,
        "reason": None,
    }
    if failure:
        result["reason"] = failure
        return result
    if len(frontier_vals) < 2:
        result["reason"] = "frontier isolation session does not yet have two completed baseline repeats"
        return result
    if frontier_spread is not None and frontier_spread > REPEATABILITY_SPREAD_THRESHOLD:
        result["reason"] = f"frontier isolation spread is {frontier_spread:.6f}"
        return result
    if frontier_anchor_delta is not None and frontier_anchor_delta > FRONTIER_ANCHOR_DRIFT_THRESHOLD:
        result["reason"] = (
            f"frontier isolation mean is {frontier_mean:.6f}, which is {frontier_anchor_delta:.6f} "
            f"worse than the canonical anchor {frontier_anchor_val:.6f}"
        )
        return result
    result["passed"] = True
    result["reason"] = "frontier isolation passed; baseline repeats are clean and close to the canonical anchor"
    return result
