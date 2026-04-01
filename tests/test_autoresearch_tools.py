from __future__ import annotations

import sys
import tempfile
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
from overnight_runner import reset_target_commit, terminate_process_group  # noqa: E402
from reconcile_session import build_output  # noqa: E402
from review_mar10_scalar_candidate_bracket import (  # noqa: E402
    ReviewError,
    evaluate_scalar_candidate_bracket,
)
from review_mar10_scalar_0475_confirmation import evaluate_scalar_0475_confirmation  # noqa: E402
from review_mar10_scalar_0475_fixed_step_confirmation import evaluate_scalar_0475_fixed_step_confirmation  # noqa: E402
from review_mar10_scalar_048125_fixed_step_confirmation import (  # noqa: E402
    evaluate_scalar_048125_fixed_step_confirmation,
)
import session_status as session_status_mod  # noqa: E402
from session_orchestrator import build_stage_command, next_stage_from_summary, plan_preflight_blockers, stage_should_advance  # noqa: E402
from session_status import (  # noqa: E402
    build_payload as build_session_payload,
    environment_status,
    evaluate_weight_decay_confirmation,
    frontier_isolation_decision,
    frontier_soak_decision,
    invalid_reboot_launch_orchestration,
    latest_completed_orchestrator_stage,
    read_post_reboot_arm_state,
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

    def test_reset_target_commit_prefers_execution_base_commit(self) -> None:
        state = {"current_best_commit": "5b486fb", "execution_base_commit": "9847c21"}
        self.assertEqual(reset_target_commit(state), "9847c21")

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

    def test_full_length_log_without_summary_classifies_as_post_train_summary_missing(self) -> None:
        payload = classify_log(
            "\n".join(
                [
                    "step 00342 (100.0%) | loss: 3.77 | lrm: 0.10 | dt: 906ms | tok/sec: 36244 | mfu: 0.0% | epoch: 1 | remaining: 0s",
                    "step 00343 (100.0%) | loss: 3.76 | lrm: 0.10 | dt: 911ms | tok/sec: 36045 | mfu: 0.0% | epoch: 1 | remaining: 0s",
                    "step 00344 (100.0%) | loss: 3.75 | lrm: 0.10 | dt: 899ms | tok/sec: 36526 | mfu: 0.0% | epoch: 1 | remaining: 0s",
                ]
            )
        )
        self.assertEqual(payload["status_class"], "post-train-summary-missing")
        self.assertEqual(payload["num_steps"], 345)

    def test_post_train_eval_exception_is_classified_explicitly(self) -> None:
        payload = classify_log(
            "\n".join(
                [
                    "completion_marker: phase=post_train_newline num_steps=345 training_seconds=300.0",
                    "completion_marker: phase=pre_eval num_steps=345 training_seconds=300.0",
                    "completion_error: phase=pre_eval exception=RuntimeError: MPS graph capture failed",
                    "Traceback (most recent call last):",
                    "  File \"train.py\", line 700, in <module>",
                    "    val_bpb = evaluate_bpb(model, tokenizer, DEVICE_BATCH_SIZE)",
                    "RuntimeError: MPS graph capture failed",
                    "completion_result: completion_phase=pre_eval num_steps=345 training_seconds=300.0 total_seconds=302.1",
                ]
            )
        )
        self.assertEqual(payload["status_class"], "post-train-eval-crash")
        self.assertEqual(payload["completion_error_phase"], "pre_eval")
        self.assertEqual(payload["num_steps"], 345)

    def test_completion_markers_do_not_break_valid_summary_classification(self) -> None:
        payload = classify_log(
            "\n".join(
                [
                    "completion_marker: phase=post_train_newline num_steps=354 training_seconds=300.6",
                    "completion_marker: phase=pre_eval num_steps=354 training_seconds=300.6",
                    "completion_marker: phase=post_eval num_steps=354 training_seconds=300.6 total_seconds=472.2",
                    "completion_marker: phase=pre_summary num_steps=354 training_seconds=300.6 total_seconds=472.2",
                    "---",
                    "val_bpb:          1.386662",
                    "startup_seconds:  12.3",
                    "warmup_seconds:   8.7",
                    "training_seconds: 300.6",
                    "eval_seconds:     150.6",
                    "total_seconds:    472.2",
                    "peak_vram_mb:     0.0",
                    "num_steps:        354",
                    "completion_marker: phase=post_summary num_steps=354 training_seconds=300.6 total_seconds=472.2",
                    "completion_result: completion_phase=post_summary num_steps=354 training_seconds=300.6 total_seconds=472.2",
                ]
            )
        )
        self.assertEqual(payload["status_class"], "post-train-overrun")
        self.assertAlmostEqual(payload["val_bpb"], 1.386662, places=6)

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
        self.assertEqual(payload["environment"]["trust_state"], "conditionally recovered")
        self.assertIn(payload["environment"]["next_stage"], {"define_next_narrow_axis", "weight_decay_confirmation"})
        self.assertIn(payload["overnight_recommendation"], {"candidate confirmed", "next-day canary earned", "search blocked"})
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
        self.assertEqual(evaluation["failure_class"], "quality-drift")
        self.assertIn("worse than the canonical anchor", evaluation["reason"])

    def test_frontier_isolation_gate_rejects_post_train_summary_missing(self) -> None:
        items = [
            {"id": "frontier_repeat_isolation_a", "status": "crash", "status_class": "post-train-summary-missing", "num_steps": 345},
            {"id": "frontier_repeat_isolation_b", "status": "keep", "status_class": "post-train-overrun", "val_bpb": 1.386662, "num_steps": 354},
        ]
        evaluation = evaluate_frontier_isolation_gate(items, frontier_anchor_val=1.386688)
        self.assertFalse(evaluation["passed"])
        self.assertEqual(evaluation["failure_class"], "post-train-summary-missing")

    def test_frontier_soak_gate_requires_six_clean_repeats(self) -> None:
        items = [
            {"id": "frontier_repeat_soak_a", "val_bpb": 1.3867, "status_class": "post-train-overrun", "num_steps": 351},
            {"id": "frontier_repeat_soak_b", "val_bpb": 1.3868, "status_class": "post-train-overrun", "num_steps": 352},
        ]
        evaluation = evaluate_frontier_isolation_gate(items, frontier_anchor_val=1.386688, required_repeats=6)
        self.assertFalse(evaluation["passed"])
        self.assertEqual(evaluation["failure_class"], "insufficient-clean-repeats")
        self.assertIn("6 completed baseline repeats", evaluation["reason"])

    def test_frontier_isolation_decision_requires_environment_forensics_on_drift(self) -> None:
        context = {"paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10", "current_best_val": 1.386688}
        items = [
            {"id": "frontier_repeat_isolation_a", "val_bpb": 1.3950, "status_class": "post-train-overrun", "num_steps": 334},
            {"id": "frontier_repeat_isolation_b", "val_bpb": 1.3954, "status_class": "post-train-overrun", "num_steps": 333},
        ]
        action = frontier_isolation_decision(context, items)
        self.assertIn("backend/environment investigation", action)

    def test_frontier_soak_decision_earns_repeatability_when_thresholds_hold(self) -> None:
        context = {"paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10", "current_best_val": 1.386688}
        items = [
            {"id": "frontier_repeat_soak_a", "val_bpb": 1.3867, "status_class": "post-train-overrun", "num_steps": 351},
            {"id": "frontier_repeat_soak_b", "val_bpb": 1.3869, "status_class": "post-train-overrun", "num_steps": 352},
            {"id": "frontier_repeat_soak_c", "val_bpb": 1.3866, "status_class": "post-train-overrun", "num_steps": 353},
            {"id": "frontier_repeat_soak_d", "val_bpb": 1.3868, "status_class": "post-train-overrun", "num_steps": 351},
            {"id": "frontier_repeat_soak_e", "val_bpb": 1.3865, "status_class": "post-train-overrun", "num_steps": 352},
            {"id": "frontier_repeat_soak_f", "val_bpb": 1.3867, "status_class": "post-train-overrun", "num_steps": 353},
        ]
        action = frontier_soak_decision(context, items)
        self.assertIn("comparability recovery", action)
        self.assertIn("run_mar10_frontier_fixed_step_same_session.sh", action)

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

    def test_backend_isolation_quality_drift_branches_to_frontier_soak(self) -> None:
        summary = {"passed": False, "reason": "frontier isolation spread is 0.003500", "failure_class": "quality-drift"}
        stage = {
            "id": "backend_isolation",
            "success_rule": "frontier_isolation_gate",
            "on_failure_by_class": {
                "quality-drift": {
                    "next_stage": "frontier_soak",
                    "reason": "backend isolation completed cleanly but drifted; continue frontier-only soak measurement",
                }
            },
            "on_failure": {"action": "stop", "reason": "backend isolation failed; continue backend/environment investigation"},
        }
        next_stage, reason = next_stage_from_summary(summary, stage)
        self.assertEqual(next_stage, "frontier_soak")
        self.assertIn("frontier-only soak measurement", reason)

    def test_failed_stage_can_advance_to_followup_diagnostic(self) -> None:
        self.assertTrue(stage_should_advance({"passed": False}, "frontier_fixed_step_same_boot_replay"))
        self.assertFalse(stage_should_advance({"passed": False}, None))

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

    def test_build_stage_command_includes_trust_target_steps(self) -> None:
        plan = {
            "best_commit": "5b486fb",
            "best_val": 1.386688,
            "execution_root": str(WORKSPACE_ROOT / "worktrees" / "execution-baseline-mar10"),
        }
        stage = {
            "id": "frontier_fixed_step_same_session",
            "kind": "repeatability",
            "queue": str(CONTROL_ROOT / "queues" / "mar10_frontier_fixed_step_same_session.jsonl"),
            "timeout_seconds": 750,
            "stall_abort_ms": 30000,
            "stall_abort_step_max": 20,
            "stall_abort_count": 3,
            "trust_target_steps": 354,
        }
        command = build_stage_command(stage, plan, resume=False)
        self.assertIn("--trust-target-steps", command)
        self.assertIn("354", command)

    def test_latest_completed_orchestrator_stage_recognizes_fixed_step_repeatability(self) -> None:
        orchestrator_state = {
            "completed_stages": [
                {"stage_id": "frontier_fixed_step_rebooted", "passed": True},
                {"stage_id": "dedicated_repeatability_fixed_step", "passed": True, "recommended_search_stage": "scalar_first_canary"},
            ]
        }
        stage = latest_completed_orchestrator_stage(orchestrator_state, "repeatability")
        self.assertIsNotNone(stage)
        self.assertEqual(stage["stage_id"], "dedicated_repeatability_fixed_step")

    def test_environment_status_treats_fixed_step_repeatability_as_active_gate(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        active_run = {"finished": False, "stage_id": "dedicated_repeatability_fixed_step"}
        orchestrator_state = {"completed_stages": [{"stage_id": "frontier_fixed_step_rebooted", "passed": True, "reason": "ok"}]}
        env = environment_status(context, active_run, None, [], orchestrator_state, False, False, {"invalid_launch_orchestration": False})
        self.assertEqual(env["trust_state"], "conditionally recovered")
        self.assertEqual(env["next_stage"], "dedicated_repeatability_fixed_step")
        self.assertEqual(env["search_blocked_reason"], "fixed-step dedicated repeatability is in progress")

    def test_environment_status_keeps_same_boot_replay_untrusted_even_on_pass(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        orchestrator_state = {
            "completed_stages": [
                {
                    "stage_id": "frontier_fixed_step_same_boot_replay",
                    "passed": True,
                    "reason": "same-boot replay passed after a reboot-stage failure; cold-session or session-initialization effects are now the leading hypothesis. Keep search blocked.",
                }
            ]
        }
        env = environment_status(context, None, None, [], orchestrator_state, False, False, {"invalid_launch_orchestration": False})
        self.assertEqual(env["trust_state"], "untrusted")
        self.assertIsNone(env["next_stage"])
        self.assertIn("cold-session", env["search_blocked_reason"])

    def test_environment_status_prefers_orchestrator_backend_stage_over_stale_finished_active_run(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        active_run = {
            "finished": True,
            "stage_id": "frontier_fixed_step_same_session",
            "session_kind": "repeatability",
            "queue_path": str(CONTROL_ROOT / "queues" / "mar10_frontier_fixed_step_same_session.jsonl"),
        }
        active_state = {
            "completed": [
                {
                    "id": "frontier_repeat_clean_c",
                    "status_class": "early-step-stall",
                    "num_steps": 11,
                }
            ]
        }
        orchestrator_state = {
            "completed_stages": [
                {
                    "stage_id": "frontier_fixed_step_same_session",
                    "passed": True,
                    "reason": "frontier isolation passed; baseline repeats are clean and close to the canonical anchor",
                    "runtime_forensics_bundle": "/tmp/fixed-step-bundle",
                }
            ]
        }
        env = environment_status(context, active_run, active_state, [], orchestrator_state, False, False, {"invalid_launch_orchestration": False})
        self.assertTrue(env["latest_backend_isolation"]["passed"])
        self.assertEqual(env["next_stage"], "frontier_fixed_step_rebooted")
        self.assertEqual(
            env["search_blocked_reason"],
            "rebooted dedicated-session fixed-step isolation is still required before repeatability can reopen",
        )

    def test_invalid_reboot_launch_orchestration_when_stage_started_before_current_boot(self) -> None:
        active_run = {
            "stage_id": "frontier_fixed_step_rebooted",
            "started_at": 1000.0,
        }
        self.assertTrue(
            invalid_reboot_launch_orchestration(
                active_run,
                None,
                False,
                None,
                False,
                1001,
                None,
            )
        )

    def test_invalid_reboot_launch_orchestration_clears_once_runner_error_exists(self) -> None:
        active_run = {
            "stage_id": "frontier_fixed_step_rebooted",
            "started_at": 1000.0,
        }
        self.assertFalse(
            invalid_reboot_launch_orchestration(
                active_run,
                None,
                False,
                None,
                False,
                1001,
                "git worktree must be clean except known artifacts; found:\n M train.py",
            )
        )

    def test_invalid_reboot_launch_orchestration_falls_back_to_interrupted_empty_attempt(self) -> None:
        active_run = {
            "stage_id": "frontier_fixed_step_rebooted",
            "started_at": 1000.0,
        }
        active_state = {"attempted": 0, "completed": []}
        orchestrator_state = {"completed_stages": []}
        self.assertTrue(
            invalid_reboot_launch_orchestration(
                active_run,
                active_state,
                True,
                orchestrator_state,
                False,
                None,
                None,
            )
        )

    def test_environment_status_reports_invalid_reboot_launch_orchestration(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        active_run = {"finished": False, "stage_id": "frontier_fixed_step_rebooted"}
        active_state = {"attempted": 0, "completed": []}
        orchestrator_state = {"completed_stages": []}
        env = environment_status(
            context,
            active_run,
            active_state,
            [],
            orchestrator_state,
            True,
            True,
            {"invalid_launch_orchestration": True},
        )
        self.assertEqual(env["trust_state"], "untrusted")
        self.assertEqual(env["next_stage"], "frontier_fixed_step_rebooted")
        self.assertIn("launch failed before any informative attempt", env["search_blocked_reason"])

    def test_environment_status_points_finished_trust_recovery_to_confirmation_canary(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        orchestrator_state = {
            "completed_stages": [
                {
                    "stage_id": "frontier_fixed_step_rebooted",
                    "passed": True,
                    "reason": "frontier isolation passed; baseline repeats are clean and close to the canonical anchor",
                },
                {
                    "stage_id": "dedicated_repeatability_fixed_step",
                    "passed": True,
                    "reason": "environment is stable and weight decay materially wins",
                    "recommended_search_stage": "weight_decay_confirmation",
                },
            ]
        }
        env = environment_status(
            context,
            None,
            None,
            [],
            orchestrator_state,
            False,
            False,
            {"invalid_launch_orchestration": False},
        )
        self.assertEqual(env["trust_state"], "conditionally recovered")
        self.assertEqual(env["next_stage"], "weight_decay_confirmation")
        self.assertIn("next-day canary earned", env["search_blocked_reason"])

    def test_weight_decay_confirmation_promotes_confirmed_lead(self) -> None:
        evaluation = evaluate_weight_decay_confirmation(
            [
                {"id": "frontier_repeat_confirmation_c", "val_bpb": 1.384847, "status_class": "post-train-overrun", "num_steps": 357},
                {"id": "weight_decay_repeat_022_confirmation_c", "val_bpb": 1.380148, "status_class": "post-train-overrun", "num_steps": 369},
                {"id": "weight_decay_repeat_022_confirmation_d", "val_bpb": 1.384010, "status_class": "post-train-overrun", "num_steps": 360},
            ]
        )
        self.assertTrue(evaluation["passed"])
        self.assertTrue(evaluation["confirmed_lead"])
        self.assertAlmostEqual(evaluation["mean_improvement"], 0.002768, places=6)
        self.assertEqual(evaluation["next_stage"], "define_next_narrow_axis")

    def test_environment_status_reports_finished_confirmation_stage(self) -> None:
        context = {"current_best_val": 1.386688, "paths": {"control_root": str(CONTROL_ROOT)}, "tag": "mar10"}
        active_run = {
            "finished": True,
            "session_kind": "repeatability",
            "stage_id": "weight_decay_confirmation",
            "queue_path": str(CONTROL_ROOT / "queues" / "mar10_weight_decay_confirmation.jsonl"),
        }
        active_state = {
            "completed": [
                {"id": "frontier_repeat_confirmation_c", "val_bpb": 1.384847, "status_class": "post-train-overrun", "num_steps": 357},
                {"id": "weight_decay_repeat_022_confirmation_c", "val_bpb": 1.380148, "status_class": "post-train-overrun", "num_steps": 369},
                {"id": "weight_decay_repeat_022_confirmation_d", "val_bpb": 1.384010, "status_class": "post-train-overrun", "num_steps": 360},
            ]
        }
        orchestrator_state = {
            "completed_stages": [
                {"stage_id": "frontier_fixed_step_rebooted", "passed": True, "reason": "frontier isolation passed"},
                {
                    "stage_id": "dedicated_repeatability_fixed_step",
                    "passed": True,
                    "reason": "environment is stable and weight decay materially wins",
                    "recommended_search_stage": "weight_decay_confirmation",
                },
            ]
        }
        env = environment_status(
            context,
            active_run,
            active_state,
            [],
            orchestrator_state,
            False,
            False,
            {"invalid_launch_orchestration": False},
        )
        self.assertEqual(env["trust_state"], "conditionally recovered")
        self.assertEqual(env["next_stage"], "define_next_narrow_axis")
        self.assertIn("confirmed lead", env["search_blocked_reason"])

    def test_scalar_candidate_bracket_promotes_best_scalar(self) -> None:
        state = {
            "finished": True,
            "attempted": 6,
            "stopped_reason": "queue exhausted",
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_repeat_e",
                    "status": "discard",
                    "val_bpb": 1.384000,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.1,
                    "eval_seconds": 150.2,
                    "total_seconds": 461.0,
                    "max_step_dt_ms": 1800,
                    "last_step_dt_ms": 840,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/candidate_weight_decay_022_repeat_e.log",
                },
                {
                    "id": "scalar_lr_04875_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.383700,
                    "num_steps": 361,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.1,
                    "eval_seconds": 150.1,
                    "total_seconds": 461.1,
                    "max_step_dt_ms": 1750,
                    "last_step_dt_ms": 842,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_04875_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_048125_on_weight_decay_022",
                    "status": "keep",
                    "val_bpb": 1.382300,
                    "num_steps": 362,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.1,
                    "eval_seconds": 150.0,
                    "total_seconds": 461.2,
                    "max_step_dt_ms": 1760,
                    "last_step_dt_ms": 844,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_048125_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_0475_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.383100,
                    "num_steps": 361,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.2,
                    "eval_seconds": 150.0,
                    "total_seconds": 461.4,
                    "max_step_dt_ms": 1780,
                    "last_step_dt_ms": 845,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_0475_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_046875_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 359,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.4,
                    "eval_seconds": 150.0,
                    "total_seconds": 461.6,
                    "max_step_dt_ms": 1810,
                    "last_step_dt_ms": 846,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_046875_on_weight_decay_022.log",
                },
                {
                    "id": "candidate_weight_decay_022_repeat_f",
                    "status": "discard",
                    "val_bpb": 1.383800,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "training_seconds": 300.1,
                    "eval_seconds": 150.2,
                    "total_seconds": 461.0,
                    "max_step_dt_ms": 1790,
                    "last_step_dt_ms": 843,
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/candidate_weight_decay_022_repeat_f.log",
                },
            ],
        }
        review = evaluate_scalar_candidate_bracket(
            state,
            Path("/tmp/report.md"),
            Path("/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar/logs/overnight/execution-weight-decay-022-scalar"),
        )
        self.assertEqual(review["classification"], "scalar_promoted")
        self.assertAlmostEqual(review["baseline_mean"], 1.3839, places=6)
        self.assertAlmostEqual(review["baseline_spread"], 0.0002, places=6)
        self.assertEqual(review["best_scalar"]["id"], "scalar_lr_048125_on_weight_decay_022")
        self.assertAlmostEqual(review["best_scalar"]["delta"], 0.0016, places=6)
        self.assertNotIn("/logs/logs/", review["best_scalar"]["log_path"])

    def test_scalar_candidate_bracket_flags_inconclusive_drift(self) -> None:
        state = {
            "finished": True,
            "attempted": 6,
            "stopped_reason": "queue exhausted",
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_repeat_e",
                    "status": "discard",
                    "val_bpb": 1.3840,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/candidate_weight_decay_022_repeat_e.log",
                },
                {
                    "id": "scalar_lr_04875_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.3810,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_04875_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_048125_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.3820,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_048125_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_0475_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.3830,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_0475_on_weight_decay_022.log",
                },
                {
                    "id": "scalar_lr_046875_on_weight_decay_022",
                    "status": "discard",
                    "val_bpb": 1.3845,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/scalar_lr_046875_on_weight_decay_022.log",
                },
                {
                    "id": "candidate_weight_decay_022_repeat_f",
                    "status": "discard",
                    "val_bpb": 1.3860,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar/candidate_weight_decay_022_repeat_f.log",
                },
            ],
        }
        review = evaluate_scalar_candidate_bracket(
            state,
            Path("/tmp/report.md"),
            Path("/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar/logs/overnight/execution-weight-decay-022-scalar"),
        )
        self.assertEqual(review["classification"], "inconclusive_drift")
        self.assertGreater(review["baseline_spread"], 0.0010)

    def test_scalar_candidate_bracket_rejects_unfinished_run(self) -> None:
        with self.assertRaises(ReviewError):
            evaluate_scalar_candidate_bracket(
                {"finished": False, "completed": []},
                Path("/tmp/report.md"),
                Path("/tmp/logs"),
            )

    def test_scalar_0475_confirmation_confirms_candidate(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_repeat_g",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_g.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.380700,
                    "num_steps": 362,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_d",
                    "status": "keep",
                    "val_bpb": 1.380900,
                    "num_steps": 361,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_repeat_h",
                    "status": "discard",
                    "val_bpb": 1.384800,
                    "num_steps": 359,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_h.log",
                },
            ],
        }
        review = evaluate_scalar_0475_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/logs/overnight/execution-weight-decay-022-scalar-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "scalar_confirmed")
        self.assertAlmostEqual(review["baseline_mean"], 1.3845, places=6)
        self.assertAlmostEqual(review["candidate_mean"], 1.3808, places=6)
        self.assertAlmostEqual(review["candidate_spread"], 0.0002, places=6)
        self.assertAlmostEqual(review["delta"], 0.0037, places=6)

    def test_scalar_0475_confirmation_flags_candidate_drift(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_repeat_g",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 360,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_g.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.380700,
                    "num_steps": 362,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_d",
                    "status": "keep",
                    "val_bpb": 1.382200,
                    "num_steps": 361,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_repeat_h",
                    "status": "discard",
                    "val_bpb": 1.384800,
                    "num_steps": 359,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_h.log",
                },
            ],
        }
        review = evaluate_scalar_0475_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/logs/overnight/execution-weight-decay-022-scalar-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "inconclusive_drift")
        self.assertGreater(review["candidate_spread"], 0.0010)

    def test_scalar_0475_confirmation_reports_candidate_stats_even_when_baseline_drifts(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_repeat_g",
                    "status": "discard",
                    "val_bpb": 1.381425,
                    "num_steps": 365,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_g.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.380410,
                    "num_steps": 367,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_0475_confirmation_d",
                    "status": "discard",
                    "val_bpb": 1.382641,
                    "num_steps": 365,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_repeat_h",
                    "status": "discard",
                    "val_bpb": 1.384940,
                    "num_steps": 357,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_repeat_h.log",
                },
            ],
        }
        review = evaluate_scalar_0475_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/logs/overnight/execution-weight-decay-022-scalar-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "inconclusive_drift")
        self.assertAlmostEqual(review["candidate_mean"], 1.3815255, places=6)
        self.assertAlmostEqual(review["candidate_spread"], 0.002231, places=6)
        self.assertAlmostEqual(review["delta"], 0.001657, places=6)
        self.assertIn("fixed-step controls", review["next_day_action"])

    def test_scalar_0475_fixed_step_confirmation_confirms_candidate(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "trust_target_steps": 354,
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_g",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_fixed_step_repeat_g.log",
                },
                {
                    "id": "scalar_lr_0475_fixed_step_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.380700,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_fixed_step_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_0475_fixed_step_confirmation_d",
                    "status": "keep",
                    "val_bpb": 1.380900,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_fixed_step_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_h",
                    "status": "discard",
                    "val_bpb": 1.384800,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_fixed_step_repeat_h.log",
                },
            ],
        }
        review = evaluate_scalar_0475_fixed_step_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/logs/overnight/execution-weight-decay-022-scalar-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "scalar_confirmed")
        self.assertAlmostEqual(review["baseline_mean"], 1.3845, places=6)
        self.assertAlmostEqual(review["candidate_mean"], 1.3808, places=6)
        self.assertAlmostEqual(review["candidate_spread"], 0.0002, places=6)
        self.assertAlmostEqual(review["delta"], 0.0037, places=6)

    def test_scalar_0475_fixed_step_confirmation_rejects_step_mismatch(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "trust_target_steps": 354,
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_g",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 353,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_fixed_step_repeat_g.log",
                },
                {
                    "id": "scalar_lr_0475_fixed_step_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.380700,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_fixed_step_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_0475_fixed_step_confirmation_d",
                    "status": "keep",
                    "val_bpb": 1.380900,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/scalar_lr_0475_fixed_step_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_h",
                    "status": "discard",
                    "val_bpb": 1.384800,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-confirmation/candidate_weight_decay_022_fixed_step_repeat_h.log",
                },
            ],
        }
        review = evaluate_scalar_0475_fixed_step_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-confirmation/logs/overnight/execution-weight-decay-022-scalar-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "stage_instability")
        self.assertIn("step-mismatch:353", ";".join(review["operational_issues"]))

    def test_scalar_048125_fixed_step_confirmation_confirms_candidate(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "trust_target_steps": 354,
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-048125-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_i",
                    "status": "discard",
                    "val_bpb": 1.384200,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/candidate_weight_decay_022_fixed_step_repeat_i.log",
                },
                {
                    "id": "scalar_lr_048125_fixed_step_confirmation_c",
                    "status": "keep",
                    "val_bpb": 1.382500,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/scalar_lr_048125_fixed_step_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_048125_fixed_step_confirmation_d",
                    "status": "keep",
                    "val_bpb": 1.382800,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/scalar_lr_048125_fixed_step_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_j",
                    "status": "discard",
                    "val_bpb": 1.384900,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/candidate_weight_decay_022_fixed_step_repeat_j.log",
                },
            ],
        }
        review = evaluate_scalar_048125_fixed_step_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-048125-confirmation/logs/overnight/execution-weight-decay-022-scalar-048125-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "scalar_confirmed")
        self.assertAlmostEqual(review["baseline_mean"], 1.38455, places=6)
        self.assertAlmostEqual(review["candidate_mean"], 1.38265, places=6)
        self.assertAlmostEqual(review["candidate_spread"], 0.0003, places=6)
        self.assertAlmostEqual(review["delta"], 0.0019, places=6)

    def test_scalar_048125_fixed_step_confirmation_marks_promising_when_subthreshold(self) -> None:
        state = {
            "finished": True,
            "attempted": 4,
            "stopped_reason": "queue exhausted",
            "trust_target_steps": 354,
            "state_path": "/tmp/overnight_execution-weight-decay-022-scalar-048125-confirmation.json",
            "completed": [
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_i",
                    "status": "discard",
                    "val_bpb": 1.385200,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/candidate_weight_decay_022_fixed_step_repeat_i.log",
                },
                {
                    "id": "scalar_lr_048125_fixed_step_confirmation_c",
                    "status": "discard",
                    "val_bpb": 1.385050,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/scalar_lr_048125_fixed_step_confirmation_c.log",
                },
                {
                    "id": "scalar_lr_048125_fixed_step_confirmation_d",
                    "status": "discard",
                    "val_bpb": 1.385000,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/scalar_lr_048125_fixed_step_confirmation_d.log",
                },
                {
                    "id": "candidate_weight_decay_022_fixed_step_repeat_j",
                    "status": "discard",
                    "val_bpb": 1.385100,
                    "num_steps": 354,
                    "status_class": "post-train-overrun",
                    "completion_phase": "post_summary",
                    "log_path": "logs/overnight/execution-weight-decay-022-scalar-048125-confirmation/candidate_weight_decay_022_fixed_step_repeat_j.log",
                },
            ],
        }
        review = evaluate_scalar_048125_fixed_step_confirmation(
            state,
            Path("/tmp/report.md"),
            Path(
                "/Users/davidabiera/Projects/team/autoresearch-macos/worktrees/execution-weight-decay-022-scalar-048125-confirmation/logs/overnight/execution-weight-decay-022-scalar-048125-confirmation"
            ),
        )
        self.assertEqual(review["classification"], "scalar_promising")
        self.assertAlmostEqual(review["delta"], 0.000125, places=6)

    def test_read_post_reboot_arm_state_preserves_machine_safe_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            arm_state = Path(tmpdir) / "mar10_fixed_step_post_reboot_arm.env"
            arm_state.write_text(
                "ARMED_BOOT_EPOCH=1774993620\n"
                "ARMED_AT_ISO=2026-03-31T15:05:12-0700\n",
                encoding="utf-8",
            )
            with mock.patch.object(session_status_mod, "POST_REBOOT_ARM_STATE", arm_state):
                payload = read_post_reboot_arm_state()
        self.assertEqual(payload["ARMED_BOOT_EPOCH"], "1774993620")
        self.assertEqual(payload["ARMED_AT_ISO"], "2026-03-31T15:05:12-0700")


if __name__ == "__main__":
    unittest.main()
