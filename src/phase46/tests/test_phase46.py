"""Automated tests for Phase46 costed EV foundation."""

from __future__ import annotations

import unittest

from phase46.constants import (
    ENGINEERING_DATES,
    FORBIDDEN_VALIDATION_DATES,
    RECIPE_ID,
    canonical_json_sha256,
)
from phase46.contract import build_research_contract
from phase46.cost_scenarios import COST_SCENARIO_REGISTRY, apply_scenario_costs
from phase46.data import ForbiddenDateError, assert_date_allowed
from phase46.independent import recompute_directional
from phase46.outcomes import build_directional_outcome, build_wait_at_decision
from phase46.qualification import choose_verdict


class TestContract(unittest.TestCase):
    def test_contract_hash_stable(self) -> None:
        c = build_research_contract()
        again = canonical_json_sha256({k: v for k, v in c.items() if k != "contract_sha256"})
        self.assertEqual(c["contract_sha256"], again)
        self.assertEqual(c["recipe_id"], RECIPE_ID)
        self.assertFalse(c["execution_assumptions"]["live_broker_truth"])

    def test_engineering_disjoint_from_validation(self) -> None:
        self.assertFalse(set(ENGINEERING_DATES) & FORBIDDEN_VALIDATION_DATES)


class TestCosts(unittest.TestCase):
    def test_no_double_count_observed(self) -> None:
        sc = COST_SCENARIO_REGISTRY["OBSERVED_BIDASK_ONLY"]
        out = apply_scenario_costs(
            gross_pnl=1.0,
            risk_amount=2.0,
            entry_spread=0.2,
            exit_spread=0.2,
            scenario=sc,
        )
        self.assertEqual(out["net_pnl"], 1.0)
        self.assertEqual(out["spread_cost_additional"], 0.0)
        self.assertIn("commission", out["unknown_cost_components"])
        self.assertIn("slippage", out["unknown_cost_components"])

    def test_widen_adds_only_incremental(self) -> None:
        sc = COST_SCENARIO_REGISTRY["STRESS_SPREAD_WIDEN_1_5X"]
        out = apply_scenario_costs(
            gross_pnl=1.0,
            risk_amount=2.0,
            entry_spread=0.2,
            exit_spread=0.2,
            scenario=sc,
        )
        # (0.2+0.2)*0.5 = 0.2
        self.assertAlmostEqual(out["spread_cost_additional"], 0.2)
        self.assertAlmostEqual(out["net_pnl"], 0.8)


class TestDataGate(unittest.TestCase):
    def test_forbidden_validation_date(self) -> None:
        with self.assertRaises(ForbiddenDateError):
            assert_date_allowed("2025-10-27")


class TestOutcomesSynthetic(unittest.TestCase):
    def _bars_and_ticks(self):
        m5 = []
        ticks = {}
        # 40 bars starting 2025-07-02 01:00
        base_epoch = 1751418000
        px = 2000.0
        for i in range(40):
            ts = f"2025-07-02 {1 + (i * 5) // 60:02d}:{(i * 5) % 60:02d}:00"
            # simpler fixed timestamps via sequential labels
            hh = 1 + (i * 5) // 60
            mm = (i * 5) % 60
            ts = f"2025-07-02 {hh:02d}:{mm:02d}:00"
            high, low, close, open_ = px + 1, px - 1, px + 0.2, px
            m5.append(
                {
                    "timestamp_utc": ts,
                    "high": high,
                    "low": low,
                    "close": close,
                    "open": open_,
                }
            )
            # one tick at open-ish and one at end
            ms0 = base_epoch * 1000 + i * 300_000
            ticks[ts] = [
                {
                    "epoch_ms": ms0,
                    "timestamp_utc": ts + ".000",
                    "bid": px,
                    "ask": px + 0.1,
                },
                {
                    "epoch_ms": ms0 + 299_000,
                    "timestamp_utc": ts + ".299",
                    "bid": px + 0.3,
                    "ask": px + 0.4,
                },
            ]
            px += 0.05
        return m5, ticks

    def test_buy_ask_entry_bid_exit(self) -> None:
        m5, ticks = self._bars_and_ticks()
        # decision idx needs ATR warmup
        row = build_directional_outcome(
            action="BUY",
            day="2025-07-02",
            decision_idx=20,
            m5=m5,
            ticks_by_bar=ticks,
        )
        self.assertEqual(row["data_quality_status"], "OK")
        self.assertEqual(row["entry_fill"], row["entry_ask"])
        self.assertEqual(row["exit_fill"], row["exit_bid"])
        self.assertFalse(row["mid_price_used"])
        # independent match
        ind = recompute_directional(
            action="BUY",
            day="2025-07-02",
            decision_idx=20,
            m5=m5,
            ticks_by_bar=ticks,
        )
        self.assertEqual(ind["outcome_sha256"], row["outcome_sha256"])
        self.assertAlmostEqual(ind["gross_pnl"], row["gross_pnl"])

    def test_sell_bid_entry_ask_exit(self) -> None:
        m5, ticks = self._bars_and_ticks()
        row = build_directional_outcome(
            action="SELL",
            day="2025-07-02",
            decision_idx=20,
            m5=m5,
            ticks_by_bar=ticks,
        )
        self.assertEqual(row["entry_fill"], row["entry_bid"])
        self.assertEqual(row["exit_fill"], row["exit_ask"])

    def test_wait_zero(self) -> None:
        m5, ticks = self._bars_and_ticks()
        w = build_wait_at_decision(day="2025-07-02", decision_idx=20, m5=m5)
        self.assertEqual(w["action"], "WAIT")
        self.assertEqual(w["gross_pnl"], 0.0)
        self.assertEqual(w["net_pnl"], 0.0)
        self.assertEqual(w["net_r"], 0.0)


class TestVerdict(unittest.TestCase):
    def test_ready(self) -> None:
        v, _ = choose_verdict(
            contract_ok=True,
            independent_ok=True,
            data_gate_ok=True,
            n_ok_buy=50,
            n_ok_sell=50,
            n_wait=50,
            scenarios_present=True,
            mid_price_used=False,
        )
        self.assertEqual(v, "COSTED_EV_FOUNDATION_READY")

    def test_forbidden(self) -> None:
        v, _ = choose_verdict(
            contract_ok=True,
            independent_ok=True,
            data_gate_ok=False,
            n_ok_buy=50,
            n_ok_sell=50,
            n_wait=50,
            scenarios_present=True,
            mid_price_used=False,
        )
        self.assertEqual(v, "DATA_INTEGRITY_FAILURE")


if __name__ == "__main__":
    unittest.main()
