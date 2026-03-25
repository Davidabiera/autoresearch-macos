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
    load_json,
    parse_repeatability_results,
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


def informative_results(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in completed
        if item.get("status") in {"keep", "discard"} and item.get("val_bpb") is not None
    ]


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


def recommended_next_action(
    context: dict[str, Any],
    active_run: dict[str, Any] | None,
    active_state: dict[str, Any] | None,
    repeatability_results: list[dict[str, Any]],
    early_stop_floor: float,
    early_stop_after: int,
) -> str:
    signal = early_stop_signal(active_state, early_stop_floor, early_stop_after)
    if signal:
        return str(signal["message"])

    if active_run and bool(active_run.get("finished")):
        if repeatability_results:
            return "review repeatability block and decide whether weight decay closes or reopens"
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
    active_run, active_state = load_active_state(paths)
    repeatability_results = parse_repeatability_results(Path(paths["repeatability_results"]))
    exploration_recent = context["gated_results"][-5:]
    repeatability_recent = repeatability_results[-5:]
    best_axis = best_nonkeep_by_axis(context["gated_results"])
    return {
        "frontier": frontier,
        "active_run": active_run,
        "active_state": active_state,
        "last_exploration_results": exploration_recent,
        "last_repeatability_results": repeatability_recent,
        "best_gated_nonkeep_by_axis": best_axis,
        "recommended_next_action": recommended_next_action(
            context,
            active_run,
            active_state,
            repeatability_results,
            early_stop_floor,
            early_stop_after,
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
        if active_state:
            lines.append(f"- attempted: `{active_state.get('attempted', 0)}`")
            lines.append(f"- active experiment: `{active_state.get('active_experiment_id')}`")
        signal = early_stop_signal(active_state, early_stop_floor, early_stop_after)
        if signal:
            lines.append(f"- governance: `{signal['message']}`")

    lines.extend(["", "## Recent Exploration Results", ""])
    lines.extend(render_result_lines(payload["last_exploration_results"]))
    lines.extend(["", "## Recent Repeatability Results", ""])
    lines.extend(render_result_lines(payload["last_repeatability_results"]))
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
