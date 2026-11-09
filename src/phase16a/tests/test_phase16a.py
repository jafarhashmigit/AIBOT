"""Phase 16A offline tests. No holdout. No broker orders. Synthetic where needed."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from phase12c.gate_adapter import ForwardGateAdapter
from phase16a.constants import (
    BUY_SELL_PRODUCTION_ENABLED,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FROZEN_CUTS,
    SESSION_DURATION_SECONDS,
)
from phase16a.features import features_at_index, latest_features
from phase16a.integrity import holdout_access_count, verify_protected_hashes
from phase16a.predictor import parity_smoke_cases, predict_h13c_experimental
from phase16a.storage import Phase16aShadowStore


class Phase16ATests(unittest.TestCase):
    def setUp(self) -> None:
        # Unit tests must not require a live MT5 import at collection time.
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertFalse(BUY_SELL_PRODUCTION_ENABLED)

    def test_01_champion_and_experimental_status(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
        self.assertEqual(SESSION_DURATION_SECONDS, 3600)
        self.assertEqual(FROZEN_CUTS["q_low"], 25)
        self.assertEqual(FROZEN_CUTS["q_high"], 75)

    def test_02_h13c_parity_and_gate(self):
        cases = parity_smoke_cases()
        for c in cases:
            self.assertEqual(c["got"], c["expected"], msg=str(c))
        gated = ForwardGateAdapter().apply("SELL")
        self.assertEqual(gated["final_action"], "WAIT")
        self.assertEqual(gated["gate_status"], "BLOCK")

    def test_03_features_causal_length(self):
        closes = [100.0 + i * 0.01 for i in range(30)]
        self.assertIsNone(features_at_index(closes, 10))
        feat = latest_features(closes)
        self.assertIsNotNone(feat)
        self.assertIn("close_to_ema_20", feat)
        self.assertIn("ema_9_20_spread", feat)

    def test_04_predict_keeps_final_wait(self):
        closes = [2000.0 + ((-1) ** i) * 0.5 for i in range(40)]
        # Rising closes for H1 up context
        h1 = []
        base = 2000.0
        for day in range(2):
            for hour in range(24):
                base += 1.0
                h1.append(
                    {
                        "time": f"2026-11-{1+day:02d} {hour:02d}:00:00",
                        "close": base,
                    }
                )
        out = predict_h13c_experimental(
            m5_closes=closes,
            h1_rows=h1,
            decision_time_utc="2026-11-02 20:00:00",
        )
        self.assertIn(out["experimental_action"], {"BUY", "SELL", "WAIT"})
        self.assertEqual(out["final_action"], "WAIT")
        self.assertEqual(out["champion_status"], "NO_MODEL")

    def test_05_store_rejects_duplicates_and_buy_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase16aShadowStore(Path(tmp))
            row = {
                "observation_id": "o1",
                "source_type": "FORWARD_SHADOW",
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "bar_open_timestamp_utc": "2026-11-01 10:00:00",
                "bar_close_timestamp_utc": "2026-11-01 10:05:00",
                "observation_created_at_utc": "2026-11-01 10:05:01",
                "open": 1, "high": 2, "low": 0.5, "close": 1.5,
                "tick_volume": 1, "spread": 0,
                "data_source": "synthetic",
                "data_quality_status": "ok",
                "gap_status": "first",
                "model_status": "NO_MODEL",
                "feature_snapshot_reference": "d1",
                "source_timezone": "UTC",
                "conversion": "already_utc",
                "source_stamp": "2026-11-01 10:00:00",
                "decision_id": "d1",
                "candidate_id": "H13_C_H1_PULLBACK",
                "candidate_status": "EXPERIMENTAL",
                "market_regime": "h1_up",
            }
            store.append_observation(row)
            with self.assertRaises(Exception):
                store.append_observation(row)
            dec = {
                "decision_id": "d1",
                "observation_id": "o1",
                "source_type": "FORWARD_SHADOW",
                "decision_timestamp_utc": "2026-11-01 10:05:00",
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "model_id": "no_model",
                "model_status": "NO_MODEL",
                "candidate_id": "H13_C_H1_PULLBACK",
                "candidate_status": "EXPERIMENTAL",
                "experimental_action": "BUY",
                "raw_action": "BUY",
                "risk_gate_result": "BLOCK",
                "final_action": "BUY",
                "decision_reason": "selected",
                "feature_snapshot_json": "{}",
                "outcome_status": "pending",
                "is_paper_trade": False,
                "is_paper_execution": False,
                "note": "x",
            }
            with self.assertRaises(Exception):
                store.append_decision(dec)
            dec["final_action"] = "WAIT"
            store.append_decision(dec)

    def test_06_protected_hashes_and_holdout(self):
        self.assertEqual(holdout_access_count(), 0)
        protected = verify_protected_hashes()
        self.assertTrue(protected["all_ok"], msg=str(protected))

    def test_07_mt5_not_imported_at_module_level(self):
        import inspect

        import phase16a.mt5_reader as mr

        # Module top-level (before first function) must not import MetaTrader5.
        preamble = inspect.getsource(mr).split("def open_readonly", 1)[0]
        self.assertNotIn("import MetaTrader5", preamble)


if __name__ == "__main__":
    unittest.main()
