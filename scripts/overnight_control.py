#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTROL_ROOT = ROOT / "control"
STATE_VERSION = 2
LOCK_FILENAME = ".codex-overnight.lock"
SUMMARY_PATTERNS = {
    "val_bpb": re.compile(r"^val_bpb:\s+([0-9.]+)$", re.MULTILINE),
    "peak_vram_mb": re.compile(r"^peak_vram_mb:\s+([0-9.]+)$", re.MULTILINE),
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ALLOWED_ASSIGNMENTS = {
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
    "ASPECT_RATIO",
    "HEAD_DIM",
    "WINDOW_PATTERN",
}
TARGET_ALLOWED_UNTRACKED = {
    "results.tsv",
    "run.log",
    "RUN_NOTES_mar10.md",
    "HANDOFF_mar10.md",
    "BETA_REPORT_mar10.md",
}
TARGET_ALLOWED_PREFIXES = (
    "logs/",
    "state/",
    "reports/",
    "scripts/",
    "queues/",
)
PHASES = {
    "idle",
    "preparing_experiment",
    "training",
    "evaluating",
    "reconciling",
    "finished",
}
ACTIVE_PROCESS: subprocess.Popen[str] | None = None
STOP_REQUESTED = False


class RunnerError(RuntimeError):
    pass


@dataclass
class Experiment:
    id: str
    description: str
    assignments: dict[str, str]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise RunnerError(f"failed to parse JSON {path}: {exc}") from exc


def run_cmd(
    args: list[str],
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise RunnerError(
            f"command failed in {cwd}: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def format_float(value: float) -> str:
    return f"{value:.6f}"


def branch_tag(branch: str) -> str:
    return branch.split("/", 1)[1] if "/" in branch else branch


def control_paths(control_root: Path, branch: str) -> dict[str, Path]:
    tag = branch_tag(branch)
    runtime_root = control_root
    return {
        "tag": Path(tag),
        "state_path": runtime_root / "state" / f"overnight_{tag}.json",
        "pid_path": runtime_root / "state" / f"overnight_{tag}.pid",
        "report_path": runtime_root / "reports" / f"overnight_{tag}.md",
        "supervisor_log_path": runtime_root / "supervisor" / f"overnight_{tag}.log",
        "log_dir": runtime_root / "logs" / tag,
    }


def target_path(target_root: Path, relative: str) -> Path:
    return target_root / relative


def current_target_branch(target_root: Path) -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_root).stdout.strip()


def current_target_head(target_root: Path) -> str:
    return run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=target_root).stdout.strip()


def git_reset_hard(target_root: Path, commit: str) -> None:
    run_cmd(["git", "reset", "--hard", commit], cwd=target_root)


def ensure_target_commit_exists(target_root: Path, commit: str) -> None:
    run_cmd(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=target_root)


def ensure_target_git_state(target_root: Path) -> None:
    status = run_cmd(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=target_root,
    ).stdout.splitlines()
    disallowed: list[str] = []
    for line in status:
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if code == "??" and path in TARGET_ALLOWED_UNTRACKED:
            continue
        if code == "??" and any(path.startswith(prefix) for prefix in TARGET_ALLOWED_PREFIXES):
            continue
        if code == "??" and path == LOCK_FILENAME:
            continue
        disallowed.append(line)
    if disallowed:
        raise RunnerError(
            "target worktree must be clean except known artifacts; found:\n" + "\n".join(disallowed)
        )


def ensure_target_invariants(state: dict[str, Any]) -> None:
    target_root = Path(state["target_worktree"])
    branch = current_target_branch(target_root)
    if branch != state["branch"]:
        raise RunnerError(f"expected target branch {state['branch']}, found {branch}")
    ensure_target_git_state(target_root)
    for relpath in ("train.py", "prepare.py"):
        if not target_path(target_root, relpath).exists():
            raise RunnerError(f"required file missing from target worktree: {relpath}")
    ensure_target_commit_exists(target_root, state["current_best_commit"])


def parse_python_constants(path: Path) -> dict[str, Any]:
    module = ast.parse(path.read_text())
    values: dict[str, Any] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            try:
                expr = ast.Expression(node.value)
                values[name] = eval(compile(expr, str(path), "eval"), {"__builtins__": {}}, {})
            except Exception:
                continue
    return values


def parse_results_descriptions(results_path: Path) -> set[str]:
    descriptions: set[str] = set()
    if not results_path.exists():
        return descriptions
    with results_path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            description = (row.get("description") or "").strip()
            if description:
                descriptions.add(description)
    return descriptions


def ensure_results_file(results_path: Path) -> None:
    if results_path.exists():
        return
    atomic_write_text(results_path, "commit\tval_bpb\tmemory_gb\tstatus\tdescription\n")


def append_results_row(results_path: Path, commit: str, val_bpb: str, memory_gb: str, status: str, description: str) -> None:
    ensure_results_file(results_path)
    with results_path.open("a") as handle:
        handle.write(f"{commit}\t{val_bpb}\t{memory_gb}\t{status}\t{description}\n")


def rewrite_train_constants(train_path: Path, assignments: dict[str, str]) -> bool:
    original = train_path.read_text()
    lines = original.splitlines()
    changed = False
    for index, line in enumerate(lines):
        for name, value in assignments.items():
            if not re.match(rf"^{re.escape(name)}\s*=", line):
                continue
            comment = ""
            if "#" in line:
                rhs, comment_text = line.split("#", 1)
                comment = "#" + comment_text
            else:
                rhs = line
            prefix = rhs.split("=")[0].rstrip()
            new_line = f"{prefix} = {value}"
            if comment:
                new_line += " " + comment.strip()
            if new_line != line:
                lines[index] = new_line
                changed = True
            break
    rewritten = "\n".join(lines) + "\n"
    train_path.write_text(rewritten)
    return changed and rewritten != original


def validate_runtime_divisibility(train_constants: dict[str, Any], prepare_constants: dict[str, Any]) -> tuple[bool, str | None]:
    total_batch_size = int(train_constants["TOTAL_BATCH_SIZE"])
    device_batch_size = int(train_constants["DEVICE_BATCH_SIZE"])
    max_seq_len = int(prepare_constants["MAX_SEQ_LEN"])
    tokens_per_fwdbwd = device_batch_size * max_seq_len
    if total_batch_size % tokens_per_fwdbwd != 0:
        return False, (
            f"invalid batch divisibility: {total_batch_size} % "
            f"({device_batch_size} * {max_seq_len}) != 0"
        )
    return True, None


def parse_summary_from_log(log_path: Path) -> tuple[float, float]:
    text = log_path.read_text()
    extracted: dict[str, float] = {}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            raise RunnerError(f"missing summary field '{key}' in {log_path}")
        extracted[key] = float(match.group(1))
    return extracted["val_bpb"], extracted["peak_vram_mb"] / 1024.0


def load_queue_file(queue_path: Path) -> list[Experiment]:
    queue: list[Experiment] = []
    seen_ids: set[str] = set()
    with queue_path.open() as handle:
        for lineno, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunnerError(f"invalid JSON on line {lineno} of {queue_path}: {exc}") from exc
            for field in ("id", "description", "assignments"):
                if field not in payload:
                    raise RunnerError(f"missing '{field}' on line {lineno} of {queue_path}")
            experiment_id = payload["id"]
            if not isinstance(experiment_id, str) or not SAFE_ID_RE.match(experiment_id):
                raise RunnerError(f"invalid id on line {lineno} of {queue_path}: {experiment_id!r}")
            if experiment_id in seen_ids:
                raise RunnerError(f"duplicate experiment id in {queue_path}: {experiment_id}")
            seen_ids.add(experiment_id)
            description = payload["description"]
            if not isinstance(description, str) or not description.strip():
                raise RunnerError(f"invalid description on line {lineno} of {queue_path}")
            assignments = payload["assignments"]
            if not isinstance(assignments, dict) or len(assignments) != 1:
                raise RunnerError(f"queue items must be single-variable on line {lineno} of {queue_path}")
            normalized: dict[str, str] = {}
            for key, value in assignments.items():
                if key not in ALLOWED_ASSIGNMENTS:
                    raise RunnerError(f"unsupported assignment key on line {lineno}: {key}")
                if not isinstance(value, str) or not value.strip():
                    raise RunnerError(f"assignment values must be non-empty strings on line {lineno}: {key}")
                normalized[key] = value.strip()
            queue.append(Experiment(experiment_id, description.strip(), normalized))
    return queue


def seed_resolved_queue(queue_items: list[Experiment], existing_descriptions: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    resolved: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for item in queue_items:
        if item.description in existing_descriptions:
            skipped.append({"id": item.id, "reason": "description already exists in results.tsv"})
            continue
        resolved.append(asdict(item))
    return resolved[:50], skipped + [
        {"id": item["id"], "reason": "queue capped at 50 experiments"} for item in resolved[50:]
    ]


def load_state(path: Path) -> dict[str, Any]:
    state = read_json(path)
    if state.get("state_version") != STATE_VERSION:
        raise RunnerError(f"unsupported state version in {path}: {state.get('state_version')}")
    return state


def active_completed_ids(state: dict[str, Any]) -> set[str]:
    return {item["id"] for item in state.get("completed", [])}


def update_state(state: dict[str, Any], state_path: Path, **updates: Any) -> None:
    state.update(updates)
    state["last_heartbeat_at"] = time.time()
    write_json(state_path, state)


def state_paths_for_args(args: argparse.Namespace) -> dict[str, Path]:
    control_root = Path(args.control_root).resolve()
    return control_paths(control_root, args.branch)


def init_state(args: argparse.Namespace) -> dict[str, Any]:
    target_root = Path(args.target_worktree).resolve()
    control_root = Path(args.control_root).resolve()
    queue_path = Path(args.queue).resolve()
    paths = state_paths_for_args(args)
    results_path = target_path(target_root, "results.tsv")
    queue_items = load_queue_file(queue_path)
    existing_descriptions = parse_results_descriptions(results_path)
    resolved_queue, skipped = seed_resolved_queue(queue_items, existing_descriptions)
    return {
        "state_version": STATE_VERSION,
        "branch": args.branch,
        "tag": branch_tag(args.branch),
        "target_worktree": str(target_root),
        "control_root": str(control_root),
        "queue_path": str(queue_path),
        "results_path": str(results_path),
        "state_path": str(paths["state_path"]),
        "pid_path": str(paths["pid_path"]),
        "report_path": str(paths["report_path"]),
        "supervisor_log_path": str(paths["supervisor_log_path"]),
        "log_dir": str(paths["log_dir"]),
        "lock_path": str(target_root / LOCK_FILENAME),
        "started_at": time.time(),
        "last_heartbeat_at": time.time(),
        "phase": "idle",
        "runner_pid": None,
        "training_pid": None,
        "start_best_commit": args.best_commit,
        "start_best_val": args.best_val,
        "current_best_commit": args.best_commit,
        "current_best_val": args.best_val,
        "queue_index": 0,
        "attempted": 0,
        "keep_count": 0,
        "discard_count": 0,
        "crash_count": 0,
        "active_experiment_id": None,
        "active_description": None,
        "active_assignments": None,
        "active_temp_commit": None,
        "active_log_path": None,
        "active_started_at": None,
        "completed": [],
        "skipped": skipped,
        "finished": False,
        "stop_requested": False,
        "stopped_reason": None,
        "resolved_queue": resolved_queue,
    }


def target_lock_path(state: dict[str, Any]) -> Path:
    return Path(state["lock_path"])


def acquire_target_lock(state: dict[str, Any]) -> None:
    lock_path = target_lock_path(state)
    runner_pid = int(state.get("runner_pid") or os.getpid())
    if lock_path.exists():
        payload = read_json(lock_path)
        existing_pid = int(payload.get("runner_pid") or 0)
        existing_state_path = payload.get("state_path")
        if process_alive(existing_pid) and existing_state_path != state["state_path"]:
            raise RunnerError(f"target already locked by live runner pid {existing_pid}: {lock_path}")
    write_json(
        lock_path,
        {
            "runner_pid": runner_pid,
            "branch": state["branch"],
            "state_path": state["state_path"],
            "control_root": state["control_root"],
            "started_at": time.time(),
        },
    )


def release_target_lock(state: dict[str, Any]) -> None:
    lock_path = target_lock_path(state)
    if not lock_path.exists():
        return
    payload = read_json(lock_path)
    if payload.get("state_path") != state["state_path"]:
        return
    lock_path.unlink(missing_ok=True)


def commit_experiment(target_root: Path, item: dict[str, Any], log_relpath: str) -> str:
    run_cmd(["git", "add", "train.py"], cwd=target_root)
    message = f"feat: overnight {item['id']}"
    why = f"why: overnight experiment {item['description']}"
    what = "what changed: " + ", ".join(f"{key}={value}" for key, value in item["assignments"].items())
    verify = f"how verified: pending uv run train.py > {log_relpath} 2>&1"
    run_cmd(["git", "commit", "-m", message, "-m", why, "-m", what, "-m", verify], cwd=target_root)
    return current_target_head(target_root)


def describe_next_item(state: dict[str, Any]) -> str:
    if state["queue_index"] >= len(state["resolved_queue"]):
        return "none"
    item = state["resolved_queue"][state["queue_index"]]
    return f"{item['id']} {item['description']}"


def should_stop(state: dict[str, Any], hours: float, max_experiments: int | None) -> str | None:
    if state.get("stop_requested"):
        return "stop requested"
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    if elapsed_hours >= hours:
        return f"elapsed time reached {hours} hours"
    if max_experiments is not None and state["attempted"] >= max_experiments:
        return f"max_experiments reached ({max_experiments})"
    if state["queue_index"] >= len(state["resolved_queue"]):
        return "queue exhausted"
    return None


def append_handoff_summary(state: dict[str, Any], stop_reason: str) -> None:
    handoff_path = target_path(Path(state["target_worktree"]), "HANDOFF_mar10.md")
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    block = [
        "",
        f"## Overnight Summary `{state['tag']}`",
        "",
        f"- report: `{Path(state['report_path']).relative_to(Path(state['control_root']))}`",
        f"- ending best commit: `{state['current_best_commit']}`",
        f"- ending best `val_bpb`: `{state['current_best_val']:.6f}`",
        f"- attempted: `{state['attempted']}`",
        f"- keeps: `{state['keep_count']}`",
        f"- discards: `{state['discard_count']}`",
        f"- crashes: `{state['crash_count']}`",
        f"- elapsed hours: `{elapsed_hours:.2f}`",
        f"- stopped because: `{stop_reason}`",
    ]
    with handoff_path.open("a") as handle:
        handle.write("\n".join(block) + "\n")


def finish_report(state: dict[str, Any], stop_reason: str) -> None:
    report_path = Path(state["report_path"])
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    next_item = None
    if state["queue_index"] < len(state["resolved_queue"]):
        next_item = state["resolved_queue"][state["queue_index"]]
    kept = [item for item in state["completed"] if item["status"] == "keep"]
    crashes = [item for item in state["completed"] if item["status"] == "crash"]
    recovered = [item for item in state["completed"] if item.get("recovered")]
    lines = [
        f"# Overnight Report: `{state['tag']}`",
        "",
        "## Summary",
        "",
        f"- start best: `{state['start_best_commit']}` / `{state['start_best_val']:.6f}`",
        f"- end best: `{state['current_best_commit']}` / `{state['current_best_val']:.6f}`",
        f"- elapsed hours: `{elapsed_hours:.2f}`",
        f"- experiments attempted: `{state['attempted']}`",
        f"- keeps: `{state['keep_count']}`",
        f"- discards: `{state['discard_count']}`",
        f"- crashes: `{state['crash_count']}`",
        f"- interrupted recoveries: `{len(recovered)}`",
        f"- stopped because: `{stop_reason}`",
        "",
        "## Top Winning Changes",
        "",
    ]
    if kept:
        for item in kept:
            lines.append(f"- `{item['id']}` `{item['val_bpb']}` {item['description']}")
    else:
        lines.append("- none")
    lines.extend(["", "## Crash Summaries", ""])
    if crashes:
        for item in crashes:
            lines.append(f"- `{item['id']}` {item['description']} ({item['reason']})")
    else:
        lines.append("- none")
    lines.extend(["", "## Skipped Queue Items", ""])
    if state["skipped"]:
        for item in state["skipped"]:
            lines.append(f"- `{item['id']}` {item['reason']}")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Candidate", ""])
    if next_item is None:
        lines.append("- none")
    else:
        lines.append(f"- `{next_item['id']}` {next_item['description']}")
    atomic_write_text(report_path, "\n".join(lines) + "\n")


def recover_active_experiment(state: dict[str, Any], state_path: Path) -> None:
    active_id = state.get("active_experiment_id")
    if not active_id:
        return
    if active_id in active_completed_ids(state):
        update_state(
            state,
            state_path,
            active_experiment_id=None,
            active_description=None,
            active_assignments=None,
            active_temp_commit=None,
            active_log_path=None,
            active_started_at=None,
            training_pid=None,
            phase="idle",
        )
        return
    if process_alive(state.get("training_pid")):
        raise RunnerError(
            f"active experiment {active_id} still has a live training pid {state['training_pid']}; use stop/status instead"
        )
    results_path = Path(state["results_path"])
    target_root = Path(state["target_worktree"])
    log_path = Path(state["active_log_path"]) if state.get("active_log_path") else None
    temp_commit = state.get("active_temp_commit") or current_target_head(target_root)
    description = state["active_description"]
    recovered = True
    try:
        if log_path and log_path.exists():
            try:
                val_bpb, memory_gb = parse_summary_from_log(log_path)
            except RunnerError:
                if description not in parse_results_descriptions(results_path):
                    append_results_row(results_path, temp_commit, "0.000000", "0.0", "crash", description)
                state["attempted"] += 1
                state["crash_count"] += 1
                state["completed"].append(
                    {
                        "id": active_id,
                        "commit": temp_commit,
                        "status": "crash",
                        "val_bpb": None,
                        "memory_gb": 0.0,
                        "description": description,
                        "reason": "recovered stale active run without summary log",
                        "log_path": str(log_path),
                        "recovered": recovered,
                    }
                )
                git_reset_hard(target_root, state["current_best_commit"])
            else:
                improved = val_bpb < float(state["current_best_val"])
                status = "keep" if improved else "discard"
                if description not in parse_results_descriptions(results_path):
                    append_results_row(
                        results_path,
                        temp_commit,
                        format_float(val_bpb),
                        f"{memory_gb:.1f}",
                        status,
                        description,
                    )
                state["attempted"] += 1
                if improved:
                    state["keep_count"] += 1
                    state["current_best_commit"] = temp_commit
                    state["current_best_val"] = val_bpb
                else:
                    state["discard_count"] += 1
                    git_reset_hard(target_root, state["current_best_commit"])
                state["completed"].append(
                    {
                        "id": active_id,
                        "commit": temp_commit,
                        "status": status,
                        "val_bpb": round(val_bpb, 6),
                        "memory_gb": round(memory_gb, 1),
                        "description": description,
                        "reason": "recovered from existing log",
                        "log_path": str(log_path),
                        "recovered": recovered,
                    }
                )
        else:
            if description not in parse_results_descriptions(results_path):
                append_results_row(results_path, temp_commit, "0.000000", "0.0", "crash", description)
            state["attempted"] += 1
            state["crash_count"] += 1
            state["completed"].append(
                {
                    "id": active_id,
                    "commit": temp_commit,
                    "status": "crash",
                    "val_bpb": None,
                    "memory_gb": 0.0,
                    "description": description,
                    "reason": "recovered stale active run without summary log",
                    "log_path": str(log_path) if log_path else None,
                    "recovered": recovered,
                }
            )
            git_reset_hard(target_root, state["current_best_commit"])
    finally:
        state["queue_index"] += 1
        update_state(
            state,
            state_path,
            active_experiment_id=None,
            active_description=None,
            active_assignments=None,
            active_temp_commit=None,
            active_log_path=None,
            active_started_at=None,
            training_pid=None,
            phase="idle",
        )


def reconcile_result(
    state: dict[str, Any],
    state_path: Path,
    log_path: Path,
    commit: str,
    description: str,
) -> None:
    target_root = Path(state["target_worktree"])
    results_path = Path(state["results_path"])
    val_bpb, memory_gb = parse_summary_from_log(log_path)
    improved = val_bpb < float(state["current_best_val"])
    status = "keep" if improved else "discard"
    append_results_row(results_path, commit, format_float(val_bpb), f"{memory_gb:.1f}", status, description)
    state["attempted"] += 1
    if improved:
        state["keep_count"] += 1
        state["current_best_commit"] = commit
        state["current_best_val"] = val_bpb
    else:
        state["discard_count"] += 1
        git_reset_hard(target_root, state["current_best_commit"])
    state["completed"].append(
        {
            "id": state["active_experiment_id"],
            "commit": commit,
            "status": status,
            "val_bpb": round(val_bpb, 6),
            "memory_gb": round(memory_gb, 1),
            "description": description,
            "reason": None,
            "log_path": str(log_path),
            "recovered": False,
        }
    )
    state["queue_index"] += 1
    update_state(
        state,
        state_path,
        active_experiment_id=None,
        active_description=None,
        active_assignments=None,
        active_temp_commit=None,
        active_log_path=None,
        active_started_at=None,
        training_pid=None,
        phase="idle",
    )


def record_crash(
    state: dict[str, Any],
    state_path: Path,
    commit: str,
    description: str,
    reason: str,
    log_path: Path | None,
) -> None:
    target_root = Path(state["target_worktree"])
    results_path = Path(state["results_path"])
    append_results_row(results_path, commit, "0.000000", "0.0", "crash", description)
    state["attempted"] += 1
    state["crash_count"] += 1
    state["completed"].append(
        {
            "id": state["active_experiment_id"],
            "commit": commit,
            "status": "crash",
            "val_bpb": None,
            "memory_gb": 0.0,
            "description": description,
            "reason": reason,
            "log_path": str(log_path) if log_path else None,
            "recovered": False,
        }
    )
    git_reset_hard(target_root, state["current_best_commit"])
    state["queue_index"] += 1
    update_state(
        state,
        state_path,
        active_experiment_id=None,
        active_description=None,
        active_assignments=None,
        active_temp_commit=None,
        active_log_path=None,
        active_started_at=None,
        training_pid=None,
        phase="idle",
    )


def run_training(state: dict[str, Any], state_path: Path, timeout_seconds: int) -> tuple[int, str | None]:
    global ACTIVE_PROCESS
    target_root = Path(state["target_worktree"])
    log_path = Path(state["active_log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_seconds
    with log_path.open("w") as handle:
        proc = subprocess.Popen(
            ["uv", "run", "train.py"],
            cwd=target_root,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ACTIVE_PROCESS = proc
        update_state(state, state_path, training_pid=proc.pid, phase="training")
        while True:
            try:
                returncode = proc.wait(timeout=10)
                ACTIVE_PROCESS = None
                return returncode, None
            except subprocess.TimeoutExpired:
                update_state(state, state_path, training_pid=proc.pid, phase="training")
                if STOP_REQUESTED:
                    proc.terminate()
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=30)
                    ACTIVE_PROCESS = None
                    handle.write("\nRUNNER_STOP: stop requested during training\n")
                    handle.flush()
                    return 143, "stop requested"
                if time.time() >= deadline:
                    proc.kill()
                    proc.wait(timeout=30)
                    ACTIVE_PROCESS = None
                    handle.write(f"\nRUNNER_TIMEOUT: exceeded {timeout_seconds} seconds\n")
                    handle.flush()
                    return 124, f"timeout after {timeout_seconds} seconds"


def handle_signal(signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    if ACTIVE_PROCESS is not None:
        try:
            ACTIVE_PROCESS.terminate()
        except OSError:
            pass


def runtime_skip(state: dict[str, Any], state_path: Path, item: dict[str, Any], reason: str) -> None:
    state["skipped"].append({"id": item["id"], "reason": reason})
    state["queue_index"] += 1
    update_state(
        state,
        state_path,
        active_experiment_id=None,
        active_description=None,
        active_assignments=None,
        active_temp_commit=None,
        active_log_path=None,
        active_started_at=None,
        training_pid=None,
        phase="idle",
    )


def run_loop(state_path: Path, hours: float, timeout_seconds: int, max_experiments: int | None) -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    state = load_state(state_path)
    state["runner_pid"] = os.getpid()
    update_state(state, state_path, runner_pid=os.getpid(), phase=state.get("phase", "idle"))
    acquire_target_lock(state)
    ensure_target_invariants(state)
    recover_active_experiment(state, state_path)
    target_root = Path(state["target_worktree"])
    results_path = Path(state["results_path"])
    prepare_constants = parse_python_constants(target_path(target_root, "prepare.py"))
    try:
        while True:
            stop_reason = should_stop(state, hours, max_experiments)
            if stop_reason is not None:
                update_state(state, state_path, finished=True, stopped_reason=stop_reason, phase="finished")
                finish_report(state, stop_reason)
                append_handoff_summary(state, stop_reason)
                return 0

            item = state["resolved_queue"][state["queue_index"]]
            update_state(
                state,
                state_path,
                active_experiment_id=item["id"],
                active_description=item["description"],
                active_assignments=item["assignments"],
                active_temp_commit=None,
                active_log_path=str(Path(state["log_dir"]) / f"{item['id']}.log"),
                active_started_at=time.time(),
                training_pid=None,
                phase="preparing_experiment",
            )

            git_reset_hard(target_root, state["current_best_commit"])
            current_descriptions = parse_results_descriptions(results_path)
            if item["description"] in current_descriptions:
                runtime_skip(state, state_path, item, "description already exists in results.tsv")
                continue

            train_path = target_path(target_root, "train.py")
            before = train_path.read_text()
            changed = rewrite_train_constants(train_path, item["assignments"])
            if not changed or train_path.read_text() == before:
                runtime_skip(state, state_path, item, "assignments already match current frontier")
                continue

            train_constants = parse_python_constants(train_path)
            valid, invalid_reason = validate_runtime_divisibility(train_constants, prepare_constants)
            log_path = Path(state["active_log_path"])
            if not valid:
                commit = current_target_head(target_root)
                record_crash(state, state_path, commit, item["description"], invalid_reason or "invalid divisibility", log_path)
                continue

            log_relpath = str(log_path.relative_to(Path(state["control_root"])))
            commit = commit_experiment(target_root, item, log_relpath)
            update_state(state, state_path, active_temp_commit=commit, phase="preparing_experiment")

            returncode, run_error = run_training(state, state_path, timeout_seconds)
            update_state(state, state_path, phase="evaluating", training_pid=None)
            if returncode != 0:
                record_crash(
                    state,
                    state_path,
                    commit,
                    item["description"],
                    run_error or f"train exited with code {returncode}",
                    log_path,
                )
                continue

            update_state(state, state_path, phase="reconciling")
            reconcile_result(state, state_path, log_path, commit, item["description"])
    finally:
        release_target_lock(state)


def print_dry_run(args: argparse.Namespace) -> None:
    target_root = Path(args.target_worktree).resolve()
    queue_path = Path(args.queue).resolve()
    results_path = target_path(target_root, "results.tsv")
    queue_items = load_queue_file(queue_path)
    resolved_queue, skipped = seed_resolved_queue(queue_items, parse_results_descriptions(results_path))
    prepare_constants = parse_python_constants(target_path(target_root, "prepare.py"))
    train_constants = parse_python_constants(target_path(target_root, "train.py"))
    print("Queue validation OK")
    print(f"resolved_experiments: {len(resolved_queue)}")
    for item in resolved_queue:
        candidate_constants = dict(train_constants)
        for key, value in item["assignments"].items():
            candidate_constants[key] = eval(value, {"__builtins__": {}}, {})
        valid, reason = validate_runtime_divisibility(candidate_constants, prepare_constants)
        payload = dict(item)
        payload["batch_divisibility"] = "valid" if valid else reason
        print(json.dumps(payload, sort_keys=True))
    if skipped:
        print("skipped:")
        for item in skipped:
            print(json.dumps(item, sort_keys=True))


def read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except ValueError:
        return None


def launch_runner(args: argparse.Namespace, resume: bool) -> int:
    paths = state_paths_for_args(args)
    control_root = Path(args.control_root).resolve()
    state_path = paths["state_path"]
    pid_path = paths["pid_path"]
    supervisor_log_path = paths["supervisor_log_path"]
    control_root.mkdir(parents=True, exist_ok=True)
    if resume:
        if not state_path.exists():
            raise RunnerError(f"cannot resume; state file does not exist: {state_path}")
        state = load_state(state_path)
        if state.get("finished"):
            raise RunnerError(f"cannot resume; run is already finished: {state_path}")
    else:
        if state_path.exists():
            existing = load_state(state_path)
            existing_pid = read_pid(pid_path)
            if existing_pid and process_alive(existing_pid):
                raise RunnerError(f"run already active with pid {existing_pid}: {state_path}")
        state = init_state(args)
        write_json(state_path, state)
    existing_pid = read_pid(pid_path)
    if existing_pid and process_alive(existing_pid):
        raise RunnerError(f"runner already active with pid {existing_pid}")
    supervisor_log_path.parent.mkdir(parents=True, exist_ok=True)
    with supervisor_log_path.open("a") as handle:
        proc = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "run-loop",
                "--state-path",
                str(state_path),
                "--hours",
                str(args.hours),
                "--timeout-seconds",
                str(args.timeout_seconds),
                *(["--max-experiments", str(args.max_experiments)] if args.max_experiments is not None else []),
            ],
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    atomic_write_text(pid_path, f"{proc.pid}\n")
    time.sleep(1)
    if proc.poll() is not None:
        if state_path.exists():
            final_state = load_state(state_path)
            if proc.returncode == 0 and final_state.get("finished"):
                print(f"runner completed immediately with stop reason: {final_state.get('stopped_reason')}")
                print(f"state: {state_path}")
                print(f"supervisor_log: {supervisor_log_path}")
                return 0
        raise RunnerError(
            f"runner exited immediately with code {proc.returncode}; see {supervisor_log_path}"
        )
    print(f"launched runner pid {proc.pid}")
    print(f"state: {state_path}")
    print(f"supervisor_log: {supervisor_log_path}")
    return 0


def status_runner(args: argparse.Namespace) -> int:
    paths = state_paths_for_args(args)
    state_path = paths["state_path"]
    pid_path = paths["pid_path"]
    if not state_path.exists():
        raise RunnerError(f"state file not found: {state_path}")
    state = load_state(state_path)
    pid = read_pid(pid_path)
    alive = process_alive(pid)
    print(json.dumps(
        {
            "runner_alive": alive,
            "runner_pid": pid,
            "phase": state.get("phase"),
            "active_experiment_id": state.get("active_experiment_id"),
            "current_best_commit": state.get("current_best_commit"),
            "current_best_val": state.get("current_best_val"),
            "last_heartbeat_at": state.get("last_heartbeat_at"),
            "next_candidate": describe_next_item(state),
            "attempted": state.get("attempted"),
            "keep_count": state.get("keep_count"),
            "discard_count": state.get("discard_count"),
            "crash_count": state.get("crash_count"),
            "finished": state.get("finished"),
            "stopped_reason": state.get("stopped_reason"),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


def stop_runner(args: argparse.Namespace) -> int:
    paths = state_paths_for_args(args)
    state_path = paths["state_path"]
    pid_path = paths["pid_path"]
    if not state_path.exists():
        raise RunnerError(f"state file not found: {state_path}")
    state = load_state(state_path)
    pid = read_pid(pid_path)
    if pid is None or not process_alive(pid):
        update_state(state, state_path, stop_requested=True)
        print("runner not alive; marked stop_requested for recovery")
        return 0
    update_state(state, state_path, stop_requested=True)
    os.kill(pid, signal.SIGTERM)
    print(f"sent SIGTERM to runner pid {pid}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser, include_best: bool) -> None:
        subparser.add_argument("--target-worktree", required=True)
        subparser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
        subparser.add_argument("--branch", required=True)
        subparser.add_argument("--queue", required=True)
        subparser.add_argument("--hours", type=float, default=8.0)
        subparser.add_argument("--timeout-seconds", type=int, default=600)
        subparser.add_argument("--max-experiments", type=int)
        if include_best:
            subparser.add_argument("--best-commit", required=True)
            subparser.add_argument("--best-val", type=float, required=True)

    add_common(subparsers.add_parser("dry-run"), include_best=True)
    add_common(subparsers.add_parser("launch"), include_best=True)
    add_common(subparsers.add_parser("resume"), include_best=False)

    for name in ("status", "stop"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
        sub.add_argument("--branch", required=True)

    run_loop_parser = subparsers.add_parser("run-loop")
    run_loop_parser.add_argument("--state-path", required=True)
    run_loop_parser.add_argument("--hours", type=float, required=True)
    run_loop_parser.add_argument("--timeout-seconds", type=int, required=True)
    run_loop_parser.add_argument("--max-experiments", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "dry-run":
        print_dry_run(args)
        return 0
    if args.command == "launch":
        return launch_runner(args, resume=False)
    if args.command == "resume":
        return launch_runner(args, resume=True)
    if args.command == "status":
        return status_runner(args)
    if args.command == "stop":
        return stop_runner(args)
    if args.command == "run-loop":
        return run_loop(Path(args.state_path), args.hours, args.timeout_seconds, args.max_experiments)
    raise RunnerError(f"unsupported command {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"overnight_control error: {exc}", file=sys.stderr)
        raise SystemExit(1)
