"""Phase55 engineering verification tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase54.archive_loader import list_archived_m5_days
from phase54.decision import NullPolicy, decide
from phase54.risk import RiskManager
from phase55.constants import ARCHIVE_ROOT, ENGINEERING_POLICY_VERSION, ENGINEERING_TAG
from phase55.engineering_policy import EngineeringTestPolicy
from phase55.harness import VerificationHarness, assert_production_policy_untouched, load_day_bundle
from phase55.independent import compare_to_engine, recompute_from_ticks
from phase55.risk_scenarios import run_risk_rejection_battery
from phase55.stores import production_counts


def _bundle():
    days = list_archived_m5_days(ARCHIVE_ROOT)
    if not days:
        raise unittest.SkipTest("no archive days")
    return load_day_bundle(days[0])


class TestEngineeringPolicy(unittest.TestCase):
    def test_sequence_deterministic(self):
        p = EngineeringTestPolicy(["BUY", "SELL", "WAIT"])
        self.assertEqual(p.version, ENGINEERING_POLICY_VERSION)
        a = p.propose({}, {}, None, {})["action"]
        b = p.propose({}, {}, None, {})["action"]
        c = p.propose({}, {}, None, {})["action"]
        self.assertEqual([a, b, c], ["BUY", "SELL", "WAIT"])
        self.assertIn(ENGINEERING_TAG, p.propose({}, {}, None, {})["reason_codes"])

    def test_production_null_untouched(self):
        r = assert_production_policy_untouched()
        self.assertTrue(r["ok"])
        d = decide({"bar_timestamp_utc": "2099-01-01 00:00:00", "data_quality_status": "OK"}, {}, None, {}, policy=NullPolicy())
        self.assertEqual(d["action"], "WAIT")


class TestBuySellRealArchive(unittest.TestCase):
    def test_buy_and_sell_lifecycle(self):
        b = _bundle()
        day, m5, h1, by = b["day"], b["m5"], b["h1"], b["ticks_by_bar"]
        with tempfile.TemporaryDirectory() as td:
            hb = VerificationHarness(
                policy=EngineeringTestPolicy(["BUY"]),
                state_path=Path(td) / "b.json",
            )
            buy = hb.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertEqual(buy["decision"]["action"], "BUY")
            self.assertIsNotNone(buy["closed"])
            self.assertEqual(buy["closed"]["entry_fill"], buy["closed"]["entry_ask"])
            self.assertEqual(buy["closed"]["exit_fill"], buy["closed"]["exit_bid"])
            self.assertTrue(buy["compare"]["ok"])
            self.assertIsNotNone(buy["closed"]["stop_loss"])
            self.assertIsNotNone(buy["closed"]["take_profit"])
            self.assertGreater(buy["closed"]["units"], 0)
            # idempotent
            self.assertTrue(hb.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)["skipped"])

            hs = VerificationHarness(
                policy=EngineeringTestPolicy(["SELL"]),
                state_path=Path(td) / "s.json",
            )
            sell = hs.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=60)
            self.assertEqual(sell["decision"]["action"], "SELL")
            self.assertEqual(sell["closed"]["entry_fill"], sell["closed"]["entry_bid"])
            self.assertEqual(sell["closed"]["exit_fill"], sell["closed"]["exit_ask"])
            self.assertTrue(sell["compare"]["ok"])


class TestWaitAndRisk(unittest.TestCase):
    def test_wait_no_position(self):
        b = _bundle()
        with tempfile.TemporaryDirectory() as td:
            h = VerificationHarness(policy=EngineeringTestPolicy(["WAIT"]), state_path=Path(td) / "w.json")
            r = h.process_decision(day=b["day"], m5=b["m5"], h1=b["h1"], ticks_by_bar=b["ticks_by_bar"], idx=48)
            self.assertEqual(r["decision"]["action"], "WAIT")
            self.assertIsNone(r["closed"])

    def test_risk_rejections(self):
        b = _bundle()
        with tempfile.TemporaryDirectory() as td:
            h = VerificationHarness(policy=EngineeringTestPolicy(["WAIT"]), state_path=Path(td) / "r.json")
            r = h.process_decision(day=b["day"], m5=b["m5"], h1=b["h1"], ticks_by_bar=b["ticks_by_bar"], idx=48)
            obs = r["observation"]
        bat = run_risk_rejection_battery(obs)
        for k in (
            "spread_block",
            "invalid_stop",
            "daily_loss_block",
            "drawdown_block",
            "max_positions_block",
            "duplicate_block",
            "circuit_breaker",
        ):
            self.assertEqual(bat["summary"][k]["final_action"], "WAIT", k)
            self.assertTrue(len(bat["summary"][k]["reasons"]) >= 1, k)

    def test_invalid_observation(self):
        b = _bundle()
        with tempfile.TemporaryDirectory() as td:
            h = VerificationHarness(policy=EngineeringTestPolicy(["BUY"]), state_path=Path(td) / "i.json")
            r = h.process_decision(day=b["day"], m5=b["m5"], h1=b["h1"], ticks_by_bar=b["ticks_by_bar"], idx=5)
            self.assertTrue(r.get("rejected"))


class TestRecovery(unittest.TestCase):
    def test_open_position_recovery(self):
        b = _bundle()
        day, m5, h1, by = b["day"], b["m5"], b["h1"], b["ticks_by_bar"]
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "rec.json"
            h1e = VerificationHarness(
                policy=EngineeringTestPolicy(["BUY"]),
                state_path=sp,
                defer_exit=True,
            )
            d = h1e.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)
            self.assertTrue(d.get("deferred"))
            self.assertEqual(len(h1e.risk.open_positions), 1)
            h2 = VerificationHarness(policy=EngineeringTestPolicy(["WAIT"]), state_path=sp)
            out = h2.continue_open_to_exit(day=day, m5=m5, ticks_by_bar=by)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["closed"]["status"], "CLOSED")
            self.assertTrue(out[0]["compare"]["ok"])
            self.assertEqual(len(h2.risk.open_positions), 0)
            self.assertTrue(h2.process_decision(day=day, m5=m5, h1=h1, ticks_by_bar=by, idx=48)["skipped"])


class TestIndependent(unittest.TestCase):
    def test_recompute_buy_sell_rules(self):
        entry = [{"bid": 100.0, "ask": 100.2}]
        exit_ = [{"bid": 100.5, "ask": 100.7}]
        buy = recompute_from_ticks(side="BUY", entry_ticks=entry, exit_ticks=exit_, atr=1.0, stop_distance=1.0)
        self.assertEqual(buy["entry_fill"], 100.2)
        self.assertEqual(buy["exit_fill"], 100.5)
        sell = recompute_from_ticks(side="SELL", entry_ticks=entry, exit_ticks=exit_, atr=1.0, stop_distance=1.0)
        self.assertEqual(sell["entry_fill"], 100.0)
        self.assertEqual(sell["exit_fill"], 100.7)


class TestIsolation(unittest.TestCase):
    def test_harness_does_not_change_production_counts(self):
        before = production_counts()
        b = _bundle()
        with tempfile.TemporaryDirectory() as td:
            # Use harness which writes to phase55 test dirs (not temp — by design)
            # Snapshot counts around a process that uses test stores
            h = VerificationHarness(
                policy=EngineeringTestPolicy(["WAIT"]),
                state_path=Path(td) / "iso.json",
            )
            h.process_decision(day=b["day"], m5=b["m5"], h1=b["h1"], ticks_by_bar=b["ticks_by_bar"], idx=72)
        after = production_counts()
        self.assertEqual(before["hist_n"], after["hist_n"])
        self.assertEqual(before["shadow_n"], after["shadow_n"])
        self.assertIn("phase55", str(h.shadow.path).replace("\\", "/").lower())


if __name__ == "__main__":
    unittest.main()
