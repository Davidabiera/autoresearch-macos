from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
WORKSPACE_ROOT = Path("/Users/davidabiera/Projects/team/autoresearch-macos")
CONTROL_ROOT = WORKSPACE_ROOT / "worktrees" / "control" / "control"

from autoresearch_lib import classify_log  # noqa: E402
from build_queue import build_queue  # noqa: E402
from frontier_status import build_payload  # noqa: E402
from reconcile_session import build_output  # noqa: E402
from session_status import build_payload as build_session_payload  # noqa: E402


class AutoresearchToolTests(unittest.TestCase):
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
        self.assertGreaterEqual(len(queue), 2)
        self.assertEqual(queue[0]["id"], "scalar_lr_04875")
        self.assertEqual(queue[1]["id"], "scalar_lr_048125")

    def test_reconciler_regenerates_current_handoff_text(self) -> None:
        payload = build_output(WORKSPACE_ROOT, "autoresearch/mar10", "mar10", CONTROL_ROOT)
        self.assertIn("Best commit: `5b486fb`", payload["handoff_text"])
        self.assertIn("Current best commit: `5b486fb`", payload["run_notes_text"])

    def test_session_status_exposes_frontier_and_next_action(self) -> None:
        payload = build_session_payload(WORKSPACE_ROOT, "autoresearch/mar10", CONTROL_ROOT, 1.3880, 4)
        self.assertEqual(payload["frontier"]["current_best_commit"], "5b486fb")
        self.assertTrue(payload["recommended_next_action"])


if __name__ == "__main__":
    unittest.main()
