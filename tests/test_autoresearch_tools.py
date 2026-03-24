from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from autoresearch_lib import DEFAULT_CONTROL_ROOT, DEFAULT_TARGET_ROOT, classify_log  # noqa: E402
from build_queue import build_queue  # noqa: E402
from frontier_status import build_payload  # noqa: E402
from reconcile_session import build_output  # noqa: E402


class AutoresearchToolTests(unittest.TestCase):
    def test_frontier_status_reports_canonical_best_and_stale_handoff(self) -> None:
        payload = build_payload(DEFAULT_TARGET_ROOT, "autoresearch/mar10", DEFAULT_CONTROL_ROOT)
        self.assertEqual(payload["current_best_commit"], "5b486fb")
        self.assertAlmostEqual(payload["current_best_val"], 1.386688, places=6)
        self.assertTrue(
            any(
                flag["artifact"] == "handoff" and flag["severity"] == "warning"
                for flag in payload["coherence_flags"]
            )
        )

    def test_timeout_only_log_classifies_as_watchdog_timeout(self) -> None:
        payload = classify_log("RUNNER_TIMEOUT: exceeded 600 seconds\n", control_state=None)
        self.assertEqual(payload["status_class"], "watchdog-timeout")
        self.assertFalse(payload["informative"])

    def test_completed_long_log_is_not_blind_crash(self) -> None:
        log_path = ROOT / "worktrees" / "control" / "control" / "logs" / "mar10" / "weight_decay_022.log"
        payload = classify_log(log_path.read_text(errors="replace"))
        self.assertTrue(payload["informative"])
        self.assertIn(payload["status_class"], {"completed", "post-train-overrun"})

    def test_queue_planner_starts_with_expected_unresolved_candidate(self) -> None:
        queue = build_queue(DEFAULT_TARGET_ROOT, "autoresearch/mar10", "optimizer-micro", 6, DEFAULT_CONTROL_ROOT)
        self.assertGreaterEqual(len(queue), 1)
        self.assertEqual(queue[0]["id"], "adam_betas_08_096")
        self.assertEqual(queue[0]["description"], "change adam betas to (0.8, 0.96)")
        self.assertEqual(len({item["description"] for item in queue}), len(queue))

    def test_reconciler_regenerates_current_handoff_text(self) -> None:
        payload = build_output(DEFAULT_TARGET_ROOT, "autoresearch/mar10", "mar10", DEFAULT_CONTROL_ROOT)
        self.assertIn("Best commit: `5b486fb`", payload["handoff_text"])
        self.assertIn("Current best commit: `5b486fb`", payload["run_notes_text"])


if __name__ == "__main__":
    unittest.main()
