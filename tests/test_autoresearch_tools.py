from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock
import subprocess


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
WORKSPACE_ROOT = Path("/Users/davidabiera/Projects/team/autoresearch-macos")
CONTROL_ROOT = WORKSPACE_ROOT / "worktrees" / "control" / "control"

from autoresearch_lib import classify_log, default_plan_path, evaluate_frontier_isolation_gate, evaluate_repeatability_gate  # noqa: E402
from build_queue import build_queue  # noqa: E402
from frontier_status import build_payload  # noqa: E402
from overnight_runner import terminate_process_group  # noqa: E402
from reconcile_session import build_output  # noqa: E402
from session_orchestrator import next_stage_from_summary, plan_preflight_blockers  # noqa: E402
from session_status import (  # noqa: E402
    build_payload as build_session_payload,
    frontier_isolation_decision,
    repeatability_branching_decision,
)


class AutoresearchToolTests(unittest.TestCase):
    def test_terminate_process_group_falls_back_to_direct_kill(self) -> None:
        class DummyProc:
            pid = 123

            def __init__(self) -> None:
                self.terminate_called = 0
                self.kill_called = 0
                self.wait_calls = 0

            def poll(self) -> None:
                return None

            def terminate(self) -> None:
                self.terminate_called += 1

            def kill(self) -> None:
                self.kill_called += 1

            def wait(self, timeout: float | None = None) -> None:
                self.wait_calls += 1
                if self.wait_calls == 1:
                    raise subprocess.TimeoutExpired(cmd="dummy", timeout=timeout)

        dummy = DummyProc()
        with mock.patch("overnight_runner.os.killpg", side_effect=PermissionError()):
            terminate_process_group(dummy)
        self.assertEqual(dummy.terminate_called, 1)
        self.assertEqual(dummy.kill_called, 1)

    def test_frontier_status_reports_canonical_best_and_current_handoff(self) -> None:
        payload = build_payload(WORKSPACE_ROOT, "autoresearch/mar10", CONTROL_ROOT)
        self.assertEqual(payload["current_best_commit"], "5b486fb")
        self.assertAlmostEqual(payload["current_best_val"], 1.386688, places=6)
        self.assertTrue(str(payload["artifacts"]["results"]).endswith("results_mar10.tsv"))
        self.assertGreaterEqual(payload["gated_result_count"], 6)
        self.assertIsNone(payload["recommended_next_candidate"])
        self.assertFalse(any(flag["artifact"] == "handoff" for flag in payload["coherence_flags"]))

    def test_timeout_only_log_classifies_as_startup_hang(self) -> None:
        payload = classify_log("RUNNER_TIMEOUT: exceeded 600 seconds\n", control_state=None)
        self.assertEqual(payload["status_class"], "startup-hang")
        self.assertFalse(payload["informative"])

    def test_completed_long_log_is_not_blind_crash(self) -> None:
        log_path = CONTROL_ROOT / "logs" / "mar10" / "weight_decay_022.log"
        payload = classify_log(log_path.read_text(errors="replace"))
        self.assertTrue(payload["informative"])
        self.assertIn(payload["status_class"], {"completed", "post-train-overrun"})

    def test_late_timeout_log_classifies_as_late_timeout(self) -> None:
        payload = classify_log(
            "\rstep 00285 (95.9%) | loss: 3.985036 | lrm: 0.13 | dt: 207736ms | tok/sec: 157 | "
            "mfu: 0.0% | epoch: 1 | remaining: 0s    \nRUNNER_TIMEOUT: exceeded 600 seconds\n"
        )
        self.assertEqual(payload["status_class"], "late-timeout")
        self.assertEqual(payload["last_remaining_seconds"], 0)

    def test_early_step_stall_log_classifies_as_early_step_stall(self) -> None:
        log_path = CONTROL_ROOT / "logs" / "mar10" / "embedding_lr_0625.log"
        payload = classify_log(log_path.read_text(errors="replace"))
        self.assertEqual(payload["status_class"], "early-step-stall")
        self.assertEqual(payload["last_step"], 1)

    def test_runner_abort_log_classifies_as_early_step_stall(self) -> None:
        payload = classify_log(
            "\n".join(
                [
                    "step 00009 (0.0%) | loss: 7.58 | lrm: 1.00 | dt: 25754ms | tok/sec: 1272 | mfu: 0.0% | epoch: 1 | remaining: 300s",
                    "step 00010 (0.0%) | loss: 7.44 | lrm: 1.00 | dt: 81118ms | tok/sec: 403 | mfu: 0.0% | epoch: 1 | remaining: 300s",
                    "step 00011 (0.0%) | loss: 7.30 | lrm: 1.00 | dt: 101609ms | tok/sec: 322 | mfu: 0.0% | epoch: 1 | remaining: 198s",
                    "RUNNER_ABORT: early stall threshold exceeded (3 >= 3; dt>=30000ms by step<=20; worst step 11 at 101.6s)",
                ]
            )
        )
        self.assertEqual(payload["status_class"], "early-step-stall")
        self.assertIn("runner aborted", payload["reason"])

    def test_optimizer_micro_band_is_exhausted_after_gated_suppression(self) -> None:
        queue = build_queue(WORKSPACE_ROOT, "autoresearch/mar10", "optimizer-micro", 6, CONTROL_ROOT)
        self.assertEqual(queue, [])

    def test_weight_decay_ridge_band_starts_with_expected_candidates(self) -> None:
        queue = build_queue(WORKSPACE_ROOT, "autoresearch/mar10", "weight-decay-ridge", 6, CONTROL_ROOT)
        self.assertGreaterEqual(len(queue), 2)
        self.assertEqual(queue[0]["id"], "weight_decay_0215")
        self.assertEqual(queue[0]["description"], "raise weight decay to 0.215")
        self.assertEqual(queue[1]["id"], "weight_decay_0235")
        self.assertEqual(queue[1]["description"], "raise weight decay to 0.235")
        self.assertEqual(len({item["description"] for item in queue}), len(queue))

    def test_scalar_first_band_starts_with_expected_candidates(self) -> None:
        queue = build_queue(WORKSPACE_ROOT, "autoresearch/mar10", "scalar-first", 4, CONTROL_ROOT)
        self.assertEqual([item["id"] for item in queue], ["scalar_lr_04875", "scalar_lr_048125"])

    def test_reconciler_regenerates_current_handoff_text(self) -> None:
        payload = build_output(WORKSPACE_ROOT, "autoresearch/mar10", "mar10", CONTROL_ROOT)
        self.assertIn("Best commit: `5b486fb`", payload["handoff_text"])
        self.assertIn("Current best commit: `5b486fb`", payload["run_notes_text"])

    def test_session_status_exposes_frontier_and_next_action(self) -> None:
        payload = build_session_payload(WORKSPACE_ROOT, "autoresearch/mar10", CONTROL_ROOT, 1.3880, 4)
        self.assertEqual(payload["frontier"]["current_best_commit"], "5b486fb")
        self.assertEqual(payload["environment"]["trust_state"], "untrusted")
        self.assertTrue(payload["recommended_next_action"])

    def test_default_plan_prefers_backend_isolation_plan(self) -> None:
        path = default_plan_path(CONTROL_ROOT, "mar10")
        self.assertTrue(str(path).endswith("mar10_backend_isolation_then_repeatability.json"))

    def test_repeatability_branching_uses_material_win_threshold(self) -> None:
        context = {"paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10", "current_best_val": 1.390250}
        items = [
            {"id": "frontier_repeat_a", "val_bpb": 1.3900, "status_class": "post-train-overrun", "num_steps": 340},
            {"id": "frontier_repeat_b", "val_bpb": 1.3905, "status_class": "post-train-overrun", "num_steps": 339},
            {"id": "weight_decay_repeat_022_a", "val_bpb": 1.3882, "status_class": "post-train-overrun", "num_steps": 341},
            {"id": "weight_decay_repeat_022_b", "val_bpb": 1.3881, "status_class": "post-train-overrun", "num_steps": 340},
        ]
        action = repeatability_branching_decision(context, items)
        self.assertIn("weight_decay_confirmation", action)

    def test_repeatability_branching_rejects_truncated_runs(self) -> None:
        context = {"paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10", "current_best_val": 1.386688}
        items = [
            {"id": "frontier_repeat_a", "val_bpb": 2.244121, "status_class": "post-train-overrun", "num_steps": 14},
            {"id": "frontier_repeat_b", "val_bpb": 1.392134, "status_class": "post-train-overrun", "num_steps": 342},
        ]
        action = repeatability_branching_decision(context, items)
        self.assertIn("backend/environment investigation", action)

    def test_repeatability_gate_selects_scalar_when_weight_decay_is_not_material(self) -> None:
        items = [
            {"id": "frontier_repeat_a", "val_bpb": 1.3900, "status_class": "post-train-overrun", "num_steps": 340},
            {"id": "frontier_repeat_b", "val_bpb": 1.3905, "status_class": "post-train-overrun", "num_steps": 339},
            {"id": "weight_decay_repeat_022_a", "val_bpb": 1.3896, "status_class": "post-train-overrun", "num_steps": 341},
            {"id": "weight_decay_repeat_022_b", "val_bpb": 1.3897, "status_class": "post-train-overrun", "num_steps": 340},
        ]
        evaluation = evaluate_repeatability_gate(items, frontier_anchor_val=1.3902)
        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["next_stage"], "scalar_first_canary")

    def test_repeatability_gate_rejects_anchor_drift(self) -> None:
        items = [
            {"id": "frontier_repeat_a", "val_bpb": 1.3950, "status_class": "post-train-overrun", "num_steps": 334},
            {"id": "frontier_repeat_b", "val_bpb": 1.3954, "status_class": "post-train-overrun", "num_steps": 333},
            {"id": "weight_decay_repeat_022_a", "val_bpb": 1.4069, "status_class": "post-train-overrun", "num_steps": 312},
            {"id": "weight_decay_repeat_022_b", "val_bpb": 1.4071, "status_class": "post-train-overrun", "num_steps": 311},
        ]
        evaluation = evaluate_repeatability_gate(items, frontier_anchor_val=1.386688)
        self.assertFalse(evaluation["passed"])
        self.assertIn("worse than the canonical anchor", evaluation["reason"])

    def test_frontier_isolation_gate_rejects_anchor_drift(self) -> None:
        items = [
            {"id": "frontier_repeat_isolation_a", "val_bpb": 1.3950, "status_class": "post-train-overrun", "num_steps": 334},
            {"id": "frontier_repeat_isolation_b", "val_bpb": 1.3954, "status_class": "post-train-overrun", "num_steps": 333},
        ]
        evaluation = evaluate_frontier_isolation_gate(items, frontier_anchor_val=1.386688)
        self.assertFalse(evaluation["passed"])
        self.assertIn("worse than the canonical anchor", evaluation["reason"])

    def test_frontier_isolation_decision_requires_environment_forensics_on_drift(self) -> None:
        context = {"paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10", "current_best_val": 1.386688}
        items = [
            {"id": "frontier_repeat_isolation_a", "val_bpb": 1.3950, "status_class": "post-train-overrun", "num_steps": 334},
            {"id": "frontier_repeat_isolation_b", "val_bpb": 1.3954, "status_class": "post-train-overrun", "num_steps": 333},
        ]
        action = frontier_isolation_decision(context, items)
        self.assertIn("backend/environment investigation", action)

    def test_orchestrator_preflight_blocks_missing_execution_root(self) -> None:
        plan = {
            "tag": "mar10",
            "execution_root": "/tmp/does-not-exist-mar10",
            "control_root": str(CONTROL_ROOT),
            "train_cmd": "/bin/echo train.py",
            "stages": [],
        }
        blockers, warnings = plan_preflight_blockers(plan, resume=False)
        self.assertTrue(blockers)
        self.assertEqual(warnings, [])
        self.assertIn("execution root does not exist", blockers[0])

    def test_backend_isolation_success_branches_to_dedicated_repeatability(self) -> None:
        summary = {"passed": True, "reason": "frontier isolation passed"}
        stage = {
            "id": "backend_isolation",
            "success_rule": "frontier_isolation_gate",
            "on_success": {"next_stage": "dedicated_repeatability"},
        }
        next_stage, reason = next_stage_from_summary(summary, stage)
        self.assertEqual(next_stage, "dedicated_repeatability")
        self.assertEqual(reason, "frontier isolation passed")

    def test_dedicated_repeatability_success_stops_even_with_recommended_search_stage(self) -> None:
        summary = {
            "passed": True,
            "reason": "environment is stable and weight decay does not materially win",
            "recommended_search_stage": "scalar_first_canary",
        }
        stage = {
            "id": "dedicated_repeatability",
            "success_rule": "repeatability_gate",
            "on_success": {"action": "stop", "reason": "environment recovered; defer search to a later run window"},
        }
        next_stage, reason = next_stage_from_summary(summary, stage)
        self.assertIsNone(next_stage)
        self.assertEqual(reason, "environment recovered; defer search to a later run window")


if __name__ == "__main__":
    unittest.main()
