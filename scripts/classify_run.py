#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoresearch_lib import classify_log, load_json


def render_markdown(log_path: Path, payload: dict[str, object]) -> str:
    lines = [
        f"# Run Classification: `{log_path.name}`",
        "",
        f"- `status_class`: `{payload['status_class']}`",
        f"- `informative`: `{str(payload['informative']).lower()}`",
        f"- `issue_scope`: `{payload['issue_scope']}`",
        f"- `suggested_action`: `{payload['suggested_action']}`",
        f"- `reason`: {payload['reason']}",
    ]
    if payload.get("val_bpb") is not None:
        lines.append(f"- `val_bpb`: `{payload['val_bpb']:.6f}`")
    if payload.get("training_seconds") is not None:
        lines.append(f"- `training_seconds`: `{payload['training_seconds']:.1f}`")
    if payload.get("total_seconds") is not None:
        lines.append(f"- `total_seconds`: `{payload['total_seconds']:.1f}`")
    if payload.get("memory_gb") is not None:
        lines.append(f"- `memory_gb`: `{payload['memory_gb']:.1f}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify an autoresearch run log.")
    parser.add_argument("--log", required=True, help="Path to the run log")
    parser.add_argument("--control-state", help="Optional control state JSON for repeated-timeout context")
    parser.add_argument("--format", choices=("json", "md"), default="json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_path = Path(args.log).resolve()
    control_state = load_json(Path(args.control_state).resolve()) if args.control_state else None
    payload = classify_log(log_path.read_text(errors="replace"), control_state=control_state)
    payload["log"] = str(log_path)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(render_markdown(log_path, payload), end="")


if __name__ == "__main__":
    main()
