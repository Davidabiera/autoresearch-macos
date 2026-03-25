#!/usr/bin/env python3
"""
Bounded unattended experiment runner for autoresearch.

Usage:
    uv run python scripts/overnight_runner.py \
        --branch autoresearch/mar10 \
        --best-commit 5b486fb \
        --best-val 1.386688 \
        --queue queues/mar10_optimizer_micro_next.jsonl \
        --hours 8
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    active_run_path,
    classify_log,
    gated_result_metadata,
    parse_gated_results,
    parse_step_progress,
    result_ledger_path,
)


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("AUTORESEARCH_ROOT", str(DEFAULT_ROOT))).resolve()
TRAIN_PATH = ROOT / "train.py"
PREPARE_PATH = ROOT / "prepare.py"
RESULTS_PATH = ROOT / "results.tsv"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def default_control_root(root: Path) -> Path:
    candidate = root / "worktrees" / "control" / "control"
    return candidate if candidate.exists() else root


CONTROL_ROOT = Path(os.environ.get("AUTORESEARCH_CONTROL_ROOT", str(default_control_root(ROOT)))).resolve()

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
KNOWN_UNTRACKED = {
    "results.tsv",
    "run.log",
    "RUN_NOTES_mar10.md",
    "HANDOFF_mar10.md",
    "BETA_REPORT_mar10.md",
}
RUNNER_OWNED_PREFIXES = ("logs/", "state/", "reports/")
RUNNER_SOURCE_PREFIXES = ("scripts/", "queues/")
SUMMARY_PATTERNS = {
    "val_bpb": re.compile(r"^val_bpb:\s+([0-9.]+)$", re.MULTILINE),
    "peak_vram_mb": re.compile(r"^peak_vram_mb:\s+([0-9.]+)$", re.MULTILINE),
}
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
STALL_POLL_SECONDS = 1.0


class RunnerError(RuntimeError):
    pass


@dataclass
class Experiment:
    id: str
    description: str
    assignments: dict[str, str]


def run_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if check and proc.returncode != 0:
        raise RunnerError(
            f"command failed: {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def current_branch() -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def current_head() -> str:
    return run_cmd(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()


def handoff_path(tag: str) -> Path:
    return ROOT / f"HANDOFF_{tag}.md"


def ensure_allowed_git_state() -> None:
    status = run_cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"]).stdout.splitlines()
    disallowed: list[str] = []
    for line in status:
        if not line:
            continue
        code = line[:2]
        path = line[3:]
        if code == "??" and path in KNOWN_UNTRACKED:
            continue
        if code == "??" and any(path.startswith(prefix) for prefix in RUNNER_OWNED_PREFIXES):
            continue
        if code == "??" and any(path.startswith(prefix) for prefix in RUNNER_SOURCE_PREFIXES):
            continue
        disallowed.append(line)
    if disallowed:
        joined = "\n".join(disallowed)
        raise RunnerError(f"git worktree must be clean except known artifacts; found:\n{joined}")


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


def control_tag(default_tag: str) -> str:
    return os.environ.get("AUTORESEARCH_GATED_RESULTS_TAG", default_tag)


def exploration_results_path(tag: str) -> Path:
    return result_ledger_path(CONTROL_ROOT, control_tag(tag), "exploration")


def session_results_path(tag: str, session_kind: str) -> Path:
    return result_ledger_path(CONTROL_ROOT, control_tag(tag), session_kind)


def repeatability_results_path(tag: str) -> Path:
    return result_ledger_path(CONTROL_ROOT, control_tag(tag), "repeatability")


def parse_gated_result_descriptions(path: Path) -> set[str]:
    _, descriptions = gated_result_metadata(parse_gated_results(path))
    return descriptions


def append_session_result(tag: str, session_kind: str, payload: dict[str, Any]) -> None:
    path = session_results_path(tag, session_kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def default_paths(branch: str) -> tuple[str, Path, Path, Path]:
    tag = branch.split("/", 1)[1] if "/" in branch else branch
    state_path = ROOT / "state" / f"overnight_{tag}.json"
    report_path = ROOT / "reports" / f"overnight_{tag}.md"
    log_dir = ROOT / "logs" / "overnight" / tag
    return tag, state_path, report_path, log_dir


def load_queue_file(queue_path: Path) -> list[Experiment]:
    experiments: list[Experiment] = []
    seen_ids: set[str] = set()
    with queue_path.open() as handle:
        for lineno, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunnerError(f"invalid JSON on line {lineno} of {queue_path}: {exc}") from exc
            for field in ("id", "description", "assignments"):
                if field not in data:
                    raise RunnerError(f"missing '{field}' on line {lineno} of {queue_path}")
            if not isinstance(data["id"], str) or not SAFE_ID_RE.match(data["id"]):
                raise RunnerError(f"invalid id on line {lineno} of {queue_path}: {data['id']!r}")
            if data["id"] in seen_ids:
                raise RunnerError(f"duplicate id in queue: {data['id']}")
            seen_ids.add(data["id"])
            if not isinstance(data["description"], str) or not data["description"].strip():
                raise RunnerError(f"invalid description on line {lineno} of {queue_path}")
            assignments = data["assignments"]
            if not isinstance(assignments, dict):
                raise RunnerError(f"assignments must be an object on line {lineno} of {queue_path}")
            normalized: dict[str, str] = {}
            for key, value in assignments.items():
                if key not in ALLOWED_ASSIGNMENTS:
                    raise RunnerError(f"unsupported assignment key on line {lineno}: {key}")
                if not isinstance(value, str) or not value.strip():
                    raise RunnerError(f"assignment values must be non-empty strings on line {lineno}: {key}")
                normalized[key] = value.strip()
            experiments.append(
                Experiment(
                    id=data["id"],
                    description=data["description"].strip(),
                    assignments=normalized,
                )
            )
    return experiments


def seed_resolved_queue(
    queue_items: list[Experiment],
    existing_descriptions: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    resolved: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for item in queue_items:
        if item.description in existing_descriptions:
            skipped.append({"id": item.id, "reason": "description already exists in results.tsv or gated results"})
            continue
        resolved.append(asdict(item))
    if len(resolved) > 50:
        overflow = resolved[50:]
        for item in overflow:
            skipped.append({"id": item["id"], "reason": "queue capped at 50 experiments"})
        resolved = resolved[:50]
    return resolved, skipped


def ensure_results_file() -> None:
    if RESULTS_PATH.exists():
        return
    RESULTS_PATH.write_text("commit\tval_bpb\tmemory_gb\tstatus\tdescription\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise RunnerError(f"failed to parse state file {path}: {exc}") from exc


def active_pointer_path(tag: str) -> Path:
    return active_run_path(CONTROL_ROOT, control_tag(tag))


def active_pointer_payload(state: dict[str, Any], state_path: Path, report_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tag": state["tag"],
        "control_tag": state["control_tag"],
        "branch": state["branch"],
        "session_kind": state["session_kind"],
        "state_path": str(state_path),
        "report_path": str(report_path),
        "queue_path": state["queue_path"],
        "started_at": state["started_at"],
        "active_experiment_id": state.get("active_experiment_id"),
        "finished": bool(state.get("finished")),
        "stopped_reason": state.get("stopped_reason"),
    }
    if state.get("ended_at") is not None:
        payload["ended_at"] = state["ended_at"]
    return payload


def persist_state(state: dict[str, Any], state_path: Path, report_path: Path) -> None:
    write_json(state_path, state)
    write_json(active_pointer_path(str(state["tag"])), active_pointer_payload(state, state_path, report_path))


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


def format_float(value: float) -> str:
    return f"{value:.6f}"


def append_results_row(commit: str, val_bpb: str, memory_gb: str, status: str, description: str) -> None:
    ensure_results_file()
    with RESULTS_PATH.open("a") as handle:
        handle.write(f"{commit}\t{val_bpb}\t{memory_gb}\t{status}\t{description}\n")


def parse_summary_from_log(log_path: Path) -> tuple[float, float]:
    text = log_path.read_text()
    extracted: dict[str, float] = {}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            raise RunnerError(f"missing summary field '{key}' in {log_path}")
        extracted[key] = float(match.group(1))
    return extracted["val_bpb"], extracted["peak_vram_mb"] / 1024.0


def resolve_train_command() -> list[str]:
    override = os.environ.get("AUTORESEARCH_TRAIN_CMD")
    if override:
        return shlex.split(override)
    if VENV_PYTHON.exists():
        return [str(VENV_PYTHON), str(TRAIN_PATH)]
    return [sys.executable, str(TRAIN_PATH)]


def ensure_torch_available(command: list[str]) -> None:
    if len(command) < 2 or Path(command[1]) != TRAIN_PATH:
        return
    if not Path(command[0]).name.startswith("python"):
        return
    probe = subprocess.run(
        [command[0], "-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('torch') else 1)"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if probe.returncode == 0:
        return
    if not VENV_PYTHON.exists():
        hint = (
            f"target worktree has no venv at {VENV_PYTHON}; "
            "launch the runner with an interpreter that already has torch or set AUTORESEARCH_TRAIN_CMD."
        )
    elif Path(command[0]) != VENV_PYTHON:
        hint = f"launch the runner with {VENV_PYTHON} or set AUTORESEARCH_TRAIN_CMD."
    else:
        hint = "the selected venv is missing torch; repair that environment before resuming."
    stderr = probe.stderr.strip() or probe.stdout.strip() or "torch module not found"
    raise RunnerError(
        f"selected train interpreter cannot import torch: {command[0]}\n"
        f"detail: {stderr}\n{hint}"
    )


def terminate_process_group(proc: subprocess.Popen[str], grace_seconds: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait()


def rewrite_train_constants(assignments: dict[str, str]) -> bool:
    original = TRAIN_PATH.read_text()
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
    TRAIN_PATH.write_text(rewritten)
    return rewritten != original and changed


def git_reset_hard(commit: str) -> None:
    run_cmd(["git", "reset", "--hard", commit])


def commit_experiment(item: dict[str, Any], log_relpath: str) -> str:
    run_cmd(["git", "add", "train.py"])
    message = f"feat: overnight {item['id']}"
    why = f"why: overnight experiment {item['description']}"
    changes = "what changed: " + ", ".join(
        f"{key}={value}" for key, value in item["assignments"].items()
    )
    verify = f"how verified: pending {' '.join(resolve_train_command())} > {log_relpath} 2>&1"
    run_cmd(["git", "commit", "-m", message, "-m", why, "-m", changes, "-m", verify])
    return current_head()


def detect_live_stall_abort(
    log_path: Path,
    stall_abort_ms: int | None,
    stall_abort_step_max: int | None,
    stall_abort_count: int | None,
) -> str | None:
    if (
        stall_abort_ms is None
        or stall_abort_step_max is None
        or stall_abort_count is None
        or stall_abort_ms <= 0
        or stall_abort_step_max <= 0
        or stall_abort_count <= 0
        or not log_path.exists()
    ):
        return None
    progress = parse_step_progress(log_path.read_text(errors="replace"))
    stalled = [
        item
        for item in progress
        if item["step"] <= stall_abort_step_max and item["dt_ms"] >= stall_abort_ms
    ]
    if len(stalled) < stall_abort_count:
        return None
    worst = max(stalled, key=lambda item: item["dt_ms"])
    return (
        f"early stall threshold exceeded ({len(stalled)} >= {stall_abort_count}; "
        f"dt>={stall_abort_ms}ms by step<={stall_abort_step_max}; "
        f"worst step {worst['step']} at {worst['dt_ms'] / 1000.0:.1f}s)"
    )


def run_training(
    log_path: Path,
    timeout_seconds: int,
    stall_abort_ms: int | None,
    stall_abort_step_max: int | None,
    stall_abort_count: int | None,
) -> tuple[int, str | None]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = resolve_train_command()
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    with log_path.open("w") as handle:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        while True:
            returncode = proc.poll()
            if returncode is not None:
                return returncode, None
            stall_reason = detect_live_stall_abort(
                log_path,
                stall_abort_ms=stall_abort_ms,
                stall_abort_step_max=stall_abort_step_max,
                stall_abort_count=stall_abort_count,
            )
            if stall_reason is not None:
                terminate_process_group(proc)
                handle.write(f"\nRUNNER_ABORT: {stall_reason}\n")
                handle.flush()
                return 125, stall_reason
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_process_group(proc)
                handle.write(f"\nRUNNER_TIMEOUT: exceeded {timeout_seconds} seconds\n")
                handle.flush()
                return 124, f"timeout after {timeout_seconds} seconds"
            time.sleep(min(STALL_POLL_SECONDS, remaining))


def init_state(args: argparse.Namespace, tag: str, state_path: Path, report_path: Path, log_dir: Path) -> dict[str, Any]:
    queue_path = Path(args.queue)
    queue_items = load_queue_file(queue_path)
    if args.session_kind == "exploration":
        invalid = [item.id for item in queue_items if len(item.assignments) != 1]
        if invalid:
            joined = ", ".join(invalid)
            raise RunnerError(f"exploration queues must contain single-variable items; invalid ids: {joined}")
    else:
        invalid = [item.id for item in queue_items if len(item.assignments) > 1]
        if invalid:
            joined = ", ".join(invalid)
            raise RunnerError(f"repeatability queues may only contain baseline or single-variable items; invalid ids: {joined}")
    existing_descriptions: set[str] = set()
    if args.session_kind == "exploration":
        existing_descriptions = parse_results_descriptions(RESULTS_PATH) | parse_gated_result_descriptions(
            exploration_results_path(tag)
        )
    resolved_queue, skipped = seed_resolved_queue(queue_items, existing_descriptions)
    return {
        "branch": args.branch,
        "tag": tag,
        "control_tag": control_tag(tag),
        "session_kind": args.session_kind,
        "queue_path": str(queue_path),
        "state_path": str(state_path),
        "report_path": str(report_path),
        "log_dir": str(log_dir),
        "started_at": time.time(),
        "ended_at": None,
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
        "completed": [],
        "skipped": skipped,
        "resolved_queue": resolved_queue,
        "finished": False,
        "stopped_reason": None,
    }


def load_or_init_state(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path, Path]:
    tag, state_path, report_path, log_dir = default_paths(args.branch)
    if args.resume:
        if not state_path.exists():
            raise RunnerError(f"--resume requested but state file does not exist: {state_path}")
        state = read_json(state_path)
        state.setdefault("control_tag", control_tag(tag))
        state.setdefault("session_kind", args.session_kind)
        state.setdefault("ended_at", None)
        return state, state_path, report_path, log_dir
    state = init_state(args, tag, state_path, report_path, log_dir)
    return state, state_path, report_path, log_dir


def print_dry_run(state: dict[str, Any]) -> None:
    prepare_constants = parse_python_constants(PREPARE_PATH)
    train_constants = parse_python_constants(TRAIN_PATH)
    print("Queue validation OK")
    print(f"resolved_experiments: {len(state['resolved_queue'])}")
    for item in state["resolved_queue"]:
        candidate_constants = dict(train_constants)
        for key, value in item["assignments"].items():
            candidate_constants[key] = ast.literal_eval(value)
        valid, reason = validate_runtime_divisibility(candidate_constants, prepare_constants)
        payload = dict(item)
        payload["batch_divisibility"] = "valid" if valid else reason
        print(json.dumps(payload, sort_keys=True))
    if state["skipped"]:
        print("skipped:")
        for item in state["skipped"]:
            print(json.dumps(item, sort_keys=True))


def runtime_skip(state: dict[str, Any], item: dict[str, Any], reason: str, state_path: Path) -> None:
    state["skipped"].append({"id": item["id"], "reason": reason})
    state["queue_index"] += 1
    state["active_experiment_id"] = None
    persist_state(state, state_path, Path(state["report_path"]))


def finish_report(state: dict[str, Any], report_path: Path, stop_reason: str) -> None:
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    next_item = None
    if state["queue_index"] < len(state["resolved_queue"]):
        next_item = state["resolved_queue"][state["queue_index"]]
    kept = [item for item in state["completed"] if item["status"] == "keep"]
    crashes = [item for item in state["completed"] if item["status"] == "crash"]
    lines = [
        f"# Overnight Report: `{state['tag']}`",
        "",
        "## Summary",
        "",
        f"- session kind: `{state['session_kind']}`",
        f"- start best: `{state['start_best_commit']}` / `{state['start_best_val']:.6f}`",
        f"- end best: `{state['current_best_commit']}` / `{state['current_best_val']:.6f}`",
        f"- elapsed hours: `{elapsed_hours:.2f}`",
        f"- experiments attempted: `{state['attempted']}`",
        f"- keeps: `{state['keep_count']}`",
        f"- discards: `{state['discard_count']}`",
        f"- crashes: `{state['crash_count']}`",
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
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def append_handoff_summary(state: dict[str, Any], report_path: Path, stop_reason: str) -> None:
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    path = handoff_path(state["tag"])
    block = [
        "",
        f"## Overnight Summary `{state['tag']}`",
        "",
        f"- report: `{report_path.relative_to(ROOT)}`",
        f"- ending best commit: `{state['current_best_commit']}`",
        f"- ending best `val_bpb`: `{state['current_best_val']:.6f}`",
        f"- attempted: `{state['attempted']}`",
        f"- keeps: `{state['keep_count']}`",
        f"- discards: `{state['discard_count']}`",
        f"- crashes: `{state['crash_count']}`",
        f"- elapsed hours: `{elapsed_hours:.2f}`",
        f"- stopped because: `{stop_reason}`",
    ]
    with path.open("a") as handle:
        handle.write("\n".join(block) + "\n")


def early_stop_reason(state: dict[str, Any], args: argparse.Namespace) -> str | None:
    if state.get("session_kind") != "exploration":
        return None
    if args.early_stop_floor is None or args.early_stop_after is None:
        return None
    informative = [
        item
        for item in state["completed"]
        if item.get("status") in {"keep", "discard"} and item.get("val_bpb") is not None
    ]
    if len(informative) < args.early_stop_after:
        return None
    window = informative[: args.early_stop_after]
    if any(item.get("status") == "keep" for item in window):
        return None
    if any(float(item["val_bpb"]) <= args.early_stop_floor for item in window):
        return None
    return (
        f"early stop: first {args.early_stop_after} informative results all exceeded "
        f"{args.early_stop_floor:.6f}"
    )


def should_stop(state: dict[str, Any], args: argparse.Namespace) -> str | None:
    elapsed_hours = (time.time() - state["started_at"]) / 3600.0
    if elapsed_hours >= args.hours:
        return f"elapsed time reached {args.hours} hours"
    if args.max_experiments is not None and state["attempted"] >= args.max_experiments:
        return f"max_experiments reached ({args.max_experiments})"
    stop = early_stop_reason(state, args)
    if stop is not None:
        return stop
    if state["queue_index"] >= len(state["resolved_queue"]):
        return "queue exhausted"
    return None


def read_log_text(log_path: Path | None) -> str:
    if log_path is None or not log_path.exists():
        return ""
    return log_path.read_text(errors="replace")


def build_ledger_entry(
    state: dict[str, Any],
    item: dict[str, Any],
    commit: str,
    status: str,
    classification: dict[str, Any],
    log_path: Path | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": item["id"],
        "commit": commit,
        "description": item["description"],
        "informative": bool(classification.get("informative")),
        "issue_scope": classification.get("issue_scope"),
        "log_path": str(log_path) if log_path is not None else None,
        "reason": classification.get("reason"),
        "session_kind": state["session_kind"],
        "source_branch": state["branch"],
        "status": status,
        "status_class": classification.get("status_class"),
        "suppress_planner": state["session_kind"] == "exploration"
        and (
            bool(classification.get("informative"))
            or classification.get("status_class") in {"config-invalid", "resource-oom"}
        ),
        "val_bpb": classification.get("val_bpb"),
    }
    for key in (
        "memory_gb",
        "startup_seconds",
        "warmup_seconds",
        "training_seconds",
        "eval_seconds",
        "total_seconds",
        "runner_timeout_seconds",
    ):
        if classification.get(key) is not None:
            entry[key] = classification.get(key)
    return entry


def build_completed_entry(
    item: dict[str, Any],
    commit: str,
    status: str,
    classification: dict[str, Any],
    log_relpath: str | None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": item["id"],
        "commit": commit,
        "status": status,
        "val_bpb": classification.get("val_bpb"),
        "memory_gb": classification.get("memory_gb", 0.0) or 0.0,
        "description": item["description"],
        "reason": classification.get("reason"),
        "log_path": log_relpath,
        "status_class": classification.get("status_class"),
        "issue_scope": classification.get("issue_scope"),
    }
    for key in ("startup_seconds", "warmup_seconds", "training_seconds", "eval_seconds", "total_seconds"):
        if classification.get(key) is not None:
            entry[key] = classification[key]
    return entry


def run_loop(args: argparse.Namespace, state: dict[str, Any], state_path: Path, report_path: Path, log_dir: Path) -> None:
    prepare_constants = parse_python_constants(PREPARE_PATH)
    while True:
        stop_reason = should_stop(state, args)
        if stop_reason is not None:
            state["finished"] = True
            state["stopped_reason"] = stop_reason
            state["active_experiment_id"] = None
            state["ended_at"] = time.time()
            persist_state(state, state_path, report_path)
            finish_report(state, report_path, stop_reason)
            append_handoff_summary(state, report_path, stop_reason)
            return

        item = state["resolved_queue"][state["queue_index"]]
        state["active_experiment_id"] = item["id"]
        persist_state(state, state_path, report_path)

        git_reset_hard(state["current_best_commit"])
        current_descriptions: set[str] = set()
        if state["session_kind"] == "exploration":
            current_descriptions = parse_results_descriptions(RESULTS_PATH)
            current_descriptions.update(parse_gated_result_descriptions(exploration_results_path(state["tag"])))
        if state["session_kind"] == "exploration" and item["description"] in current_descriptions:
            runtime_skip(state, item, "description already exists in results.tsv or gated results", state_path)
            continue

        log_path = log_dir / f"{item['id']}.log"
        log_relpath = str(log_path.relative_to(ROOT))
        base_repeat = state["session_kind"] == "repeatability" and not item["assignments"]
        if base_repeat:
            commit = current_head()
        else:
            before = TRAIN_PATH.read_text()
            changed = rewrite_train_constants(item["assignments"])
            if not changed or TRAIN_PATH.read_text() == before:
                runtime_skip(state, item, "assignments already match current frontier", state_path)
                continue
            commit = commit_experiment(item, log_relpath)

        train_constants = parse_python_constants(TRAIN_PATH)
        valid, invalid_reason = validate_runtime_divisibility(train_constants, prepare_constants)
        if not valid:
            append_results_row(commit, "0.000000", "0.0", "crash", f"{item['description']} ({invalid_reason})")
            classification = {
                "informative": False,
                "issue_scope": "experiment-specific",
                "reason": invalid_reason,
                "status_class": "config-invalid",
                "val_bpb": None,
            }
            append_session_result(
                state["tag"],
                state["session_kind"],
                build_ledger_entry(state, item, commit, "crash", classification, None),
            )
            state["attempted"] += 1
            state["crash_count"] += 1
            state["completed"].append(build_completed_entry(item, commit, "crash", classification, None))
            git_reset_hard(state["current_best_commit"])
            state["queue_index"] += 1
            state["active_experiment_id"] = None
            persist_state(state, state_path, report_path)
            continue

        returncode, run_error = run_training(
            log_path,
            args.timeout_seconds,
            args.stall_abort_ms,
            args.stall_abort_step_max,
            args.stall_abort_count,
        )
        log_text = read_log_text(log_path)
        if returncode != 0:
            append_results_row(commit, "0.000000", "0.0", "crash", item["description"])
            classification = classify_log(log_text, state)
            if classification["status_class"] == "unknown-crash" and run_error:
                classification["reason"] = run_error
            append_session_result(
                state["tag"],
                state["session_kind"],
                build_ledger_entry(state, item, commit, "crash", classification, log_path),
            )
            state["attempted"] += 1
            state["crash_count"] += 1
            state["completed"].append(build_completed_entry(item, commit, "crash", classification, log_relpath))
            git_reset_hard(state["current_best_commit"])
            state["queue_index"] += 1
            state["active_experiment_id"] = None
            persist_state(state, state_path, report_path)
            continue

        try:
            val_bpb, memory_gb = parse_summary_from_log(log_path)
        except RunnerError as exc:
            append_results_row(commit, "0.000000", "0.0", "crash", item["description"])
            classification = classify_log(log_text, state)
            classification["reason"] = str(exc)
            append_session_result(
                state["tag"],
                state["session_kind"],
                build_ledger_entry(state, item, commit, "crash", classification, log_path),
            )
            state["attempted"] += 1
            state["crash_count"] += 1
            state["completed"].append(build_completed_entry(item, commit, "crash", classification, log_relpath))
            git_reset_hard(state["current_best_commit"])
            state["queue_index"] += 1
            state["active_experiment_id"] = None
            persist_state(state, state_path, report_path)
            continue

        improved = val_bpb < float(state["current_best_val"])
        status = "keep" if improved else "discard"
        append_results_row(commit, format_float(val_bpb), f"{memory_gb:.1f}", status, item["description"])
        classification = classify_log(log_text, state)
        classification["memory_gb"] = round(memory_gb, 1)
        classification["val_bpb"] = round(val_bpb, 6)
        append_session_result(
            state["tag"],
            state["session_kind"],
            build_ledger_entry(state, item, commit, status, classification, log_path),
        )
        state["attempted"] += 1
        if improved:
            state["keep_count"] += 1
            if state["session_kind"] == "exploration":
                state["current_best_commit"] = commit
                state["current_best_val"] = val_bpb
        else:
            state["discard_count"] += 1
        if state["session_kind"] == "exploration" or not base_repeat:
            git_reset_hard(state["current_best_commit"])
        state["completed"].append(build_completed_entry(item, commit, status, classification, log_relpath))
        state["queue_index"] += 1
        state["active_experiment_id"] = None
        persist_state(state, state_path, report_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--best-commit", required=True)
    parser.add_argument("--best-val", type=float, required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-experiments", type=int)
    parser.add_argument("--session-kind", choices=("exploration", "repeatability"), default="exploration")
    parser.add_argument("--early-stop-floor", type=float)
    parser.add_argument("--early-stop-after", type=int)
    parser.add_argument("--stall-abort-ms", type=int)
    parser.add_argument("--stall-abort-step-max", type=int)
    parser.add_argument("--stall-abort-count", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stall_args = (args.stall_abort_ms, args.stall_abort_step_max, args.stall_abort_count)
    if any(value is not None for value in stall_args) and not all(value is not None for value in stall_args):
        raise RunnerError(
            "--stall-abort-ms, --stall-abort-step-max, and --stall-abort-count must be provided together"
        )
    if current_branch() != args.branch:
        raise RunnerError(f"expected branch {args.branch}, found {current_branch()}")
    ensure_allowed_git_state()
    ensure_torch_available(resolve_train_command())
    state, state_path, report_path, log_dir = load_or_init_state(args)
    if args.dry_run:
        print_dry_run(state)
        return 0
    persist_state(state, state_path, report_path)
    run_loop(args, state, state_path, report_path, log_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"overnight_runner error: {exc}", file=sys.stderr)
        raise SystemExit(1)
