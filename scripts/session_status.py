#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    COMPLETION_FAILURE_CLASSES,
    DEFAULT_CONTROL_ROOT,
    DEFAULT_TARGET_ROOT,
    MATERIAL_WIN_THRESHOLD,
    REPEATABILITY_SPREAD_THRESHOLD,
    STALL_FAILURE_CLASSES,
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
    repeatability_failure_detail,
)
from frontier_status import build_payload as build_frontier_payload

SCRIPT_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = SCRIPT_DIR.parent
POST_REBOOT_AGENT_LABEL = "com.codex.mar10-fixed-step-post-reboot"
POST_REBOOT_AGENT_PLIST = Path("/Users/davidabiera/Library/LaunchAgents") / f"{POST_REBOOT_AGENT_LABEL}.plist"
POST_REBOOT_LAUNCH_LOG = WORKTREE_ROOT / "logs" / "mar10_fixed_step_post_reboot_launch.log"
POST_REBOOT_ARM_STATE = WORKTREE_ROOT / "state" / "mar10_fixed_step_post_reboot_arm.env"


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


def load_frontier_ledger(control_root: Path | None) -> dict[str, Any] | None:
    if control_root is None:
        return None
    return load_json(control_root / "state" / "frontier.json")


def current_boot_epoch() -> int | None:
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "kern.boottime"],
            check=True,
            capture_output=True,
            text=True,
        )
        match = re.search(r"\{ sec = (\d+),", proc.stdout)
        if match:
            return int(match.group(1))
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        proc = subprocess.run(
            ["/bin/zsh", "-lc", "last reboot | head -1"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    match = re.search(r"reboot time\s+\w+\s+(\w+\s+\d+\s+\d+:\d+)", proc.stdout)
    if not match:
        return None
    now = dt.datetime.now()
    boot = dt.datetime.strptime(f"{match.group(1)} {now.year}", "%b %d %H:%M %Y")
    if boot > now:
        boot = boot.replace(year=boot.year - 1)
    return int(boot.timestamp())


def read_post_reboot_arm_state() -> dict[str, str]:
    if not POST_REBOOT_ARM_STATE.exists():
        return {}
    payload: dict[str, str] = {}
    for line in POST_REBOOT_ARM_STATE.read_text(errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def latest_post_reboot_runner_error() -> str | None:
    if not POST_REBOOT_LAUNCH_LOG.exists():
        return None
    matches = re.findall(
        r"overnight_runner error:\s*(.+)",
        POST_REBOOT_LAUNCH_LOG.read_text(errors="replace"),
    )
    if not matches:
        return None
    return matches[-1].strip()


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


def frontier_soak_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_frontier_soak.jsonl"


def fixed_step_same_session_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_frontier_fixed_step_same_session.jsonl"


def fixed_step_rebooted_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_frontier_fixed_step_rebooted.jsonl"


def fixed_step_same_boot_replay_queue_path(context: dict[str, Any]) -> Path:
    return Path(str(context["paths"]["control_root"])) / "queues" / f"{context['tag']}_frontier_fixed_step_same_boot_replay.jsonl"


def fixed_step_same_session_launcher() -> str:
    return str(SCRIPT_DIR / "run_mar10_frontier_fixed_step_same_session.sh")


def fixed_step_rebooted_launcher() -> str:
    return str(SCRIPT_DIR / "run_mar10_frontier_fixed_step_rebooted.sh")


def fixed_step_post_reboot_launcher() -> str:
    return str(SCRIPT_DIR / "run_mar10_fixed_step_post_reboot.sh")


def fixed_step_post_reboot_installer() -> str:
    return str(SCRIPT_DIR / "install_mar10_fixed_step_post_reboot_agent.sh")


def fixed_step_repeatability_launcher() -> str:
    return str(SCRIPT_DIR / "run_mar10_repeatability_fixed_step.sh")


def invalid_reboot_launch_orchestration(
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    active_run_is_interrupted: bool,
    orchestrator_state: dict[str, Any] | None,
    orchestrator_is_interrupted: bool,
    boot_epoch: int | None,
    runner_error: str | None,
) -> bool:
    stage_id = str(active_run.get("stage_id") or "") if active_run else str((orchestrator_state or {}).get("current_stage_id") or "")
    if stage_id != "frontier_fixed_step_rebooted":
        return False
    completed_stages = list((orchestrator_state or {}).get("completed_stages", []) or [])
    if runner_error or completed_stages:
        return False
    started_at = float(
        (active_run or {}).get("started_at")
        or (orchestrator_state or {}).get("started_at")
        or 0.0
    )
    if boot_epoch is not None and started_at and started_at < boot_epoch:
        return True
    if not (active_run_is_interrupted or orchestrator_is_interrupted):
        return False
    attempted = int((active_state or {}).get("attempted", 0) or 0)
    completed = list((active_state or {}).get("completed", []) or [])
    return attempted == 0 and not completed and not completed_stages


def post_reboot_handoff_status(
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    active_run_is_interrupted: bool,
    orchestrator_state: dict[str, Any] | None,
    orchestrator_is_interrupted: bool,
) -> dict[str, Any]:
    log_exists = POST_REBOOT_LAUNCH_LOG.exists()
    boot_epoch = current_boot_epoch()
    arm_state = read_post_reboot_arm_state()
    runner_error = latest_post_reboot_runner_error()
    return {
        "agent_plist_path": str(POST_REBOOT_AGENT_PLIST),
        "agent_plist_exists": POST_REBOOT_AGENT_PLIST.exists(),
        "arm_state_path": str(POST_REBOOT_ARM_STATE),
        "arm_state_exists": POST_REBOOT_ARM_STATE.exists(),
        "arm_state": arm_state,
        "armed_boot_epoch": arm_state.get("ARMED_BOOT_EPOCH"),
        "current_boot_epoch": boot_epoch,
        "launch_log_path": str(POST_REBOOT_LAUNCH_LOG),
        "launch_log_exists": log_exists,
        "launch_log_size_bytes": POST_REBOOT_LAUNCH_LOG.stat().st_size if log_exists else 0,
        "runner_error": runner_error,
        "installer_path": fixed_step_post_reboot_installer(),
        "wrapper_path": str(SCRIPT_DIR / "mar10_fixed_step_post_reboot_once.sh"),
        "invalid_launch_orchestration": invalid_reboot_launch_orchestration(
            active_run,
            active_state,
            active_run_is_interrupted,
            orchestrator_state,
            orchestrator_is_interrupted,
            boot_epoch,
            runner_error,
        ),
    }


def current_repeatability_results(
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if active_run and active_run.get("session_kind") == "repeatability" and active_state:
        return list(active_state.get("completed", []))
    return repeatability_results


def evaluate_weight_decay_confirmation(items: list[dict[str, Any]]) -> dict[str, Any]:
    failure = repeatability_failure_detail(items)
    frontier_items = [
        item for item in items if str(item.get("id") or "").startswith("frontier_repeat_confirmation")
    ]
    weight_decay_items = [
        item for item in items if str(item.get("id") or "").startswith("weight_decay_repeat_022_confirmation")
    ]
    frontier_vals = [float(item["val_bpb"]) for item in frontier_items if item.get("val_bpb") is not None]
    weight_decay_vals = [float(item["val_bpb"]) for item in weight_decay_items if item.get("val_bpb") is not None]
    frontier_mean = sum(frontier_vals) / len(frontier_vals) if frontier_vals else None
    weight_decay_mean = sum(weight_decay_vals) / len(weight_decay_vals) if weight_decay_vals else None
    weight_decay_spread = max(weight_decay_vals) - min(weight_decay_vals) if len(weight_decay_vals) >= 2 else None
    mean_improvement = (
        frontier_mean - weight_decay_mean
        if frontier_mean is not None and weight_decay_mean is not None
        else None
    )
    result: dict[str, Any] = {
        "passed": False,
        "operationally_clean": False,
        "confirmed_lead": False,
        "weight_decay_better": False,
        "frontier_count": len(frontier_vals),
        "weight_decay_count": len(weight_decay_vals),
        "frontier_mean": frontier_mean,
        "weight_decay_mean": weight_decay_mean,
        "weight_decay_spread": weight_decay_spread,
        "mean_improvement": mean_improvement,
        "next_stage": "define_next_narrow_axis",
        "failure_class": failure["failure_class"] if failure else None,
    }
    if failure:
        result["reason"] = failure["reason"]
        return result
    if len(frontier_vals) < 1 or len(weight_decay_vals) < 2:
        result["failure_class"] = "insufficient-clean-repeats"
        result["reason"] = "weight decay confirmation does not yet have enough completed results"
        return result
    result["passed"] = True
    result["operationally_clean"] = True
    result["weight_decay_better"] = bool(
        frontier_mean is not None and weight_decay_mean is not None and weight_decay_mean < frontier_mean
    )
    if mean_improvement is not None and mean_improvement > MATERIAL_WIN_THRESHOLD:
        result["confirmed_lead"] = True
        result["reason"] = (
            "bounded confirmation canary stayed clean and `WEIGHT_DECAY=0.22` remains materially ahead of frontier"
        )
        return result
    if result["weight_decay_better"]:
        result["reason"] = (
            "bounded confirmation canary stayed clean and `WEIGHT_DECAY=0.22` remains ahead of frontier, "
            "but the edge is below the material-win threshold"
        )
        return result
    result["reason"] = "bounded confirmation canary stayed clean but `WEIGHT_DECAY=0.22` no longer beats frontier"
    return result


def _is_clean_fixed_step_repeatability_item(item: dict[str, Any] | None, required_steps: int = 354) -> bool:
    if not item:
        return False
    if item.get("status") == "crash":
        return False
    if item.get("runner_abort_reason"):
        return False
    if item.get("completion_error_phase") or item.get("completion_error_type") or item.get("completion_error_message"):
        return False
    status_class = str(item.get("status_class") or "")
    if status_class in STALL_FAILURE_CLASSES or status_class in COMPLETION_FAILURE_CLASSES:
        return False
    num_steps = item.get("num_steps")
    if num_steps is None or int(num_steps) != required_steps:
        return False
    completion_phase = item.get("completion_phase")
    if completion_phase is not None and completion_phase != "post_summary":
        return False
    return item.get("val_bpb") is not None


def _stable_pair_assessment(
    items_by_id: dict[str, dict[str, Any]],
    baseline_ids: tuple[str, str],
    candidate_ids: tuple[str, str],
) -> dict[str, Any] | None:
    baseline_items = [items_by_id.get(item_id) for item_id in baseline_ids]
    candidate_items = [items_by_id.get(item_id) for item_id in candidate_ids]
    if not all(_is_clean_fixed_step_repeatability_item(item) for item in baseline_items + candidate_items):
        return None
    baseline_vals = [float(item["val_bpb"]) for item in baseline_items]
    candidate_vals = [float(item["val_bpb"]) for item in candidate_items]
    baseline_mean = sum(baseline_vals) / len(baseline_vals)
    candidate_mean = sum(candidate_vals) / len(candidate_vals)
    baseline_spread = max(baseline_vals) - min(baseline_vals)
    candidate_spread = max(candidate_vals) - min(candidate_vals)
    delta = baseline_mean - candidate_mean
    if baseline_spread > REPEATABILITY_SPREAD_THRESHOLD or candidate_spread > REPEATABILITY_SPREAD_THRESHOLD:
        classification = "inconclusive_drift"
    elif delta > MATERIAL_WIN_THRESHOLD:
        classification = "confirmed"
    elif delta > 0.0:
        classification = "promising"
    else:
        classification = "closed"
    return {
        "baseline_mean": baseline_mean,
        "candidate_mean": candidate_mean,
        "baseline_spread": baseline_spread,
        "candidate_spread": candidate_spread,
        "delta": delta,
        "classification": classification,
    }


def _stable_bracket_best_candidate(
    items_by_id: dict[str, dict[str, Any]],
    baseline_ids: tuple[str, str],
    candidate_ids: tuple[str, ...],
) -> dict[str, Any] | None:
    baseline_items = [items_by_id.get(item_id) for item_id in baseline_ids]
    if not all(_is_clean_fixed_step_repeatability_item(item) for item in baseline_items):
        return None
    baseline_vals = [float(item["val_bpb"]) for item in baseline_items]
    baseline_mean = sum(baseline_vals) / len(baseline_vals)
    baseline_spread = max(baseline_vals) - min(baseline_vals)
    if baseline_spread > REPEATABILITY_SPREAD_THRESHOLD:
        return {
            "baseline_mean": baseline_mean,
            "baseline_spread": baseline_spread,
            "best_delta": None,
            "best_id": None,
            "classification": "inconclusive_drift",
        }
    candidates: list[dict[str, Any]] = []
    for item_id in candidate_ids:
        item = items_by_id.get(item_id)
        if not _is_clean_fixed_step_repeatability_item(item):
            continue
        value = float(item["val_bpb"])
        candidates.append({"id": item_id, "val_bpb": value, "delta": baseline_mean - value})
    if not candidates:
        return None
    best = max(candidates, key=lambda item: float(item["delta"]))
    if float(best["delta"]) > MATERIAL_WIN_THRESHOLD:
        classification = "promoted"
    elif float(best["delta"]) > 0.0:
        classification = "promising"
    else:
        classification = "closed"
    return {
        "baseline_mean": baseline_mean,
        "baseline_spread": baseline_spread,
        "best_delta": float(best["delta"]),
        "best_id": str(best["id"]),
        "classification": classification,
    }


def post_confirmation_axis_status(repeatability_results: list[dict[str, Any]]) -> dict[str, Any]:
    items_by_id = {
        str(item.get("id")): item
        for item in repeatability_results
        if item.get("id")
    }
    scalar_0475 = _stable_pair_assessment(
        items_by_id,
        ("candidate_weight_decay_022_fixed_step_repeat_g", "candidate_weight_decay_022_fixed_step_repeat_h"),
        ("scalar_lr_0475_fixed_step_confirmation_c", "scalar_lr_0475_fixed_step_confirmation_d"),
    )
    scalar_048125 = _stable_pair_assessment(
        items_by_id,
        ("candidate_weight_decay_022_fixed_step_repeat_i", "candidate_weight_decay_022_fixed_step_repeat_j"),
        ("scalar_lr_048125_fixed_step_confirmation_c", "scalar_lr_048125_fixed_step_confirmation_d"),
    )
    unembedding = _stable_bracket_best_candidate(
        items_by_id,
        ("candidate_weight_decay_022_fixed_step_repeat_k", "candidate_weight_decay_022_fixed_step_repeat_l"),
        (
            "unembedding_lr_0047_on_weight_decay_022_fixed_step",
            "unembedding_lr_0048_on_weight_decay_022_fixed_step",
        ),
    )
    ridge = _stable_bracket_best_candidate(
        items_by_id,
        ("candidate_weight_decay_022_fixed_step_repeat_m", "candidate_weight_decay_022_fixed_step_repeat_n"),
        (
            "weight_decay_0218_fixed_step",
            "weight_decay_02225_fixed_step",
        ),
    )
    scalar_exhausted = bool(
        scalar_0475
        and scalar_0475.get("classification") in {"promising", "closed"}
        and scalar_048125
        and scalar_048125.get("classification") == "closed"
    )
    unembedding_closed = bool(unembedding and unembedding.get("classification") == "closed")
    ridge_closed = bool(ridge and ridge.get("classification") == "closed")
    return {
        "scalar_0475": scalar_0475,
        "scalar_048125": scalar_048125,
        "unembedding": unembedding,
        "ridge": ridge,
        "scalar_exhausted": scalar_exhausted,
        "unembedding_closed": unembedding_closed,
        "ridge_closed": ridge_closed,
        "all_adjacent_axes_resolved": scalar_exhausted and unembedding_closed and ridge_closed,
    }


def historical_confirmation_stage(repeatability_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    confirmation_items = [
        item
        for item in repeatability_results
        if str(item.get("id") or "").startswith("frontier_repeat_confirmation")
        or str(item.get("id") or "").startswith("weight_decay_repeat_022_confirmation")
    ]
    if not confirmation_items:
        return None
    evaluation = evaluate_weight_decay_confirmation(confirmation_items)
    if not evaluation.get("passed"):
        return None
    return {
        "stage_id": "weight_decay_confirmation",
        "role": "confirmation",
        "passed": bool(evaluation["passed"]),
        "reason": evaluation["reason"],
        "failure_class": evaluation.get("failure_class"),
        "evaluation": evaluation,
        "confirmed_lead": evaluation.get("confirmed_lead"),
        "weight_decay_better": evaluation.get("weight_decay_better"),
        "next_stage": evaluation.get("next_stage"),
    }


def queue_matches(context: dict[str, Any], queue_path: str | None, suffix: str) -> bool:
    if not queue_path:
        return False
    return str(queue_path).endswith(f"{context['tag']}_{suffix}.jsonl")


def finished_active_stage_summary(
    context: dict[str, Any],
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not active_run or not bool(active_run.get("finished")):
        return None
    session_results = current_repeatability_results(active_run, active_state, repeatability_results)
    stage_id = str(active_run.get("stage_id") or "")
    queue_path = str(active_run.get("queue_path") or "")
    if stage_id in {"backend_isolation", "frontier_isolation", "frontier_soak", "frontier_fixed_step_same_session", "frontier_fixed_step_rebooted", "frontier_fixed_step_same_boot_replay"} or queue_matches(context, queue_path, "frontier_isolation") or queue_matches(context, queue_path, "frontier_soak") or queue_matches(context, queue_path, "frontier_fixed_step_same_session") or queue_matches(context, queue_path, "frontier_fixed_step_rebooted") or queue_matches(context, queue_path, "frontier_fixed_step_same_boot_replay"):
        required_repeats = 6 if stage_id == "frontier_soak" or queue_matches(context, queue_path, "frontier_soak") else 2
        evaluation = evaluate_frontier_isolation_gate(
            session_results,
            frontier_anchor_val=float(context["current_best_val"]),
            required_repeats=required_repeats,
        )
        return {
            "stage_id": stage_id or "backend_isolation",
            "role": "backend_isolation",
            "passed": bool(evaluation["passed"]),
            "reason": evaluation["reason"],
            "failure_class": evaluation.get("failure_class"),
            "evaluation": evaluation,
            "runtime_forensics_bundle": active_run.get("runtime_forensics_bundle"),
        }
    if stage_id in {"dedicated_repeatability", "dedicated_repeatability_fixed_step"} or queue_matches(context, queue_path, "repeatability_dedicated_session") or queue_matches(context, queue_path, "repeatability_fixed_step"):
        evaluation = evaluate_repeatability_gate(session_results, frontier_anchor_val=float(context["current_best_val"]))
        return {
            "stage_id": stage_id or "dedicated_repeatability",
            "role": "repeatability",
            "passed": bool(evaluation["passed"]),
            "reason": evaluation["reason"],
            "failure_class": evaluation.get("failure_class"),
            "evaluation": evaluation,
            "recommended_search_stage": evaluation.get("next_stage"),
            "runtime_forensics_bundle": active_run.get("runtime_forensics_bundle"),
        }
    if stage_id == "weight_decay_confirmation" or queue_matches(context, queue_path, "weight_decay_confirmation"):
        evaluation = evaluate_weight_decay_confirmation(session_results)
        return {
            "stage_id": stage_id or "weight_decay_confirmation",
            "role": "confirmation",
            "passed": bool(evaluation["passed"]),
            "reason": evaluation["reason"],
            "failure_class": evaluation.get("failure_class"),
            "evaluation": evaluation,
            "confirmed_lead": evaluation.get("confirmed_lead"),
            "weight_decay_better": evaluation.get("weight_decay_better"),
            "next_stage": evaluation.get("next_stage"),
            "runtime_forensics_bundle": active_run.get("runtime_forensics_bundle"),
        }
    return None


def latest_completed_orchestrator_stage(orchestrator_state: dict[str, Any] | None, role: str) -> dict[str, Any] | None:
    if not orchestrator_state:
        return None
    completed = list(orchestrator_state.get("completed_stages") or [])
    for stage in reversed(completed):
        stage_id = str(stage.get("stage_id") or "")
        if role == "backend_isolation" and stage_id in {"backend_isolation", "frontier_soak", "frontier_fixed_step_same_session", "frontier_fixed_step_rebooted", "frontier_fixed_step_same_boot_replay"}:
            return stage
        if role == "repeatability" and stage_id in {"dedicated_repeatability", "dedicated_repeatability_fixed_step"}:
            return stage
    return None


def environment_status(
    context: dict[str, Any],
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
    orchestrator_state: dict[str, Any] | None,
    active_run_is_interrupted: bool,
    orchestrator_is_interrupted: bool,
    post_reboot_handoff: dict[str, Any],
) -> dict[str, Any]:
    finished_active = finished_active_stage_summary(context, active_run, active_state, repeatability_results)
    latest_backend = latest_completed_orchestrator_stage(orchestrator_state, "backend_isolation")
    latest_repeat = latest_completed_orchestrator_stage(orchestrator_state, "repeatability")
    latest_confirmation = finished_active if finished_active and finished_active["role"] == "confirmation" else None
    if not latest_confirmation:
        latest_confirmation = historical_confirmation_stage(repeatability_results)
    if not latest_backend and finished_active and finished_active["role"] == "backend_isolation":
        latest_backend = finished_active
    if not latest_repeat and finished_active and finished_active["role"] == "repeatability":
        latest_repeat = finished_active
    post_confirmation_axes = post_confirmation_axis_status(repeatability_results)
    state = "untrusted"
    blocked_reason: str | None = None
    next_stage: str | None = None
    bundle_path = None
    runner_error = str(post_reboot_handoff.get("runner_error") or "") or None
    if latest_backend:
        bundle_path = latest_backend.get("runtime_forensics_bundle")
    latest_backend_stage_id = str(latest_backend.get("stage_id") or "") if latest_backend else ""
    if latest_confirmation and latest_backend and latest_backend.get("passed") and latest_repeat and latest_repeat.get("passed"):
        state = "conditionally recovered"
        next_stage = str(latest_confirmation.get("next_stage") or "define_next_narrow_axis")
        if latest_confirmation.get("passed") and latest_confirmation.get("confirmed_lead"):
            if post_confirmation_axes.get("all_adjacent_axes_resolved"):
                blocked_reason = (
                    "bounded canary resolved cleanly; `WEIGHT_DECAY=0.22` is the confirmed lead, "
                    "scalar is exhausted, unembedding is closed, and ridge is closed; no overnight run is recommended "
                    "until the operating review is complete and a materially different axis is deliberately designed"
                )
            else:
                blocked_reason = (
                    "bounded canary resolved cleanly; `WEIGHT_DECAY=0.22` is the confirmed lead; "
                    "define the next narrow axis before reopening broader search"
                )
        elif latest_confirmation.get("passed"):
            blocked_reason = (
                "bounded canary resolved cleanly but did not fully confirm `WEIGHT_DECAY=0.22`; "
                "keep the loop narrow and define the next adjacent axis deliberately"
            )
        else:
            blocked_reason = (
                f"bounded canary was operationally unstable: {latest_confirmation.get('reason')}; "
                "keep broader search closed until stage stability is re-established"
            )
    elif latest_backend and latest_backend.get("passed") and latest_repeat and latest_repeat.get("passed"):
        state = "conditionally recovered"
        next_stage = str(latest_repeat.get("recommended_search_stage") or "day-2 canary")
        blocked_reason = (
            f"next-day canary earned: `{next_stage}`; broad search remains closed until the bounded canary resolves"
        )
    elif post_reboot_handoff.get("invalid_launch_orchestration"):
        state = "untrusted"
        blocked_reason = "rebooted dedicated-session launch failed before any informative attempt; repair the LaunchAgent handoff and rerun after reboot"
        next_stage = "frontier_fixed_step_rebooted"
    elif latest_backend_stage_id == "frontier_soak":
        state = "untrusted"
        blocked_reason = "comparability recovery still requires fixed-step local isolation before repeatability can reopen"
        next_stage = "frontier_fixed_step_same_session"
    elif latest_backend_stage_id == "frontier_fixed_step_same_session":
        state = "untrusted"
        blocked_reason = "rebooted dedicated-session fixed-step isolation is still required before repeatability can reopen"
        next_stage = "frontier_fixed_step_rebooted"
    elif latest_backend_stage_id == "frontier_fixed_step_rebooted":
        if latest_backend and latest_backend.get("passed"):
            state = "conditionally recovered"
            blocked_reason = "fixed-step dedicated repeatability is still required before search can reopen"
            next_stage = "dedicated_repeatability_fixed_step"
        else:
            state = "untrusted"
            blocked_reason = runner_error or str(latest_backend.get("reason"))
            next_stage = "frontier_fixed_step_same_boot_replay"
    elif latest_backend_stage_id == "frontier_fixed_step_same_boot_replay":
        state = "untrusted"
        blocked_reason = runner_error or str(latest_backend.get("reason"))
        next_stage = None
    elif latest_backend and latest_backend.get("passed"):
        state = "conditionally recovered"
        next_stage = "dedicated_repeatability"
        blocked_reason = "dedicated repeatability rerun still required before search can reopen"
    elif latest_backend:
        state = "untrusted"
        blocked_reason = str(latest_backend.get("reason"))
    elif latest_repeat and not latest_repeat.get("passed"):
        state = "untrusted"
        blocked_reason = str(latest_repeat.get("reason"))
    if active_run and not bool(active_run.get("finished")) and not active_run_is_interrupted:
        stage_id = str(active_run.get("stage_id") or "")
        if stage_id in {"dedicated_repeatability", "dedicated_repeatability_fixed_step"} and latest_backend and latest_backend.get("passed"):
            state = "conditionally recovered"
            next_stage = stage_id
            blocked_reason = "fixed-step dedicated repeatability is in progress" if stage_id == "dedicated_repeatability_fixed_step" else "dedicated repeatability is in progress"
        elif stage_id in {"backend_isolation", "frontier_isolation", "frontier_soak", "frontier_fixed_step_same_session", "frontier_fixed_step_rebooted", "frontier_fixed_step_same_boot_replay"}:
            state = "untrusted"
            next_stage = stage_id
            blocked_reason = f"{stage_id} is in progress"
            bundle_path = active_run.get("runtime_forensics_bundle")
    return {
        "trust_state": state,
        "latest_backend_isolation": latest_backend,
        "latest_repeatability_stage": latest_repeat,
        "latest_confirmation_stage": latest_confirmation,
        "post_confirmation_axes": post_confirmation_axes,
        "search_blocked_reason": blocked_reason,
        "next_stage": next_stage,
        "bundle_path": bundle_path,
    }


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


def frontier_soak_decision(context: dict[str, Any], items: list[dict[str, Any]]) -> str:
    evaluation = evaluate_frontier_isolation_gate(
        items,
        frontier_anchor_val=float(context["current_best_val"]),
        required_repeats=6,
    )
    if not evaluation["passed"]:
        return (
            "search blocked; frontier soak confirmed environment drift. "
            f"Next diagnostic stage: `{fixed_step_same_session_launcher()}`"
        )
    return (
        "frontier soak finished with enough evidence to move into comparability recovery. "
        f"Next stage: `{fixed_step_same_session_launcher()}`"
    )


def overnight_recommendation(
    environment: dict[str, Any],
    blockers: list[str],
    active_run: dict[str, Any] | None,
) -> str:
    if blockers:
        return "search blocked"
    if active_run and not bool(active_run.get("finished")):
        return "search blocked"
    latest_confirmation = environment.get("latest_confirmation_stage")
    if latest_confirmation and latest_confirmation.get("passed") and latest_confirmation.get("confirmed_lead"):
        post_confirmation_axes = environment.get("post_confirmation_axes") or {}
        if post_confirmation_axes.get("all_adjacent_axes_resolved"):
            return "hold window"
        return "candidate confirmed"
    if latest_confirmation and latest_confirmation.get("passed"):
        return "candidate still narrow"
    if latest_confirmation:
        return "search blocked"
    latest_repeat = environment.get("latest_repeatability_stage")
    latest_backend = environment.get("latest_backend_isolation")
    if latest_repeat and latest_repeat.get("passed") and latest_backend and latest_backend.get("passed"):
        return "next-day canary earned"
    latest_backend_stage_id = str((environment.get("latest_backend_isolation") or {}).get("stage_id") or "")
    if latest_backend_stage_id in {"frontier_soak", "frontier_fixed_step_same_session", "frontier_fixed_step_same_boot_replay"}:
        return "search blocked"
    if latest_backend_stage_id == "frontier_fixed_step_rebooted" and latest_backend and latest_backend.get("passed"):
        return "repeatability earned"
    if latest_backend_stage_id == "frontier_fixed_step_rebooted":
        return "search blocked"
    if latest_backend and latest_backend.get("passed"):
        return "repeatability earned"
    return "search blocked"


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
    environment: dict[str, Any],
    post_reboot_handoff: dict[str, Any],
) -> str:
    latest_backend = environment.get("latest_backend_isolation")
    latest_repeat = environment.get("latest_repeatability_stage")
    latest_confirmation = environment.get("latest_confirmation_stage")
    post_confirmation_axes = environment.get("post_confirmation_axes") or {}
    runner_error = str(post_reboot_handoff.get("runner_error") or "")
    if blockers:
        return "do not launch autonomous stages until blockers are cleared: " + "; ".join(blockers)
    if post_reboot_handoff.get("invalid_launch_orchestration"):
        return (
            "latest rebooted trust attempt is invalid launch orchestration; recreate the LaunchAgent on disk only with "
            f"`{post_reboot_handoff['installer_path']}`, do not bootstrap it, then reboot and rerun the rebooted fixed-step gate"
        )
    if runner_error and "git worktree must be clean except known artifacts" in runner_error:
        return (
            "execution-baseline preflight failed because tracked files are dirty; restore the execution worktree to a clean tracked state "
            "(notably reset `TRUST_TARGET_STEPS` in the execution baseline `train.py` back to `0`), keep only runner-owned `logs/` and "
            "`state/`, then reinstall the post-reboot LaunchAgent and rerun exactly one rebooted fixed-step trust attempt"
        )
    if orchestrator_is_interrupted and not latest_backend:
        return "previous orchestrator session is interrupted; inspect its state and relaunch through the orchestrator"
    if active_run_is_interrupted and not latest_backend:
        return "previous stage runner is interrupted; inspect its state and relaunch through the orchestrator"
    if latest_confirmation:
        if not latest_confirmation.get("passed"):
            return (
                "bounded confirmation canary was operationally unstable; keep broad search closed and stabilize the stage "
                f"before reopening the loop: {latest_confirmation.get('reason')}"
            )
        if latest_confirmation.get("confirmed_lead"):
            if post_confirmation_axes.get("all_adjacent_axes_resolved"):
                return (
                    "no overnight run today; `WEIGHT_DECAY=0.22` is the confirmed lead, "
                    "scalar is exhausted (`0.475` sub-threshold, `0.48125` closed), "
                    "unembedding is closed, and ridge is closed. Keep broad search closed, "
                    "use the review window to reconstruct `mar10` and `mar24-night`, classify active versus archival branches, "
                    "and reset work tracking in Linear before defining any new research axis."
                )
            return (
                "bounded confirmation canary resolved cleanly; `WEIGHT_DECAY=0.22` is the confirmed lead. "
                "Keep broad search closed and define the next narrow axis around the confirmed candidate."
            )
        if latest_confirmation.get("weight_decay_better"):
            return (
                "bounded confirmation canary resolved cleanly; `WEIGHT_DECAY=0.22` still beats frontier, "
                "but the edge is below the material-win bar. Keep the loop narrow and define one adjacent-axis check."
            )
        return (
            "bounded confirmation canary resolved cleanly, but `WEIGHT_DECAY=0.22` did not stay ahead of frontier. "
            "Keep broad search closed and choose the next axis deliberately."
        )
    if latest_repeat and latest_repeat.get("passed") and latest_backend and latest_backend.get("passed"):
        recommended_stage = latest_repeat.get("recommended_search_stage") or environment.get("next_stage") or "day-2 canary"
        return (
            "next-day canary earned; stop tonight and schedule the next bounded canary on a later run window: "
            f"`{recommended_stage}`"
        )
    if latest_backend and not latest_backend.get("passed") and not (active_run and not bool(active_run.get("finished"))):
        failure_class = str(latest_backend.get("failure_class") or "")
        if failure_class in {"post-train-summary-missing", "post-train-eval-crash"}:
            return f"search blocked; completion-path failed: {latest_backend.get('reason')}"
        if str(latest_backend.get("stage_id") or "") == "frontier_soak":
            return frontier_soak_decision(context, latest_backend.get("completed") or [])
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_same_session":
            return f"search blocked; same-session fixed-step isolation failed: {latest_backend.get('reason')}"
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_rebooted":
            return f"search blocked; rebooted fixed-step isolation failed: {latest_backend.get('reason')}"
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_same_boot_replay":
            return f"search blocked; same-boot replay failed: {latest_backend.get('reason')}"
        if failure_class == "quality-drift" and str(latest_backend.get("stage_id") or "") != "frontier_soak":
            return (
                "backend isolation completed cleanly but drifted; use the overnight window for a frontier-only soak block: "
                f"`{frontier_soak_queue_path(context)}`"
            )
        return f"search blocked; quality-drift or runtime trust failure: {latest_backend.get('reason')}"
    if latest_backend and latest_backend.get("passed") and not latest_repeat and not (active_run and not bool(active_run.get("finished"))):
        if str(latest_backend.get("stage_id") or "") == "frontier_soak":
            return (
                "comparability recovery is next; run the fixed-step same-session isolation block now, "
                f"then the rebooted dedicated-session block: `{fixed_step_same_session_launcher()}` then `{fixed_step_rebooted_launcher()}`"
            )
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_same_session":
            return (
                "same-session fixed-step isolation passed; write the one-shot reboot LaunchAgent to disk with "
                f"`{fixed_step_post_reboot_installer()}`, do not bootstrap it, then reboot into a dedicated session so "
                f"`{fixed_step_post_reboot_launcher()}` runs automatically from launchd"
            )
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_rebooted":
            return f"local fixed-step isolation block passed; run `{fixed_step_repeatability_launcher()}`"
        if str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_same_boot_replay":
            return f"search blocked; same-boot replay completed: {latest_backend.get('reason')}"
        return f"launch the dedicated repeatability rerun `{repeatability_queue_path(context)}`"

    if latest_backend and str(latest_backend.get("stage_id") or "") == "frontier_fixed_step_same_boot_replay":
        return f"search blocked; same-boot replay completed: {latest_backend.get('reason')}"

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
            if "frontier-soak" in active_branch or active_queue.endswith("mar10_frontier_soak.jsonl"):
                return frontier_soak_decision(context, session_results)
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
    frontier_ledger = load_frontier_ledger(control_root)
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
    post_reboot_handoff = post_reboot_handoff_status(
        active_run,
        active_state,
        active_run_is_interrupted,
        orchestrator_state,
        orchestrator_is_interrupted,
    )
    environment = environment_status(
        context,
        active_run,
        active_state,
        repeatability_results,
        orchestrator_state,
        active_run_is_interrupted,
        orchestrator_is_interrupted,
        post_reboot_handoff,
    )
    if (
        frontier_ledger
        and (environment.get("latest_confirmation_stage") or {}).get("confirmed_lead")
        and frontier_ledger.get("frontier_commit")
        and frontier_ledger.get("frontier_val_bpb") is not None
    ):
        frontier["current_best_commit"] = str(frontier_ledger["frontier_commit"])[:7]
        frontier["current_best_val"] = round(float(frontier_ledger["frontier_val_bpb"]), 6)
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
        "post_reboot_handoff": post_reboot_handoff,
        "default_plan": default_plan,
        "preflight_blockers": blockers,
        "live_stall_warning": live_warning,
        "environment": environment,
        "overnight_recommendation": overnight_recommendation(environment, blockers, active_run),
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
            environment,
            post_reboot_handoff,
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
    environment = payload["environment"]
    lines = [
        f"# Session Status: `{frontier['branch']}`",
        "",
        "## Canonical Frontier",
        "",
        f"- best commit: `{frontier['current_best_commit']}`",
        f"- best `val_bpb`: `{frontier['current_best_val']:.6f}`",
        f"- execution ready: `{str(frontier['execution_ready']).lower()}`",
        "",
        "## Environment Trust",
        "",
        f"- trust state: `{environment['trust_state']}`",
        f"- overnight recommendation: `{payload['overnight_recommendation']}`",
        f"- next stage: `{environment.get('next_stage')}`",
        f"- search blocked reason: `{environment.get('search_blocked_reason')}`",
        f"- latest backend-isolation bundle: `{environment.get('bundle_path')}`",
        "",
        "## Active Run",
        "",
    ]
    latest_backend = environment.get("latest_backend_isolation")
    latest_repeat = environment.get("latest_repeatability_stage")
    if latest_backend:
        lines.insert(12, f"- latest backend-isolation failure class: `{latest_backend.get('failure_class')}`")
    if latest_repeat:
        lines.insert(13 if latest_backend else 12, f"- latest repeatability failure class: `{latest_repeat.get('failure_class')}`")
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
    latest_confirmation = environment.get("latest_confirmation_stage")
    post_confirmation_axes = environment.get("post_confirmation_axes") or {}
    if not orchestrator_state:
        lines.append("- none")
    else:
        orchestrator_next_action = orchestrator_state.get("next_action")
        if latest_confirmation and latest_confirmation.get("confirmed_lead") and post_confirmation_axes.get("all_adjacent_axes_resolved"):
            orchestrator_next_action = (
                "superseded by post-ridge closure; no overnight run today. "
                "Use the review window to reconstruct mar10 plus mar24-night and reset work tracking before selecting a materially different axis."
            )
        lines.append(f"- plan id: `{orchestrator_state.get('plan_id')}`")
        lines.append(f"- finished: `{str(bool(orchestrator_state.get('finished'))).lower()}`")
        lines.append(f"- current stage: `{orchestrator_state.get('current_stage_id')}`")
        lines.append(f"- next action: `{orchestrator_next_action}`")
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

    lines.extend(["", "## Post-Reboot Handoff", ""])
    handoff = payload["post_reboot_handoff"]
    lines.append(f"- installer: `{handoff['installer_path']}`")
    lines.append(f"- agent plist: `{handoff['agent_plist_path']}` exists=`{str(bool(handoff['agent_plist_exists'])).lower()}`")
    lines.append(f"- arm state: `{handoff['arm_state_path']}` exists=`{str(bool(handoff['arm_state_exists'])).lower()}` armed_boot_epoch=`{handoff['armed_boot_epoch']}` current_boot_epoch=`{handoff['current_boot_epoch']}`")
    lines.append(f"- launch log: `{handoff['launch_log_path']}` exists=`{str(bool(handoff['launch_log_exists'])).lower()}` size_bytes=`{handoff['launch_log_size_bytes']}`")
    lines.append(f"- latest runner error: `{handoff.get('runner_error')}`")
    lines.append(f"- invalid launch orchestration: `{str(bool(handoff['invalid_launch_orchestration'])).lower()}`")

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
