"""Phase 45 tests — audit policy and verdict logic."""

from __future__ import annotations

import unittest

from phase45.constants import CHAMPION_STATUS, PRODUCTION_FINAL_ACTION, RECIPE_ID, RETIRED_STRATEGIES
from phase45.qualification import decide_verdict
from phase45.scan_verdicts import scan_final_verdicts
from phase45.constants import REPORTS_ROOT


class TestPolicy(unittest.TestCase):
    def test_policy(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(PRODUCTION_FINAL_ACTION, "WAIT")
        self.assertTrue(RECIPE_ID.startswith("phase45_"))
        self.assertIn("H13_C", RETIRED_STRATEGIES)
        self.assertIn("mean_reversion", RETIRED_STRATEGIES)


class TestScan(unittest.TestCase):
    def test_reload_verdicts(self):
        rows = scan_final_verdicts(REPORTS_ROOT)
        self.assertGreaterEqual(len(rows), 10)
        phases = {r["phase"] for r in rows}
        self.assertIn("phase44", phases)
        self.assertIn("phase43", phases)


class TestVerdict(unittest.TestCase):
    def test_redirect(self):
        v = decide_verdict(
            taxonomy={"primary_root_cause": "F1+F3+F4"},
            learning={"genuinely_adaptive": False},
            data={"data_blocks_research": False},
            gaps={"gaps": [{"gap_id": "G1"}]},
        )
        self.assertEqual(v["final_verdict"], "RESEARCH_PROGRAM_REDIRECT_REQUIRED")

    def test_data_block(self):
        v = decide_verdict(
            taxonomy={},
            learning={"genuinely_adaptive": False},
            data={"data_blocks_research": True},
            gaps={"gaps": []},
        )
        self.assertEqual(v["final_verdict"], "DATA_LIMITATIONS_BLOCK_RESEARCH")


if __name__ == "__main__":
    unittest.main()
