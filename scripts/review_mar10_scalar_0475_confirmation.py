#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from autoresearch_lib import (
    COMPLETION_FAILURE_CLASSES,
    MATERIAL_WIN_THRESHOLD,
    MIN_CLEAN_NUM_STEPS,
    REPEATABILITY_SPREAD_THRESHOLD,
    STALL_FAILURE_CLASSES,
    load_json,
)


DEFAULT_EXECUTION_ROOT = Path(
    "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation"
)
DEFAULT_STATE_PATH = DEFAULT_EXECUTION_ROOT / "state" / "overnight_execution-weight-decay-022-scalar-confirmation.json"
DEFAULT_REPORT_PATH = DEFAULT_EXECUTION_ROOT / "reports" / "overnight_execution-weight-decay-022-scalar-confirmation.md"
DEFAULT_LOG_ROOT = (
    DEFAULT_EXECUTION_ROOT / "logs" / "overnight" / "execution-weight-decay-022-scalar-confirmation"
)
BASELINE_IDS = (
    "candidate_weight_decay_022_repeat_g",
    "candidate_weight_decay_022_repeat_h",
)
CANDIDATE_IDS = (
    "scalar_lr_0475_confirmation_c",
    "scalar_lr_0475_confirmation_d",
)
EXPECTED_IDS = (BASELINE_IDS[0], CANDIDATE_IDS[0], CANDIDATE_IDS[1], BASELINE_IDS[1])


class ReviewError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review the mar10 scalar 0.475 confirmation run.")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--log-root", default=str(DEFAULT_LOG_ROOT))
    parser.add_argument("--format", choices=("md", "json"), default="md")
    return parser.parse_args()


def _require_item(completed_by_id: dict[str, dict[str, Any]], item_id: str) -> dict[str, Any]:
    if item_id not in completed_by_id:
        raise ReviewError(f"missing completed entry `{item_id}`")
    return completed_by_id[item_id]


def _is_clean(item: dict[str, Any]) -> tuple[bool, str | None]:
    if item.get("status") == "crash":
        return False, "crash"
    if item.get("runner_abort_reason"):
        return False, "runner-abort"
    if item.get("completion_error_phase") or item.get("completion_error_type") or item.get("completion_error_message"):
        return False, "completion-error"
    status_class = str(item.get("status_class") or "")
    if status_class in STALL_FAILURE_CLASSES:
        return False, status_class
    if status_class in COMPLETION_FAILURE_CLASSES:
        return False, status_class
    num_steps = item.get("num_steps")
    if num_steps is not None and int(num_steps) < MIN_CLEAN_NUM_STEPS:
        return False, "truncated-run"
    if item.get("completion_phase") != "post_summary":
        return False, f"incomplete-completion:{item.get('completion_phase')}"
    return True, None


def _absolute_log_path(item: dict[str, Any], log_root: Path) -> Path | None:
    value = item.get("log_path")
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return log_root.parents[2] / path


