"""Unit tests for Phase53 policies and gates (no MT5)."""

from __future__ import annotations

import unittest

from phase53.evaluation import discovery_gate, summarize_decisions
from phase53.policies import decide_cmc, decide_exf, decide_slf, family_registry
from phase53.qualification import choose_verdict


class TestPolicies(unittest.TestCase):
    def test_registry_three_families(self):
        reg = family_registry()
        self.assertEqual(reg["n_families"], 3)
        self.assertIn("registry_sha256", reg)

    def test_cmc_wait_on_tight_move(self):
        d = decide_cmc(
            {
                "B02_net_disp_atr_12": 0.1,
                "E02_spread_atr": 0.05,
                "D03_overlap": 1.0,
                "C02_rv_48": 0.001,
            }
        )
        self.assertEqual(d["action"], "WAIT")

    def test_cmc_buy(self):
        d = decide_cmc(
            {
                "B02_net_disp_atr_12": 0.8,
                "E02_spread_atr": 0.05,
                "D03_overlap": 1.0,
                "C02_rv_48": 0.001,
            }
        )
        self.assertEqual(d["action"], "BUY")

    def test_exf_fade(self):
        d = decide_exf(
            {
                "B03_consec_dir": 7.0,
                "B04_impulse_retr_ratio": 0.2,
                "E02_spread_atr": 0.05,
                "C02_rv_48": 0.001,
            }
        )
        self.assertEqual(d["action"], "SELL")

    def test_slf_wait_without_agree(self):
        d = decide_slf(
            {
                "D03_overlap": 1.0,
                "F04_mtf_agree": 0.0,
                "F02_h1_ret": 0.01,
                "E03_spread_delta": -0.01,
                "C02_rv_48": 0.001,
            }
        )
        self.assertEqual(d["action"], "WAIT")


class TestVerdict(unittest.TestCase):
    def test_no_edge(self):
        v, _ = choose_verdict({"discovery": {"n_survivors": 0}, "confirmation": {"opened": False}})
        self.assertEqual(v, "NO_EDGE_FOUND")

    def test_insufficient(self):
        v, _ = choose_verdict({"insufficient_independent_data": "none left"})
        self.assertEqual(v, "INSUFFICIENT_INDEPENDENT_DATA")


class TestGate(unittest.TestCase):
    def test_wait_only_fails(self):
        decisions = [{"day": "2025-01-01", "action": "WAIT", "net_r": 0.0, "stress_net_r": 0.0}] * 30
        decisions += [{"day": "2025-01-02", "action": "WAIT", "net_r": 0.0, "stress_net_r": 0.0}] * 30
        summary = summarize_decisions(decisions, label="t")
        bas = {
            "CONSTANT_BUY": summarize_decisions(
                [{"day": "2025-01-01", "action": "BUY", "net_r": 0.1, "stress_net_r": 0.05}] * 30
                + [{"day": "2025-01-02", "action": "BUY", "net_r": 0.1, "stress_net_r": 0.05}] * 30,
                label="b",
            )
        }
        bas["CONSTANT_SELL"] = bas["CONSTANT_BUY"]
        bas["ALWAYS_WAIT"] = summary
        gate = discovery_gate(summary, bas, {"randomized": summary, "static": summary})
        self.assertFalse(gate["survives_discovery"])


if __name__ == "__main__":
    unittest.main()
