#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    DEFAULT_CONTROL_ROOT,
    DEFAULT_TARGET_ROOT,
    artifact_paths,
    axis_from_item_id,
    best_nonkeep_by_axis,
    collect_frontier_context,
    current_branch,
    evaluate_frontier_isolation_gate,
    evaluate_repeatability_gate,
    foreign_research_processes,
    load_json,
    parse_noncanonical_signals,
    parse_repeatability_results,
    parse_step_progress,
    process_alive,
)
from frontier_status import build_payload as build_frontier_payload


def load_active_state(paths: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    active_run = load_json(Path(paths["active_run"]))
    if not active_run:
        return None, None
    state_path = active_run.get("state_path")
    if not state_path:
        return active_run, None
    active_state = load_json(Path(str(state_path)))
    if active_state is not None:
        active_run["finished"] = bool(active_state.get("finished", active_run.get("finished")))
        active_run["active_experiment_id"] = active_state.get("active_experiment_id", active_run.get("active_experiment_id"))
        active_run["stopped_reason"] = active_state.get("stopped_reason", active_run.get("stopped_reason"))
    return active_run, active_state


def active_run_interrupted(active_run: dict[str, Any] | None) -> bool:
    if not active_run or bool(active_run.get("finished")):
        return False
    pid = active_run.get("pid")
    if pid is None:
        return True
    return not process_alive(int(pid))


def load_orchestrator_state(paths: dict[str, Any]) -> dict[str, Any] | None:
    return load_json(Path(paths["orchestrator_state"]))


def orchestrator_interrupted(orchestrator_state: dict[str, Any] | None) -> bool:
    if not orchestrator_state or bool(orchestrator_state.get("finished")):
        return False
    pid = orchestrator_state.get("pid")
    if pid is None:
        return True
    return not process_alive(int(pid))


def load_default_plan(paths: dict[str, Any]) -> dict[str, Any] | None:
    return load_json(Path(paths["default_plan"]))


def informative_results(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in completed
        if item.get("status") in {"keep", "discard"} and item.get("val_bpb") is not None
    ]


def active_log_path(active_state: dict[str, Any] | None) -> Path | None:
    if not active_state:
        return None
    log_dir = active_state.get("log_dir")
    active_experiment_id = active_state.get("active_experiment_id")
    if not log_dir or not active_experiment_id:
        return None
    return Path(str(log_dir)) / f"{active_experiment_id}.log"


def live_stall_warning(
    active_state: dict[str, Any] | None,
    stall_ms: int = 30_000,
    stall_step_max: int = 20,
    stall_count: int = 3,
) -> str | None:
    log_path = active_log_path(active_state)
    if log_path is None or not log_path.exists():
        return None
    progress = parse_step_progress(log_path.read_text(errors="replace"))
    stalled = [
        item
        for item in progress
        if item["step"] <= stall_step_max and item["dt_ms"] >= stall_ms
    ]
    if len(stalled) < stall_count:
        return None
    worst = max(stalled, key=lambda item: item["dt_ms"])
    return (
        f"active log already shows {len(stalled)} early stalls >= {stall_ms}ms by step <= {stall_step_max}; "
        f"worst step {worst['step']} at {worst['dt_ms'] / 1000.0:.1f}s"
    )


def repeatability_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_repeatability_dedicated_session.jsonl"


def weight_decay_confirmation_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_weight_decay_confirmation.jsonl"


def scalar_canary_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_scalar_first_canary.jsonl"


def frontier_isolation_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_frontier_isolation.jsonl"


def current_repeatability_results(
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if active_run and active_run.get("session_kind") == "repeatability" and active_state:
        return list(active_state.get("completed", []))
    return repeatability_results


def repeatability_branching_decision(context: dict[str, Any], items: list[dict[str, Any]]) -> str:
    evaluation = evaluate_repeatability_gate(items, frontier_anchor_val=float(context["current_best_val"]))
    if not evaluation["passed"]:
        return f"pause hyperparameter search and open backend/environment investigation; {evaluation['reason']}"
    if evaluation["next_stage"] == "weight_decay_confirmation":
        return (
            "environment is stable and weight decay materially wins; "
            f"run the confirmation block `{weight_decay_confirmation_queue_path(context)}`"
        )
    return (
        "environment is stable and weight decay does not materially win; "
        f"close weight decay and launch the scalar-first canary `{scalar_canary_queue_path(context)}`"
    )


def frontier_isolation_decision(context: dict[str, Any], items: list[dict[str, Any]]) -> str:
    evaluation = evaluate_frontier_isolation_gate(items, frontier_anchor_val=float(context["current_best_val"]))
    if not evaluation["passed"]:
        return f"pause hyperparameter search and continue backend/environment investigation; {evaluation['reason']}"
    return (
        "frontier isolation passed; baseline repeats are clean enough to reopen the controlled loop. "
        f"Next queue: `{repeatability_queue_path(context)}`"
    )


def early_stop_signal(active_state: dict[str, Any] | None, floor: float, after: int) -> dict[str, Any] | None:
    if not active_state or active_state.get("finished"):
        return None
    completed = list(active_state.get("completed", []))
    if any(item.get("status_class") in {"startup-hang", "early-step-stall", "late-timeout"} for item in completed):
        return {
            "should_stop": True,
            "message": "stop live run now; an operational stall class was recorded in-session",
        }
    informative = informative_results(completed)
    if len(informative) >= after:
        window = informative[:after]
        if all(float(item["val_bpb"]) > floor and item.get("status") != "keep" for item in window):
            return {
                "should_stop": True,
                "message": (
                    f"stop live run early; first {after} informative results all exceeded {floor:.6f}"
                ),
            }
    return {
        "should_stop": False,
        "message": (
            f"continue live run; only {len(informative)}/{after} informative results have been evaluated "
            f"against the {floor:.6f} early-stop floor"
        ),
    }


def preflight_blockers(
    plan: dict[str, Any] | None,
    active_run: dict[str, Any] | None,
    active_run_is_interrupted: bool,
    orchestrator_state: dict[str, Any] | None,
    orchestrator_is_interrupted: bool,
) -> list[str]:
    if not plan:
        return []
    blockers: list[str] = []
    execution_root = Path(str(plan["execution_root"])).resolve()
    if not execution_root.exists():
        blockers.append(f"execution root does not exist: `{execution_root}`")
        return blockers
    branch = current_branch(execution_root)
    if not branch.startswith("codex/execution-baseline"):
        blockers.append(f"execution root is on `{branch}`, not an execution-baseline branch")
    if active_run and not bool(active_run.get("finished")) and not active_run_is_interrupted:
        blockers.append(f"unfinished stage run is active for control tag `{plan['tag']}`")
    if orchestrator_state and not bool(orchestrator_state.get("finished")) and not orchestrator_is_interrupted:
        blockers.append(f"unfinished orchestrator session is active for control tag `{plan['tag']}`")
    allowed_pids: set[int] = set()
    if active_run and not active_run_is_interrupted and active_run.get("pid") is not None:
        allowed_pids.add(int(active_run["pid"]))
    if orchestrator_state and not orchestrator_is_interrupted and orchestrator_state.get("pid") is not None:
        allowed_pids.add(int(orchestrator_state["pid"]))
    foreign = foreign_research_processes(execution_root, allowed_pids=allowed_pids)
    for item in foreign[:3]:
        blockers.append(
            f"foreign research process pid {item['pid']} is alive outside execution root (cwd `{item.get('cwd') or 'unknown'}`)"
        )
    return blockers


def recommended_next_action(
    context: dict[str, Any],
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
    early_stop_floor: float,
    early_stop_after: int,
    live_warning: str | None,
    orchestrator_state: dict[str, Any] | None,
    active_run_is_interrupted: bool,
    orchestrator_is_interrupted: bool,
    blockers: list[str],
) -> str:
    if blockers:
        return "do not launch autonomous stages until blockers are cleared: " + "; ".join(blockers)
    if orchestrator_is_interrupted:
        return "previous orchestrator session is interrupted; inspect its state and relaunch through the orchestrator"
    if active_run_is_interrupted:
        return "previous stage runner is interrupted; inspect its state and relaunch through the orchestrator"

    signal = early_stop_signal(active_state, early_stop_floor, early_stop_after)
    if live_warning and active_run and not bool(active_run.get("finished")):
        return "allow the current repeatability item to finish, but treat this session as runtime-unstable unless later repeats normalize"
    if signal:
        return str(signal["message"])

    if active_run and bool(active_run.get("finished")):
        if active_run.get("session_kind") == "repeatability":
            session_results = current_repeatability_results(active_run, active_state, repeatability_results)
            active_branch = str(active_run.get("branch") or "")
            active_queue = str(active_run.get("queue_path") or "")
            if "frontier-baseline-stability" in active_branch or active_queue.endswith("mar10_frontier_baseline_clean_probe.jsonl"):
                return (
                    "treat the single baseline probe as signal only; launch "
                    f"the dedicated-session repeatability block `{repeatability_queue_path(context)}`"
                )
            if "frontier-isolation" in active_branch or active_queue.endswith("mar10_frontier_isolation.jsonl"):
                return frontier_isolation_decision(context, session_results)
            return repeatability_branching_decision(context, session_results)
        weight_decay_results = [
            item
            for item in context["gated_results"]
            if axis_from_item_id(str(item.get("id") or "")) == "weight_decay" and item.get("val_bpb") is not None
        ]
        recent = weight_decay_results[-4:]
        if (
            len(recent) >= 4
            and all(float(item["val_bpb"]) > early_stop_floor for item in recent)
            and not any(float(item["val_bpb"]) <= 1.386732 for item in recent)
        ):
            return "launch the repeatability block before opening a new search axis"
        if context["fresh_unresolved_queue"]:
            candidate = context["fresh_unresolved_queue"][0]
            return f"run next queued exploration item `{candidate['id']}`"
        return "define the next search band; the current exploration queue is exhausted"

    if orchestrator_state and orchestrator_state.get("next_action"):
        return str(orchestrator_state["next_action"])

    if context["fresh_unresolved_queue"]:
        candidate = context["fresh_unresolved_queue"][0]
        return f"run next queued exploration item `{candidate['id']}`"
    return "define the next search band; no fresh exploration items remain"


def build_payload(
    target_root: Path,
    branch: str,
    control_root: Path | None,
    early_stop_floor: float,
    early_stop_after: int,
) -> dict[str, Any]:
    context = collect_frontier_context(target_root, branch, control_root=control_root)
    paths = artifact_paths(target_root, branch, control_root=control_root, tag=context["tag"])
    frontier = build_frontier_payload(target_root, branch, control_root)
    context["current_best_val"] = frontier["current_best_val"]
    active_run, active_state = load_active_state(paths)
    active_run_is_interrupted = active_run_interrupted(active_run)
    orchestrator_state = load_orchestrator_state(paths)
    orchestrator_is_interrupted = orchestrator_interrupted(orchestrator_state)
    default_plan = load_default_plan(paths)
    blockers = preflight_blockers(default_plan, active_run, active_run_is_interrupted, orchestrator_state, orchestrator_is_interrupted)
    repeatability_results = parse_repeatability_results(Path(paths["repeatability_results"]))
    noncanonical_signals = parse_noncanonical_signals(Path(paths["noncanonical_signals"]))
    live_warning = live_stall_warning(active_state)
    exploration_recent = context["gated_results"][-5:]
    repeatability_recent = repeatability_results[-5:]
    noncanonical_recent = noncanonical_signals[-5:]
    best_axis = best_nonkeep_by_axis(context["gated_results"])
    return {
        "frontier": frontier,
        "active_run": active_run,
        "active_state": active_state,
        "active_run_interrupted": active_run_is_interrupted,
        "orchestrator_state": orchestrator_state,
        "orchestrator_interrupted": orchestrator_is_interrupted,
        "default_plan": default_plan,
        "preflight_blockers": blockers,
        "live_stall_warning": live_warning,
        "last_exploration_results": exploration_recent,
        "last_repeatability_results": repeatability_recent,
        "last_noncanonical_signals": noncanonical_recent,
        "best_gated_nonkeep_by_axis": best_axis,
        "recommended_next_action": recommended_next_action(
            context,
            active_run,
            active_state,
            repeatability_results,
            early_stop_floor,
            early_stop_after,
            live_warning,
            orchestrator_state,
            active_run_is_interrupted,
            orchestrator_is_interrupted,
            blockers,
        ),
    }


def render_result_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- none"]
    lines: list[str] = []
    for item in items:
        val = item.get("val_bpb")
        val_text = "NA" if val is None else f"{float(val):.6f}"
        status_class = item.get("status_class") or "unknown"
        lines.append(
            f"- `{item.get('id')}` `{item.get('status')}` `{val_text}` `{status_class}` {item.get('description')}"
        )
    return lines


def render_axis_lines(best_axis: dict[str, dict[str, Any]]) -> list[str]:
    if not best_axis:
        return ["- none"]
    lines: list[str] = []
    for axis in sorted(best_axis):
        item = best_axis[axis]
        lines.append(
            f"- `{axis}`: `{item.get('id')}` `{float(item['val_bpb']):.6f}` {item.get('description')}"
        )
    return lines


def render_markdown(payload: dict[str, Any], early_stop_floor: float, early_stop_after: int) -> str:
    frontier = payload["frontier"]
    active_run = payload["active_run"]
    active_state = payload["active_state"]
    live_warning = payload["live_stall_warning"]
    lines = [
        f"# Session Status: `{frontier['branch']}`",
        "",
        "## Canonical Frontier",
        "",
        f"- best commit: `{frontier['current_best_commit']}`",
        f"- best `val_bpb`: `{frontier['current_best_val']:.6f}`",
        f"- execution ready: `{str(frontier['execution_ready']).lower()}`",
        "",
        "## Active Run",
        "",
    ]
    if not active_run:
        lines.append("- none")
    else:
        lines.append(f"- session kind: `{active_run.get('session_kind')}`")
        lines.append(f"- branch: `{active_run.get('branch')}`")
        lines.append(f"- state: `{active_run.get('state_path')}`")
        lines.append(f"- finished: `{str(bool(active_run.get('finished'))).lower()}`")
        if active_run.get("pid") is not None:
            lines.append(f"- pid: `{active_run.get('pid')}`")
        if payload["active_run_interrupted"]:
            lines.append("- interrupted: `true`")
        if active_state:
            lines.append(f"- attempted: `{active_state.get('attempted', 0)}`")
            lines.append(f"- active experiment: `{active_state.get('active_experiment_id')}`")
        signal = early_stop_signal(active_state, early_stop_floor, early_stop_after)
        if signal:
            lines.append(f"- governance: `{signal['message']}`")
        if live_warning:
            lines.append(f"- live stall warning: `{live_warning}`")

    lines.extend(["", "## Orchestrator", ""])
    orchestrator_state = payload["orchestrator_state"]
    if not orchestrator_state:
        lines.append("- none")
    else:
        lines.append(f"- plan id: `{orchestrator_state.get('plan_id')}`")
        lines.append(f"- finished: `{str(bool(orchestrator_state.get('finished'))).lower()}`")
        lines.append(f"- current stage: `{orchestrator_state.get('current_stage_id')}`")
        lines.append(f"- next action: `{orchestrator_state.get('next_action')}`")
        if payload["orchestrator_interrupted"]:
            lines.append("- interrupted: `true`")
        completed_stages = orchestrator_state.get("completed_stages") or []
        if completed_stages:
            last_stage = completed_stages[-1]
            lines.append(
                f"- last stage: `{last_stage.get('stage_id')}` passed=`{str(bool(last_stage.get('passed'))).lower()}` reason=`{last_stage.get('reason')}`"
            )

    lines.extend(["", "## Preflight Blockers", ""])
    if payload["preflight_blockers"]:
        for blocker in payload["preflight_blockers"]:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")

    lines.extend(["", "## Recent Exploration Results", ""])
    lines.extend(render_result_lines(payload["last_exploration_results"]))
    lines.extend(["", "## Recent Repeatability Results", ""])
    lines.extend(render_result_lines(payload["last_repeatability_results"]))
    lines.extend(["", "## Recent Noncanonical Signals", ""])
    lines.extend(render_result_lines(payload["last_noncanonical_signals"]))
    lines.extend(["", "## Best Gated Non-Keep By Axis", ""])
    lines.extend(render_axis_lines(payload["best_gated_nonkeep_by_axis"]))
    lines.extend(["", "## Next Action", ""])
    lines.append(f"- {payload['recommended_next_action']}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize canonical frontier and live session state.")
    parser.add_argument("--branch", required=True, help="Branch to inspect, e.g. autoresearch/mar10")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
    parser.add_argument("--early-stop-floor", type=float, default=1.3880)
    parser.add_argument("--early-stop-after", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    control_root = Path(args.control_root).resolve()
    payload = build_payload(target_root, args.branch, control_root, args.early_stop_floor, args.early_stop_after)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(render_markdown(payload, args.early_stop_floor, args.early_stop_after), end="")


if __name__ == "__main__":
    main()
