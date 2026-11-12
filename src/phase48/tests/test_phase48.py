"""Phase48 root-cause audit tests."""

from __future__ import annotations

import unittest

from phase47.ev import expected_net_r
from phase48.constants import EXPECTED_N, EXPECTED_PER_ACTION, PHASE46_CONTRACT_SHA256_EXPECTED
from phase48.root_causes import classify
from phase48.verify_outcomes import full_verify_11211, load_outcomes, verify_contract, verify_wait_row


class TestVerify11211(unittest.TestCase):
    def test_contract(self) -> None:
        c = verify_contract()
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["stored"], PHASE46_CONTRACT_SHA256_EXPECTED)

    def test_wait_contract_fields(self) -> None:
        rows = load_outcomes()
        waits = [r for r in rows if r["action"] == "WAIT"]
        self.assertEqual(len(waits), EXPECTED_PER_ACTION)
        for r in waits[:50]:
            self.assertEqual(verify_wait_row(r), [])

    def test_full_11211(self) -> None:
        result = full_verify_11211()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["total_records_accounted"], EXPECTED_N)
        self.assertEqual(result["wait"]["checked"], EXPECTED_PER_ACTION)
        self.assertEqual(result["directional"]["checked"], EXPECTED_PER_ACTION * 2)
        self.assertEqual(result["directional"]["mismatches"], 0)
        self.assertEqual(result["wait"]["failures"], 0)


class TestEVAndClassification(unittest.TestCase):
    def test_ev_identity(self) -> None:
        self.assertAlmostEqual(expected_net_r(0.55, 1.2, -0.8), 0.55 * 1.2 + 0.45 * (-0.8))

    def test_classify_requires_keys(self) -> None:
        # Minimal smoke: classification runs on stub-like structure from a tiny verify
        verify = full_verify_11211()
        # Use lightweight stubs for other audits if full run not desired — still call classify shape
        bundle = {
            "verify_11211": verify,
            "probability": {
                "buy_pooled": {"brier_skill_vs_const": -0.001, "n": 100},
                "sell_pooled": {"brier_skill_vs_const": 0.0, "n": 100},
            },
            "ev": {
                "buy": {"ev_identity_ok": True, "corr_p_vs_actual_sign": 0.01},
                "sell": {"ev_identity_ok": True, "corr_p_vs_actual_sign": 0.01},
            },
            "features": {
                "by_action": {
                    "BUY": {"max_abs_corr_with_target": 0.02},
                    "SELL": {"max_abs_corr_with_target": 0.03},
                }
            },
            "wait_gates": {
                "per_side": {
                    "BUY": {
                        "uncertainty_frac_above_threshold": 0.99,
                        "would_pass_all_gates_jointly": 0,
                    },
                    "SELL": {"would_pass_all_gates_jointly": 0},
                }
            },
            "costs": {"ok": True},
            "folds": {"leakage_ok": True},
        }
        out = classify(bundle)
        self.assertIn("top3_root_causes", out)
        self.assertGreaterEqual(len(out["top3_root_causes"]), 1)
        classes = {f["class"] for f in out["findings"]}
        self.assertIn("FEATURE_INFORMATION_FAILURE", classes)


if __name__ == "__main__":
    unittest.main()
