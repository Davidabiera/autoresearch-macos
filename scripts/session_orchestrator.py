#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    active_run_path,
    current_branch,
    evaluate_repeatability_gate,
    foreign_research_processes,
    load_json,
    orchestrator_state_path,
    process_alive,
)


ROOT = Path(__file__).resolve().parent.parent
HEARTBEAT_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 750


class OrchestratorError(RuntimeError):
    pass


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


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


def stage_result(active_run: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
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
    }
    if stage.get("success_rule") == "repeatability_gate":
        evaluation = evaluate_repeatability_gate(completed)
        summary["evaluation"] = evaluation
        summary["passed"] = bool(evaluation["passed"])
        summary["reason"] = evaluation["reason"]
        summary["next_stage"] = evaluation.get("next_stage")
        return summary

    failure = operational_failure_reason(completed)
    summary["passed"] = failure is None
    summary["reason"] = failure or "stage completed cleanly"
    return summary


def write_orchestrator_state(path: Path, payload: dict[str, Any]) -> None:
    payload["last_heartbeat_at"] = time.time()
    write_json(path, payload)


def run_stage(stage: dict[str, Any], plan: dict[str, Any], orchestrator_state: dict[str, Any], resume: bool) -> dict[str, Any]:
    control_root = Path(str(plan["control_root"])).resolve()
    env = os.environ.copy()
    env["AUTORESEARCH_ROOT"] = str(Path(str(plan["execution_root"])).resolve())
    env["AUTORESEARCH_CONTROL_ROOT"] = str(control_root)
    env["AUTORESEARCH_GATED_RESULTS_TAG"] = str(plan["tag"])
    env["AUTORESEARCH_TRAIN_CMD"] = str(plan["train_cmd"])
    env["AUTORESEARCH_PLAN_PATH"] = str(orchestrator_state["plan_path"])
    env["AUTORESEARCH_STAGE_ID"] = str(stage["id"])
    env["AUTORESEARCH_LAUNCHER"] = "session_orchestrator"

    command = build_stage_command(stage, plan, resume=resume)
    proc = subprocess.Popen(command, cwd=ROOT, env=env)
    orchestrator_state["current_stage_id"] = stage["id"]
    orchestrator_state["current_stage_kind"] = stage["kind"]
    orchestrator_state["current_stage_queue"] = stage["queue"]
    orchestrator_state["current_stage_pid"] = proc.pid
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
    if not active_run:
        raise OrchestratorError(f"stage `{stage['id']}` finished without updating active run state for `{plan['tag']}`")
    return stage_result(active_run, stage)


def next_stage_from_summary(summary: dict[str, Any], stage: dict[str, Any]) -> tuple[str | None, str]:
    if summary["passed"]:
        if stage.get("success_rule") == "repeatability_gate":
            return summary.get("next_stage"), summary["reason"]
        return None, summary["reason"]
    return None, summary["reason"]


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
            if args.mode == "tonight":
                orchestrator_state["next_action"] = f"tonight boundary reached cleanly: {reason}"
                orchestrator_state["overnight_eligible"] = True
            else:
                orchestrator_state["next_action"] = f"stage chain completed: {reason}"
                orchestrator_state["overnight_eligible"] = True
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
