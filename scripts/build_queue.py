#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from autoresearch_lib import (
    DEFAULT_CONTROL_ROOT,
    DEFAULT_TARGET_ROOT,
    QueueItem,
    artifact_paths,
    collect_frontier_context,
    existing_queue_metadata,
    make_queue_item,
    queue_item_to_dict,
)


FALLBACK_TEMPLATES: dict[str, list[QueueItem]] = {
    "optimizer-micro": [
        make_queue_item("ADAM_BETAS", "(0.8, 0.96)", "change adam betas to (0.8, 0.96)"),
        make_queue_item("ADAM_BETAS", "(0.775, 0.95)", "change adam betas to (0.775, 0.95)"),
        make_queue_item("WARMDOWN_RATIO", "0.52", "lengthen warmdown ratio to 0.52"),
        make_queue_item("WARMDOWN_RATIO", "0.48", "shorten warmdown ratio to 0.48"),
        make_queue_item("WARMUP_RATIO", "0.001", "add warmup ratio of 0.001"),
        make_queue_item("WARMUP_RATIO", "0.0025", "add warmup ratio of 0.0025"),
    ],
    "cadence": [
        make_queue_item("DEVICE_BATCH_SIZE", "4", "reduce device batch size to 4"),
        make_queue_item("DEVICE_BATCH_SIZE", "2", "reduce device batch size to 2"),
    ],
    "stability": [
        make_queue_item("WEIGHT_DECAY", "0.22", "raise weight decay to 0.22"),
        make_queue_item("WEIGHT_DECAY", "0.18", "lower weight decay to 0.18"),
        make_queue_item("SCALAR_LR", "0.475", "lower scalar lr to 0.475"),
    ],
    "weight-decay-ridge": [
        make_queue_item("WEIGHT_DECAY", "0.225", "raise weight decay to 0.225"),
        make_queue_item("WEIGHT_DECAY", "0.23", "raise weight decay to 0.23"),
        make_queue_item("WEIGHT_DECAY", "0.215", "raise weight decay to 0.215"),
        make_queue_item("WEIGHT_DECAY", "0.235", "raise weight decay to 0.235"),
        make_queue_item("SCALAR_LR", "0.4875", "lower scalar lr to 0.4875"),
        make_queue_item("SCALAR_LR", "0.4625", "lower scalar lr to 0.4625"),
    ],
    "scalar-first": [
        make_queue_item("SCALAR_LR", "0.4875", "lower scalar lr to 0.4875"),
        make_queue_item("SCALAR_LR", "0.48125", "lower scalar lr to 0.48125"),
        make_queue_item("SCALAR_LR", "0.475", "lower scalar lr to 0.475"),
        make_queue_item("SCALAR_LR", "0.46875", "lower scalar lr to 0.46875"),
    ],
    "unembedding-followup": [
        make_queue_item("UNEMBEDDING_LR", "0.0047", "lower unembedding lr to 0.0047"),
        make_queue_item("UNEMBEDDING_LR", "0.0048", "raise unembedding lr to 0.0048"),
    ],
}


def select_candidates(context: dict[str, object], band: str) -> list[dict[str, object]]:
    unresolved = context["fresh_unresolved_queue"]
    if band == "optimizer-micro":
        return list(unresolved)
    group_keys = {
        "cadence": {"TOTAL_BATCH_SIZE", "DEVICE_BATCH_SIZE"},
        "stability": {"WEIGHT_DECAY", "SCALAR_LR", "WARMDOWN_RATIO", "WARMUP_RATIO", "FINAL_LR_FRAC"},
        "weight-decay-ridge": {"WEIGHT_DECAY", "SCALAR_LR"},
        "scalar-first": {"SCALAR_LR"},
        "unembedding-followup": {"UNEMBEDDING_LR"},
    }[band]
    return [
        item
        for item in unresolved
        if any(name in group_keys for name in dict(item.get("assignments", {})).keys())
    ]


def build_queue(
    target_root: Path,
    branch: str,
    band: str,
    max_items: int,
    control_root: Path | None,
) -> list[dict[str, object]]:
    context = collect_frontier_context(target_root, branch, control_root=control_root)
    paths = artifact_paths(target_root, branch, control_root=control_root, tag=context["tag"])
    existing_result_descriptions = {row.description for row in context["rows"]}
    existing_ids, existing_queue_descriptions = existing_queue_metadata(
        context["control_state"],
        queue_path=Path(paths["control_queue"]),
        gated_results=context["gated_results"],
    )
    selected: list[dict[str, object]] = []
    seen_descriptions: set[str] = set()
    seen_ids: set[str] = set()

    for item in select_candidates(context, band):
        description = str(item["description"])
        item_id = str(item["id"])
        if description in existing_result_descriptions or description in seen_descriptions:
            continue
        if item_id in seen_ids:
            continue
        selected.append(queue_item_to_dict(item))
        seen_descriptions.add(description)
        seen_ids.add(item_id)
        if len(selected) >= max_items:
            return selected

    for template in FALLBACK_TEMPLATES[band]:
        item = queue_item_to_dict(template)
        description = item["description"]
        item_id = item["id"]
        if description in existing_result_descriptions or description in existing_queue_descriptions or description in seen_descriptions:
            continue
        if item_id in existing_ids or item_id in seen_ids:
            continue
        selected.append(item)
        seen_descriptions.add(description)
        seen_ids.add(item_id)
        if len(selected) >= max_items:
            break
    return selected


def render_markdown(branch: str, band: str, queue: list[dict[str, object]]) -> str:
    lines = [
        f"# Planned Queue: `{branch}`",
        "",
        f"- band: `{band}`",
        f"- items: `{len(queue)}`",
        "",
    ]
    if not queue:
        lines.append("- no fresh queue items were produced after dedupe")
        return "\n".join(lines) + "\n"
    for item in queue:
        lines.append(f"- `{item['id']}` {item['description']}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a safe next experiment queue.")
    parser.add_argument("--branch", required=True, help="Branch to inspect, e.g. autoresearch/mar10")
    parser.add_argument(
        "--band",
        choices=("optimizer-micro", "cadence", "stability", "weight-decay-ridge", "scalar-first", "unembedding-followup"),
        default="optimizer-micro",
    )
    parser.add_argument("--max-items", type=int, default=6)
    parser.add_argument("--out", help="Optional JSONL output path")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT))
    parser.add_argument("--control-root", default=str(DEFAULT_CONTROL_ROOT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    control_root = Path(args.control_root).resolve()
    queue = build_queue(target_root, args.branch, args.band, args.max_items, control_root)
    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as handle:
            for item in queue:
                handle.write(json.dumps(item, sort_keys=True) + "\n")
    if args.format == "json":
        print(json.dumps(queue, indent=2, sort_keys=True))
        return
    print(render_markdown(args.branch, args.band, queue), end="")


if __name__ == "__main__":
    main()
