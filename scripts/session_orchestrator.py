#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    active_run_path,
    current_branch,
    evaluate_frontier_isolation_gate,
    evaluate_repeatability_gate,
    foreign_research_processes,
    load_json,
    orchestrator_state_path,
    parse_step_progress,
    process_alive,
    runtime_forensics_root,
)


ROOT = Path(__file__).resolve().parent.parent
HEARTBEAT_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 750
SYSTEM_SNAPSHOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("date.txt", "date"),
    ("uptime.txt", "uptime"),
    ("pmset_log_tail.txt", "pmset -g log | tail -n 200"),
    ("memory_pressure.txt", "memory_pressure"),
    ("processes.txt", "ps -Ao pid,etime,command | rg \"train.py|overnight_runner.py|python .*train.py\" || true"),
)
UNIFIED_LOG_QUERY = (
    "log show --style compact --start '{start}' --end '{end}' "
    "--predicate 'eventMessage CONTAINS[c] \"thermal\" OR "
    "eventMessage CONTAINS[c] \"Jetsam\" OR "
    "eventMessage CONTAINS[c] \"memorystatus\" OR "
    "eventMessage CONTAINS[c] \"MPS\" OR "
    "eventMessage CONTAINS[c] \"Metal\"' || true"
)


class OrchestratorError(RuntimeError):
    pass


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def iso_timestamp(value: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def timestamp_slug(value: float) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(value))


def shell_capture(command: str) -> str:
    proc = subprocess.run(
        ["/bin/zsh", "-lc", command],
        text=True,
        capture_output=True,
    )
    body = proc.stdout
    if proc.stderr:
        body += ("\n" if body else "") + proc.stderr
    header = f"$ {command}\nexit_code={proc.returncode}\n"
    if not body:
        return header
    if not body.endswith("\n"):
        body += "\n"
    return header + body


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def capture_system_snapshot(bundle_root: Path, phase: str) -> None:
    snapshot_root = bundle_root / phase
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for filename, command in SYSTEM_SNAPSHOT_COMMANDS:
        write_text(snapshot_root / filename, shell_capture(command))


def capture_unified_log(bundle_root: Path, started_at: float, ended_at: float) -> None:
    start_text = iso_timestamp(started_at - 30.0)
    end_text = iso_timestamp(ended_at + 30.0)
    command = UNIFIED_LOG_QUERY.format(start=start_text, end=end_text)
    write_text(bundle_root / "post_run" / "unified_log.txt", shell_capture(command))


def stage_bundle_root(plan: dict[str, Any], stage: dict[str, Any], started_at: float) -> Path | None:
    if stage.get("success_rule") != "frontier_isolation_gate":
        return None
    control_root = Path(str(plan["control_root"])).resolve()
    tag = str(plan["tag"])
    root = runtime_forensics_root(control_root, tag)
    return root / f"{timestamp_slug(started_at)}_{tag}_{stage['id']}"