def evaluate_scalar_0475_confirmation(
    state: dict[str, Any],
    report_path: Path,
    log_root: Path,
) -> dict[str, Any]:
    if not bool(state.get("finished")):
        raise ReviewError("run is not finished yet")
    attempted = int(state.get("attempted", 0))
    stopped_reason = str(state.get("stopped_reason") or "")
    completed = list(state.get("completed") or [])
    completed_by_id = {str(item.get("id")): item for item in completed}
    missing_ids = [item_id for item_id in EXPECTED_IDS if item_id not in completed_by_id]
    order_ids = [str(item.get("id")) for item in completed if item.get("id")]
    order_matches = order_ids[: len(EXPECTED_IDS)] == list(EXPECTED_IDS)

    artifacts = {
        "state": str(Path(str(state.get("state_path") or DEFAULT_STATE_PATH)).resolve()),
        "report": str(report_path.resolve()),
        "log_root": str(log_root.resolve()),
        "logs": {
            item_id: str(_absolute_log_path(completed_by_id[item_id], log_root).resolve())
            for item_id in EXPECTED_IDS
            if item_id in completed_by_id and _absolute_log_path(completed_by_id[item_id], log_root) is not None
        },
    }

    operational_issues: list[str] = []
    if attempted != len(EXPECTED_IDS):
        operational_issues.append(f"attempted={attempted} expected={len(EXPECTED_IDS)}")
    if stopped_reason not in {"queue exhausted", "max_experiments reached (4)"}:
        operational_issues.append(f"unexpected stop reason: {stopped_reason}")
    if missing_ids:
        operational_issues.append(f"missing completed ids: {', '.join(missing_ids)}")
    if not order_matches:
        operational_issues.append("completed item order does not match expected confirmation order")

    item_details: list[dict[str, Any]] = []
    baseline_values: dict[str, float] = {}
    candidate_values: dict[str, float] = {}

    for item_id in EXPECTED_IDS:
        item = _require_item(completed_by_id, item_id)
        clean, clean_failure = _is_clean(item)
        detail = {
            "id": item_id,
            "status": item.get("status"),
            "val_bpb": item.get("val_bpb"),
            "num_steps": item.get("num_steps"),
            "status_class": item.get("status_class"),
            "completion_phase": item.get("completion_phase"),
            "reason": item.get("reason"),
            "training_seconds": item.get("training_seconds"),
            "eval_seconds": item.get("eval_seconds"),
            "total_seconds": item.get("total_seconds"),
            "max_step_dt_ms": item.get("max_step_dt_ms"),
            "last_step_dt_ms": item.get("last_step_dt_ms"),
            "clean": clean,
            "clean_failure": clean_failure,
            "log_path": artifacts["logs"].get(item_id),
        }
        item_details.append(detail)
        if not clean:
            operational_issues.append(f"{item_id} failed integrity: {clean_failure}")
        value = item.get("val_bpb")
        if value is not None and item_id in BASELINE_IDS:
            baseline_values[item_id] = float(value)
        if value is not None and item_id in CANDIDATE_IDS:
            candidate_values[item_id] = float(value)

    classification = "stage_instability" if operational_issues else None
    baseline_mean = None
    baseline_spread = None
    candidate_mean = None
    candidate_spread = None
    delta = None
    baseline_verdict = "not evaluated"
    candidate_verdict = "not evaluated"
    next_day_action = "none"

    if classification is None:
        missing_baselines = [item_id for item_id in BASELINE_IDS if item_id not in baseline_values]
        if missing_baselines:
            classification = "stage_instability"
            baseline_verdict = f"missing baseline values: {', '.join(missing_baselines)}"
        else:
            baseline_mean = (baseline_values[BASELINE_IDS[0]] + baseline_values[BASELINE_IDS[1]]) / 2.0
            baseline_spread = abs(baseline_values[BASELINE_IDS[0]] - baseline_values[BASELINE_IDS[1]])
            if baseline_spread > REPEATABILITY_SPREAD_THRESHOLD:
                classification = "inconclusive_drift"
                baseline_verdict = (
                    f"baseline spread {baseline_spread:.6f} exceeded {REPEATABILITY_SPREAD_THRESHOLD:.6f}"
                )
            else:
                baseline_verdict = (
                    f"baseline bracket is stable: mean={baseline_mean:.6f}, spread={baseline_spread:.6f}"
                )

    if classification is None:
        missing_candidates = [item_id for item_id in CANDIDATE_IDS if item_id not in candidate_values]
        if missing_candidates:
            classification = "stage_instability"
            candidate_verdict = f"missing candidate values: {', '.join(missing_candidates)}"
        else:
            candidate_mean = (candidate_values[CANDIDATE_IDS[0]] + candidate_values[CANDIDATE_IDS[1]]) / 2.0
            candidate_spread = abs(candidate_values[CANDIDATE_IDS[0]] - candidate_values[CANDIDATE_IDS[1]])
            if candidate_spread > REPEATABILITY_SPREAD_THRESHOLD:
                classification = "inconclusive_drift"
                candidate_verdict = (
                    f"candidate spread {candidate_spread:.6f} exceeded {REPEATABILITY_SPREAD_THRESHOLD:.6f}"
                )
            else:
                candidate_verdict = (
                    f"candidate repeats are stable: mean={candidate_mean:.6f}, spread={candidate_spread:.6f}"
                )

    if baseline_mean is not None and candidate_mean is not None:
        delta = baseline_mean - candidate_mean

    if classification is None and delta is not None:
        if delta > MATERIAL_WIN_THRESHOLD:
            classification = "scalar_confirmed"
            next_day_action = "confirm `SCALAR_LR=0.475` as the new lead on top of `WEIGHT_DECAY=0.22`"
        elif delta > 0.0:
            classification = "scalar_promising"
            next_day_action = (
                "keep `SCALAR_LR=0.475` as promising but not confirmed; schedule one bounded follow-up confirmation"
            )
        else:
            classification = "scalar_closed"
            next_day_action = "close scalar and retain plain `WEIGHT_DECAY=0.22` as the lead"

    operational_verdict = "pass" if not operational_issues else "fail"
    return {
        "classification": classification,
        "operational_verdict": operational_verdict,
        "operational_issues": operational_issues,
        "baseline_verdict": baseline_verdict,
        "candidate_verdict": candidate_verdict,
        "baseline_g": baseline_values.get(BASELINE_IDS[0]),
        "baseline_h": baseline_values.get(BASELINE_IDS[1]),
        "baseline_mean": baseline_mean,
        "baseline_spread": baseline_spread,
        "candidate_c": candidate_values.get(CANDIDATE_IDS[0]),
        "candidate_d": candidate_values.get(CANDIDATE_IDS[1]),
        "candidate_mean": candidate_mean,
        "candidate_spread": candidate_spread,
        "delta": delta,
        "next_day_action": next_day_action,
        "artifacts": artifacts,
        "item_details": item_details,
        "attempted": attempted,
        "stopped_reason": stopped_reason,
        "expected_ids": list(EXPECTED_IDS),
    }


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# mar10 Scalar 0.475 Confirmation Review",
        "",
        "## Artifacts",
        "",
        f"- state: `{review['artifacts']['state']}`",
        f"- report: `{review['artifacts']['report']}`",
        f"- log root: `{review['artifacts']['log_root']}`",
        "",
        "## Operational Verdict",
        "",
        f"- verdict: `{review['operational_verdict']}`",
        f"- attempted: `{review['attempted']}`",
        f"- stopped because: `{review['stopped_reason']}`",
    ]
    if review["operational_issues"]:
        lines.append(f"- issues: `{'; '.join(review['operational_issues'])}`")
    else:
        lines.append("- issues: `none`")

    lines.extend(
        [
            "",
            "## Baseline Bracket Verdict",
            "",
            f"- baseline `g`: `{format_float(review['baseline_g'])}`",
            f"- baseline `h`: `{format_float(review['baseline_h'])}`",
            f"- `baseline_mean`: `{format_float(review['baseline_mean'])}`",
            f"- `baseline_spread`: `{format_float(review['baseline_spread'])}`",
            f"- verdict: `{review['baseline_verdict']}`",
            "",
            "## Candidate Repeatability Verdict",
            "",
            f"- candidate `c`: `{format_float(review['candidate_c'])}`",
            f"- candidate `d`: `{format_float(review['candidate_d'])}`",
            f"- `candidate_mean`: `{format_float(review['candidate_mean'])}`",
            f"- `candidate_spread`: `{format_float(review['candidate_spread'])}`",
            f"- `delta`: `{format_float(review['delta'])}`",
            f"- verdict: `{review['candidate_verdict']}`",
            "",
            "## Final Classification",
            "",
            f"- classification: `{review['classification']}`",
            "",
            "## Single Next-Day Action",
            "",
            f"- {review['next_day_action']}",
            "",
            "## Per-Item Integrity",
            "",
        ]
    )
    for item in review["item_details"]:
        lines.append(
            f"- `{item['id']}` `status={item['status']}` `val_bpb={format_float(item['val_bpb'])}` "
            f"`num_steps={item.get('num_steps')}` `status_class={item.get('status_class')}` "
            f"`completion_phase={item.get('completion_phase')}` `training={format_float(item.get('training_seconds'))}` "
            f"`eval={format_float(item.get('eval_seconds'))}` `total={format_float(item.get('total_seconds'))}` "
            f"`max_dt_ms={item.get('max_step_dt_ms')}` `last_dt_ms={item.get('last_step_dt_ms')}` "
            f"`clean={str(item['clean']).lower()}`"
        )
        if item.get("log_path"):
            lines.append(f"  log: `{item['log_path']}`")
        if item.get("reason"):
            lines.append(f"  reason: `{item['reason']}`")
    return "\n".join(lines) + "\n"


def format_float(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.6f}"


def main() -> None:
    args = parse_args()
    state_path = Path(args.state).resolve()
    report_path = Path(args.report).resolve()
    log_root = Path(args.log_root).resolve()
    state = load_json(state_path)
    if not state:
        raise ReviewError(f"state file not found: {state_path}")
    review = evaluate_scalar_0475_confirmation(state, report_path, log_root)
    if args.format == "json":
        print(json.dumps(review, indent=2, sort_keys=True))
        return
    print(render_markdown(review), end="")


if __name__ == "__main__":
    main()
