#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_state(path: Path) -> dict:
    return json.loads(path.read_text())


def load_report(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text()


def extract_frontier_repeat_rows(results_path: Path, state: dict) -> list[str]:
    rows: list[str] = []
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            if "frontier overnight soak" in line:
                rows.append(line)
    if rows:
        return rows[-8:]

    completed_rows: list[str] = []
    for item in state.get("completed", []):
        if "frontier overnight soak" not in str(item.get("description", "")):
            continue
        val = item.get("val_bpb")
        val_str = "n/a" if val is None else f"{float(val):.6f}"
        completed_rows.append(
            f"{item.get('commit')} {val_str} {item.get('status')} {item.get('description')}"
        )
    return completed_rows[-8:]


def extract_top_winners(report_text: str | None, state: dict) -> list[str]:
    if report_text:
        lines = report_text.splitlines()
        winners: list[str] = []
        in_section = False
        for line in lines:
            if line.strip() == "## Top Winning Changes":
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.startswith("- "):
                winners.append(line)
        if winners:
            return winners

    winners = []
    for item in state.get("completed", []):
        if item.get("status") != "keep":
            continue
        winners.append(
            f"- `{item.get('id')}` `{float(item.get('val_bpb')):.6f}` {item.get('description')}"
        )
    return winners


def extract_latest_completed(state: dict, limit: int = 8) -> list[str]:
    rows: list[str] = []
    for item in state.get("completed", [])[-limit:]:
        val = item.get("val_bpb")
        val_str = "n/a" if val is None else f"{float(val):.6f}"
        rows.append(
            f"- {item.get('id')} | {item.get('status')} | {val_str} | {item.get('description')}"
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--results-path", required=True)
    parser.add_argument("--live-target", type=float, required=True)
    args = parser.parse_args()

    state_path = Path(args.state_path)
    state = load_state(state_path)
    report_path = Path(state["report_path"])
    report_text = load_report(report_path)
    frontier_rows = extract_frontier_repeat_rows(Path(args.results_path), state)
    winners = extract_top_winners(report_text, state)
    latest_completed = extract_latest_completed(state)

    print("Overnight Summary")
    print(f"- phase: {state.get('phase')}")
    print(f"- finished: {state.get('finished')}")
    print(f"- stopped_reason: {state.get('stopped_reason')}")
    print(f"- attempted: {state.get('attempted')}")
    print(f"- keeps: {state.get('keep_count')}")
    print(f"- discards: {state.get('discard_count')}")
    print(f"- crashes: {state.get('crash_count')}")
    print(f"- best_commit: {state.get('current_best_commit')}")
    print(f"- best_val_bpb: {state.get('current_best_val'):.6f}")
    print(f"- beat_live_target: {state.get('current_best_val') < args.live_target}")
    print()

    print("Frontier Repeat Rows")
    if frontier_rows:
        for row in frontier_rows:
            print(f"- {row}")
    else:
        print("- none found")
    print()

    print("Winning Families")
    if winners:
        for winner in winners:
            print(winner)
    else:
        print("- none")
    print()

    print("Recent Completed Runs")
    if latest_completed:
        for row in latest_completed:
            print(row)
    else:
        print("- none")
    print()

    print("Next-Step Rule")
    if state.get("crash_count", 0) > 0 and state.get("keep_count", 0) == 0:
        print("- overnight was crash-heavy without offsetting wins; re-baseline before new broad search")
    elif state.get("current_best_val", float("inf")) < args.live_target:
        print("- adopt the best overnight commit as the new live frontier and queue a confirming daytime repeat")
    else:
        print("- preserve the current frontier and choose the next daytime queue from the cleanest overnight signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