def max_dt_ms_from_log(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    progress = parse_step_progress(log_path.read_text(errors="replace"))
    if not progress:
        return None
    return max(item["dt_ms"] for item in progress)


def compare_reference_classes(tag: str) -> dict[str, list[str]]:
    return {
        "visibly_unstable": [
            "frontier_repeat_a",
            "frontier_repeat_clean_c",
            "frontier_repeat_dedicated_b",
        ],
        "clean_but_degraded": [
            "frontier_repeat_dedicated_a",
            "frontier_repeat_isolation_a",
            "frontier_repeat_isolation_b",
        ],
        "historical_anchor": [
            f"canonical frontier {tag}: 5b486fb / 1.386688",
        ],
    }


def infer_target_root(control_root: Path) -> Path:
    if control_root.name == "control" and control_root.parent.name == "control" and control_root.parent.parent.name == "worktrees":
        return control_root.parent.parent.parent
    return control_root.parent


def load_plan(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    required = ("plan_id", "tag", "best_commit", "best_val", "execution_root", "control_root", "train_cmd", "max_stage_chain", "stages")
    missing = [key for key in required if key not in payload]
    if missing:
        joined = ", ".join(missing)
        raise OrchestratorError(f"plan file is missing required keys: {joined}")
    if not isinstance(payload["stages"], list) or not payload["stages"]:
        raise OrchestratorError("plan file must define at least one stage")
    return payload


def allowed_stage_chain(plan: dict[str, Any], mode: str) -> int:
    configured = plan.get("max_stage_chain")
    if isinstance(configured, int):
        return configured
    if isinstance(configured, dict):
        value = configured.get(mode)
        if isinstance(value, int):
            return value
    raise OrchestratorError("plan max_stage_chain must be an integer or an object keyed by mode")


def stage_by_id(plan: dict[str, Any], stage_id: str) -> dict[str, Any]:
    for stage in plan["stages"]:
        if stage["id"] == stage_id:
            return stage
    raise OrchestratorError(f"unknown stage id in plan: {stage_id}")


def default_next_stage(plan: dict[str, Any], completed_ids: list[str]) -> str | None:
    for stage in plan["stages"]:
        if stage["id"] not in completed_ids:
            return stage["id"]
    return None


def active_run_payload(control_root: Path, tag: str) -> dict[str, Any] | None:
    return load_json(active_run_path(control_root, tag))


def unfinished_active_run(active_run: dict[str, Any] | None) -> tuple[bool, bool]:
    if not active_run or bool(active_run.get("finished")):
        return False, False
    pid = active_run.get("pid")
    alive = process_alive(int(pid)) if pid is not None else False
    return True, alive


def plan_preflight_blockers(plan: dict[str, Any], resume: bool) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    tag = str(plan["tag"])
    execution_root = Path(str(plan["execution_root"])).resolve()
    control_root = Path(str(plan["control_root"])).resolve()

    if not execution_root.exists():
        blockers.append(f"execution root does not exist: `{execution_root}`")
        return blockers, warnings

    branch = current_branch(execution_root)
    if not branch.startswith("codex/execution-baseline"):
        blockers.append(f"execution root is on `{branch}`, not an execution-baseline branch")

    plan_tag = str(plan["tag"])
    active_run = active_run_payload(control_root, tag)
    has_unfinished, alive = unfinished_active_run(active_run)
    if has_unfinished and alive and not resume:
        blockers.append(f"unfinished active run already exists for `{tag}`")
    elif has_unfinished and not alive:
        warnings.append("previous active run is marked unfinished but its process is gone; treat it as interrupted")

    orchestrator_state = load_json(orchestrator_state_path(control_root, tag))
    if orchestrator_state and not bool(orchestrator_state.get("finished")):
        pid = orchestrator_state.get("pid")
        if pid is not None and process_alive(int(pid)) and not resume:
            blockers.append(f"unfinished orchestrator session already exists for `{tag}`")
        elif pid is not None and not process_alive(int(pid)):
            warnings.append("previous orchestrator session is marked unfinished but its process is gone; treat it as interrupted")

    foreign = foreign_research_processes(execution_root, allowed_pids={os.getpid()})
    if foreign:
        sample = foreign[0]
        blockers.append(
            f"foreign research process is alive outside execution root (pid {sample['pid']}, cwd `{sample.get('cwd') or 'unknown'}`)"
        )

    if not Path(str(plan["train_cmd"]).split()[0]).exists():
        blockers.append(f"train interpreter does not exist: `{str(plan['train_cmd']).split()[0]}`")

    for stage in plan["stages"]:
        queue_path = Path(str(stage["queue"]))
        if not queue_path.exists():
            blockers.append(f"stage `{stage['id']}` queue is missing: `{queue_path}`")
        if stage.get("kind") not in {"repeatability", "exploration"}:
            blockers.append(f"stage `{stage['id']}` has invalid kind `{stage.get('kind')}`")
    if plan_tag != tag:
        blockers.append(f"plan tag mismatch: expected `{tag}`")
    return blockers, warnings


def build_stage_command(stage: dict[str, Any], plan: dict[str, Any], resume: bool) -> list[str]:
    runner = ROOT / "scripts" / "overnight_runner.py"
    execution_root = Path(str(plan["execution_root"])).resolve()
    command = [
        sys.executable,
        str(runner),
        "--branch",
        current_branch(execution_root),
        "--best-commit",
        str(plan["best_commit"]),
        "--best-val",
        str(plan["best_val"]),
        "--queue",
        str(stage["queue"]),
        "--session-kind",
        str(stage["kind"]),
        "--timeout-seconds",
        str(stage.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
        "--stall-abort-ms",
        str(stage["stall_abort_ms"]),
        "--stall-abort-step-max",
        str(stage["stall_abort_step_max"]),
        "--stall-abort-count",
        str(stage["stall_abort_count"]),
    ]
    if stage.get("max_experiments") is not None:
        command.extend(["--max-experiments", str(stage["max_experiments"])])
    if stage.get("early_stop_floor") is not None:
        command.extend(["--early-stop-floor", str(stage["early_stop_floor"])])
    if stage.get("early_stop_after") is not None:
        command.extend(["--early-stop-after", str(stage["early_stop_after"])])
    if resume:
        command.append("--resume")
    return command


def operational_failure_reason(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        status_class = str(item.get("status_class") or "")
        if status_class in {"startup-hang", "early-step-stall", "late-timeout", "watchdog-timeout", "runner-abort"}:
            return f"stage recorded `{status_class}` on `{item.get('id')}`"
        if str(item.get("status") or "") == "crash":
            return f"stage crashed on `{item.get('id')}`"
        num_steps = item.get("num_steps")
        if num_steps is not None and int(num_steps) < 300:
            return f"stage produced a truncated run on `{item.get('id')}` with only {int(num_steps)} steps"
    return None


def stage_result(active_run: dict[str, Any], stage: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    state_path = Path(str(active_run["state_path"]))
    state = read_json(state_path)
    completed = list(state.get("completed", []))
    summary: dict[str, Any] = {
        "stage_id": stage["id"],
        "kind": stage["kind"],
        "state_path": str(state_path),
        "report_path": str(active_run.get("report_path")),
        "attempted": int(state.get("attempted", 0)),
        "completed": completed,
        "stopped_reason": state.get("stopped_reason"),
        "runtime_forensics_bundle": state.get("runtime_forensics_bundle"),
    }
    if stage.get("success_rule") == "repeatability_gate":
        evaluation = evaluate_repeatability_gate(completed, frontier_anchor_val=float(plan["best_val"]))
        summary["evaluation"] = evaluation
        summary["passed"] = bool(evaluation["passed"])
        summary["reason"] = evaluation["reason"]
        summary["failure_class"] = evaluation.get("failure_class")
        summary["recommended_search_stage"] = evaluation.get("next_stage")
        summary["search_eligible"] = bool(evaluation["passed"])
        return summary
    if stage.get("success_rule") == "frontier_isolation_gate":
        evaluation = evaluate_frontier_isolation_gate(
            completed,
            frontier_anchor_val=float(plan["best_val"]),
            required_repeats=int(stage.get("required_repeats", 2)),
        )
        summary["evaluation"] = evaluation
        summary["passed"] = bool(evaluation["passed"])
        summary["reason"] = evaluation["reason"]
        summary["failure_class"] = evaluation.get("failure_class")
        summary["search_eligible"] = False
        return summary

    failure = operational_failure_reason(completed)
    summary["passed"] = failure is None
    summary["reason"] = failure or "stage completed cleanly"
    summary["failure_class"] = None if failure is None else "operational-failure"
    summary["search_eligible"] = False
    return summary


def write_runtime_forensics_bundle(
    bundle_root: Path,
    plan: dict[str, Any],
    stage: dict[str, Any],
    summary: dict[str, Any],
    active_run: dict[str, Any] | None,
) -> None:
    bundle_root.mkdir(parents=True, exist_ok=True)
    state_path = Path(str(summary["state_path"])) if summary.get("state_path") else None
    state = read_json(state_path) if state_path and state_path.exists() else {}
    report_path = Path(str(summary["report_path"])) if summary.get("report_path") else None
    started_at = float(state.get("started_at") or summary.get("started_at") or time.time())
    ended_at = float(state.get("ended_at") or summary.get("ended_at") or time.time())

    metadata = {
        "tag": plan["tag"],
        "plan_id": plan["plan_id"],
        "stage_id": stage["id"],
        "session_kind": stage["kind"],
        "branch": active_run.get("branch") if active_run else plan.get("execution_root"),
        "execution_root": active_run.get("execution_root") if active_run else plan.get("execution_root"),
        "control_root": active_run.get("control_root") if active_run else plan.get("control_root"),
        "launcher": active_run.get("launcher") if active_run else "session_orchestrator",
        "queue_path": active_run.get("queue_path") if active_run else stage.get("queue"),
        "state_path": str(state_path) if state_path else None,
        "report_path": str(report_path) if report_path else None,
        "anchor_commit": plan["best_commit"],
        "anchor_val": float(plan["best_val"]),
        "started_at": started_at,
        "ended_at": ended_at,
        "started_at_iso": iso_timestamp(started_at),
        "ended_at_iso": iso_timestamp(ended_at),
    }
    write_json(bundle_root / "metadata.json", metadata)

    if state_path and state_path.exists():
        shutil.copy2(state_path, bundle_root / state_path.name)
    if report_path and report_path.exists():
        shutil.copy2(report_path, bundle_root / report_path.name)

    completed_items: list[dict[str, Any]] = []
    anchor_val = float(plan["best_val"])
    target_log_root = bundle_root / "logs"
    if target_log_root.exists():
        shutil.rmtree(target_log_root)
    target_log_root.mkdir(parents=True, exist_ok=True)
    for item in summary.get("completed", []):
        item_copy = dict(item)
        log_path_value = item.get("log_path")
        if log_path_value and active_run and active_run.get("execution_root"):
            absolute_log = Path(str(active_run["execution_root"])) / str(log_path_value)
            item_copy["absolute_log_path"] = str(absolute_log)
            item_copy["max_dt_ms"] = max_dt_ms_from_log(absolute_log)
            if absolute_log.exists():
                shutil.copy2(absolute_log, target_log_root / absolute_log.name)
        val = item.get("val_bpb")
        if val is not None:
            item_copy["anchor_delta"] = round(float(val) - anchor_val, 6)
        completed_items.append(item_copy)

    evaluation = dict(summary.get("evaluation") or {})
    final_summary = {
        "verdict": "pass" if summary.get("passed") else "fail",
        "failure_class": summary.get("failure_class"),
        "stop_reason": summary.get("reason"),
        "stage_id": stage["id"],
        "anchor_commit": plan["best_commit"],
        "anchor_val": anchor_val,
        "frontier_mean": evaluation.get("frontier_mean"),
        "frontier_spread": evaluation.get("frontier_spread"),
        "frontier_anchor_delta": evaluation.get("frontier_anchor_delta"),
        "completed": completed_items,
        "search_blocked": not bool(summary.get("passed")),
        "next_stage": stage.get("on_success", {}).get("next_stage") if summary.get("passed") else None,
        "runtime_forensics_bundle": str(bundle_root),
    }
    write_json(bundle_root / "summary.json", final_summary)

    comparisons = compare_reference_classes(str(plan["tag"]))
    lines = [
        f"# Backend Isolation Summary: `{plan['tag']}`",
        "",
        "## Verdict",
        "",
        f"- verdict: `{final_summary['verdict']}`",
        f"- failure class: `{summary.get('failure_class')}`",
        f"- stop reason: `{summary.get('reason')}`",
        f"- anchor: `{plan['best_commit']}` / `{anchor_val:.6f}`",
        f"- bundle: `{bundle_root}`",
        "",
        "## Current Results",
        "",
    ]
    if completed_items:
        for item in completed_items:
            val_text = "NA" if item.get("val_bpb") is None else f"{float(item['val_bpb']):.6f}"
            delta = item.get("anchor_delta")
            delta_text = "NA" if delta is None else f"{float(delta):+.6f}"
            max_dt = item.get("max_dt_ms")
            max_dt_text = "NA" if max_dt is None else str(int(max_dt))
            lines.append(
                f"- `{item.get('id')}` `val_bpb={val_text}` `delta={delta_text}` "
                f"`num_steps={item.get('num_steps')}` `max_dt_ms={max_dt_text}`"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Comparison Classes",
            "",
            "- visibly unstable:",
            *[f"  - `{name}`" for name in comparisons["visibly_unstable"]],
            "- clean but degraded:",
            *[f"  - `{name}`" for name in comparisons["clean_but_degraded"]],
            "- historical anchor:",
            *[f"  - `{name}`" for name in comparisons["historical_anchor"]],
        ]
    )
    write_text(bundle_root / "summary.md", "\n".join(lines) + "\n")


def write_orchestrator_state(path: Path, payload: dict[str, Any]) -> None:
    payload["last_heartbeat_at"] = time.time()
    write_json(path, payload)


def run_stage(stage: dict[str, Any], plan: dict[str, Any], orchestrator_state: dict[str, Any], resume: bool) -> dict[str, Any]:
    control_root = Path(str(plan["control_root"])).resolve()
    stage_started_at = time.time()
    bundle_root = stage_bundle_root(plan, stage, stage_started_at)
    env = os.environ.copy()
    env["AUTORESEARCH_ROOT"] = str(Path(str(plan["execution_root"])).resolve())
    env["AUTORESEARCH_CONTROL_ROOT"] = str(control_root)
    env["AUTORESEARCH_GATED_RESULTS_TAG"] = str(plan["tag"])
    env["AUTORESEARCH_TRAIN_CMD"] = str(plan["train_cmd"])
    env["AUTORESEARCH_PLAN_PATH"] = str(orchestrator_state["plan_path"])
    env["AUTORESEARCH_STAGE_ID"] = str(stage["id"])
    env["AUTORESEARCH_LAUNCHER"] = "session_orchestrator"
    if bundle_root is not None:
        env["AUTORESEARCH_RUNTIME_FORENSICS_BUNDLE"] = str(bundle_root)
        capture_system_snapshot(bundle_root, "pre_run")

    command = build_stage_command(stage, plan, resume=resume)
    proc = subprocess.Popen(command, cwd=ROOT, env=env)
    orchestrator_state["current_stage_id"] = stage["id"]
    orchestrator_state["current_stage_kind"] = stage["kind"]
    orchestrator_state["current_stage_queue"] = stage["queue"]
    orchestrator_state["current_stage_pid"] = proc.pid
    orchestrator_state["next_action"] = f"run stage `{stage['id']}`"
    if bundle_root is not None:
        orchestrator_state["current_stage_bundle"] = str(bundle_root)
    write_orchestrator_state(orchestrator_state_path(control_root, str(plan["tag"])), orchestrator_state)

    last_heartbeat = 0.0
    while True:
        returncode = proc.poll()
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_SECONDS:
            write_orchestrator_state(orchestrator_state_path(control_root, str(plan["tag"])), orchestrator_state)
            last_heartbeat = now
        if returncode is not None:
            break
        time.sleep(1.0)

    active_run = active_run_payload(control_root, str(plan["tag"]))
    if returncode != 0:
        summary = {
            "stage_id": stage["id"],
            "kind": stage["kind"],
            "state_path": None,
            "report_path": None,
            "attempted": 0,
            "completed": [],
            "stopped_reason": f"stage runner exited with code {returncode}",
            "runtime_forensics_bundle": str(bundle_root) if bundle_root is not None else None,
            "passed": False,
            "reason": f"stage runner exited with code {returncode} before updating active state",
            "search_eligible": False,
            "started_at": stage_started_at,
            "ended_at": time.time(),
        }
        if bundle_root is not None:
            capture_system_snapshot(bundle_root, "post_run")
            capture_unified_log(bundle_root, stage_started_at, time.time())
            write_runtime_forensics_bundle(bundle_root, plan, stage, summary, None)
        return summary
    if not active_run:
        raise OrchestratorError(f"stage `{stage['id']}` finished without updating active run state for `{plan['tag']}`")
    if str(active_run.get("stage_id") or "") != str(stage["id"]):
        raise OrchestratorError(
            f"stage `{stage['id']}` finished but active run points at `{active_run.get('stage_id')}`; refusing stale state"
        )
    summary = stage_result(active_run, stage, plan)
    if bundle_root is not None:
        capture_system_snapshot(bundle_root, "post_run")
        active_state = read_json(Path(str(summary["state_path"])))
        capture_unified_log(
            bundle_root,
            float(active_state.get("started_at") or stage_started_at),
            float(active_state.get("ended_at") or time.time()),
        )
        write_runtime_forensics_bundle(bundle_root, plan, stage, summary, active_run)
    return summary


def next_stage_from_summary(summary: dict[str, Any], stage: dict[str, Any]) -> tuple[str | None, str]:
    if summary["passed"]:
        on_success = stage.get("on_success") or {}
        if on_success.get("action") == "stop":
            return None, str(on_success.get("reason") or summary["reason"])
        if on_success.get("next_stage"):
            return str(on_success["next_stage"]), summary["reason"]
        if stage.get("success_rule") == "repeatability_gate":
            return summary.get("recommended_search_stage"), summary["reason"]
        return None, summary["reason"]
    failure_class = str(summary.get("failure_class") or "")
    on_failure_by_class = stage.get("on_failure_by_class") or {}
    on_failure = on_failure_by_class.get(failure_class) or stage.get("on_failure") or {}
    if on_failure.get("next_stage"):
        return str(on_failure["next_stage"]), str(on_failure.get("reason") or summary["reason"])
    return None, str(on_failure.get("reason") or summary["reason"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-driven session orchestration for autoresearch.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--mode", choices=("tonight", "overnight"), default="tonight")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).resolve()
    plan = load_plan(plan_path)
    control_root = Path(str(plan["control_root"])).resolve()
    target_root = infer_target_root(control_root)
    blockers, warnings = plan_preflight_blockers(plan, resume=args.resume)
    if blockers:
        for blocker in blockers:
            print(f"preflight blocker: {blocker}", file=sys.stderr)
        return 2

    state_path = orchestrator_state_path(control_root, str(plan["tag"]))
    if args.resume and state_path.exists():
        orchestrator_state = read_json(state_path)
        orchestrator_state.setdefault("current_stage_bundle", None)
    else:
        orchestrator_state = {
            "plan_id": plan["plan_id"],
            "plan_path": str(plan_path),
            "tag": plan["tag"],
            "mode": args.mode,
            "pid": os.getpid(),
            "target_root": str(target_root),
            "execution_root": str(Path(str(plan["execution_root"])).resolve()),
            "control_root": str(control_root),
            "started_at": time.time(),
            "ended_at": None,
            "finished": False,
            "interrupted": False,
            "completed_stages": [],
            "current_stage_id": None,
            "current_stage_kind": None,
            "current_stage_queue": None,
            "current_stage_pid": None,
            "current_stage_bundle": None,
            "warnings": warnings,
            "next_action": "launch first stage",
            "overnight_eligible": False,
        }
    write_orchestrator_state(state_path, orchestrator_state)

    completed_ids = [item["stage_id"] for item in orchestrator_state.get("completed_stages", [])]
    next_stage_id = orchestrator_state.get("current_stage_id") if args.resume and orchestrator_state.get("current_stage_id") else default_next_stage(plan, completed_ids)
    if next_stage_id is None:
        orchestrator_state["finished"] = True
        orchestrator_state["ended_at"] = time.time()
        orchestrator_state["next_action"] = "plan is already exhausted"
        write_orchestrator_state(state_path, orchestrator_state)
        return 0

    stage_limit = allowed_stage_chain(plan, args.mode)
    stages_run = 0
    resume_current = args.resume
    while next_stage_id is not None and stages_run < stage_limit:
        stage = stage_by_id(plan, next_stage_id)
        summary = run_stage(stage, plan, orchestrator_state, resume=resume_current)
        resume_current = False
        orchestrator_state["completed_stages"].append(summary)
        orchestrator_state["current_stage_id"] = None
        orchestrator_state["current_stage_kind"] = None
        orchestrator_state["current_stage_queue"] = None
        orchestrator_state["current_stage_pid"] = None
        orchestrator_state["current_stage_bundle"] = None
        next_stage_id, reason = next_stage_from_summary(summary, stage)
        stages_run += 1

        if not summary["passed"]:
            orchestrator_state["finished"] = True
            orchestrator_state["ended_at"] = time.time()
            orchestrator_state["next_action"] = f"stop autonomous search: {reason}"
            orchestrator_state["overnight_eligible"] = False
            write_orchestrator_state(state_path, orchestrator_state)
            return 0

        if next_stage_id is None:
            orchestrator_state["finished"] = True
            orchestrator_state["ended_at"] = time.time()
            recommended_search_stage = summary.get("recommended_search_stage")
            if recommended_search_stage:
                orchestrator_state["next_action"] = (
                    f"{reason}; do not launch search tonight. "
                    f"Recommended day-2 canary: `{recommended_search_stage}`"
                )
            elif args.mode == "tonight":
                orchestrator_state["next_action"] = f"tonight boundary reached cleanly: {reason}"
            else:
                orchestrator_state["next_action"] = f"stage chain completed: {reason}"
            orchestrator_state["overnight_eligible"] = False
            write_orchestrator_state(state_path, orchestrator_state)
            return 0

        orchestrator_state["next_action"] = f"advance to stage `{next_stage_id}`"
        write_orchestrator_state(state_path, orchestrator_state)

    orchestrator_state["finished"] = True
    orchestrator_state["ended_at"] = time.time()
    orchestrator_state["next_action"] = f"autonomy boundary reached after {stages_run} stage(s)"
    orchestrator_state["overnight_eligible"] = False
    write_orchestrator_state(state_path, orchestrator_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
