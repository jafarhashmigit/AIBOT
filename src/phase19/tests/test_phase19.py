"""Deterministic Phase 19 synthetic shadow-outcome pipeline validation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from phase18.barrier import BUY, SELL, market_arrays_from_bars, simulate_trade_horizon
from phase18.constants import HORIZON_LABELS, HORIZONS
from phase18.daily_report import aggregate_daily
from phase18.experience import ExperienceStore
from phase18.horizons import expected_outcome_check_utc
from phase18.outcomes import create_pending_outcomes
from phase18.store import Phase18Store
from phase19.constants import (
    BROKER_ORDERS,
    CANDIDATE_STATUS,
    CHAMPION_STATUS,
    FORBIDDEN_PHRASES,
    HOLDOUT_ACCESSES,
    SOURCE_HISTORICAL,
    SOURCE_SHADOW,
    SYNTHETIC_NAMESPACE,
    SYNTHETIC_NOT_REAL,
    SYNTHETIC_SIGNAL_BANNER,
)
from phase19.fixtures import build_scenario, expected_status_for_kind
from phase19.integrity import integrity_report, verify_protected_hashes
from phase19.mock_discord import MockDiscordClient
from phase19.pipeline import (
    journal_synthetic_signal,
    resume_after_interrupt,
    run_scenario_lifecycle,
    seed_historical_control,
    synthetic_root,
)
from phase19.synthetic_messages import (
    assert_no_guarantee_language,
    build_synthetic_signal_payload,
)


class Phase19Tests(unittest.TestCase):
    def test_01_buy_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("BUY_PASS", root=Path(tmp))
            primary = result["primary_h12"]
            self.assertIsNotNone(primary)
            self.assertEqual(primary["status"], "PASS")
            self.assertEqual(primary["exit_reason"], "TP")
            ref = result["reference_trade"]
            self.assertEqual(ref["exit_reason"], "TP")
            self.assertAlmostEqual(float(primary["realized_r"]), float(ref["net_pnl_r"]), places=6)

    def test_02_buy_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("BUY_FAIL", root=Path(tmp))
            primary = result["primary_h12"]
            self.assertEqual(primary["status"], "FAIL")
            self.assertEqual(primary["exit_reason"], "SL")
            ref = result["reference_trade"]
            self.assertAlmostEqual(float(primary["realized_r"]), float(ref["net_pnl_r"]), places=6)

    def test_03_sell_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("SELL_PASS", root=Path(tmp))
            primary = result["primary_h12"]
            self.assertEqual(primary["status"], "PASS")
            self.assertEqual(primary["exit_reason"], "TP")

    def test_04_sell_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("SELL_FAIL", root=Path(tmp))
            primary = result["primary_h12"]
            self.assertEqual(primary["status"], "FAIL")
            self.assertEqual(primary["exit_reason"], "SL")

    def test_05_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("TIMEOUT", root=Path(tmp))
            primary = result["primary_h12"]
            self.assertEqual(primary["status"], "TIMEOUT")
            self.assertEqual(primary["exit_reason"], "TIME")
            self.assertEqual(result["outcome_counts"]["TIMEOUT"], 5)
            self.assertEqual(result["outcome_counts"]["PASS"], 0)
            self.assertEqual(result["outcome_counts"]["FAIL"], 0)

    def test_06_all_five_horizons(self):
        self.assertEqual(list(HORIZONS.keys()), ["H1", "H2", "H3", "H6", "H12"])
        self.assertEqual(HORIZON_LABELS["H1"], "5M")
        self.assertEqual(HORIZON_LABELS["H2"], "10M")
        self.assertEqual(HORIZON_LABELS["H3"], "15M")
        self.assertEqual(HORIZON_LABELS["H6"], "30M")
        self.assertEqual(HORIZON_LABELS["H12"], "60M")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("BUY_PASS", root=Path(tmp))
            store = Phase18Store(Path(tmp))
            labels = {o["horizon_label"] for o in store.outcomes()}
            self.assertEqual(labels, {"5M", "10M", "15M", "30M", "60M"})
            self.assertEqual(result["outcome_counts"]["PASS"], 5)

    def test_07_horizon_timing(self):
        close = "2026-11-09 12:05:00"
        self.assertEqual(expected_outcome_check_utc(close, "H1"), "2026-11-09 12:10:00")
        self.assertEqual(expected_outcome_check_utc(close, "H2"), "2026-11-09 12:15:00")
        self.assertEqual(expected_outcome_check_utc(close, "H3"), "2026-11-09 12:20:00")
        self.assertEqual(expected_outcome_check_utc(close, "H6"), "2026-11-09 12:35:00")
        self.assertEqual(expected_outcome_check_utc(close, "H12"), "2026-11-09 13:05:00")

    def test_08_09_expected_horizon_formatting(self):
        scenario = build_scenario("BUY_PASS")
        for hid, label in HORIZON_LABELS.items():
            payload = build_synthetic_signal_payload(
                scenario["decision"],
                scenario["observation"],
                expected_horizon_id=hid,
            )
            content = payload["content"]
            self.assertIn(f"Expected Horizon: {label}", content)
            self.assertIn("Expected Outcome Check:", content)
            self.assertIn(SYNTHETIC_SIGNAL_BANNER, content)
            self.assertIn(SYNTHETIC_NOT_REAL, content)
            assert_no_guarantee_language(content)
            for phrase in FORBIDDEN_PHRASES:
                self.assertNotIn(phrase.lower(), content.lower())

    def test_10_11_12_experience_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_scenario_lifecycle("BUY_PASS", root=root)
            run_scenario_lifecycle("BUY_FAIL", root=root)
            # Second scenario same root will add more — use separate for clarity
        with tempfile.TemporaryDirectory() as tmp:
            pass_root = Path(tmp) / "pass"
            fail_root = Path(tmp) / "fail"
            run_scenario_lifecycle("BUY_PASS", root=pass_root)
            run_scenario_lifecycle("BUY_FAIL", root=fail_root)
            pass_exp = ExperienceStore(pass_root).list_shadow()
            fail_exp = ExperienceStore(fail_root).list_shadow()
            self.assertTrue(any(r["outcome"] == "PASS" for r in pass_exp))
            self.assertTrue(any(r["outcome"] == "FAIL" for r in fail_exp))
            self.assertTrue(all(r["source"] == SOURCE_SHADOW for r in pass_exp))
            self.assertTrue(all(r["source"] == SOURCE_SHADOW for r in fail_exp))

    def test_13_historical_shadow_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_scenario_lifecycle("BUY_PASS", root=root)
            seed_historical_control(root)
            exp = ExperienceStore(root)
            self.assertGreater(exp.counts()["agent_shadow"], 0)
            self.assertEqual(exp.counts()["historical_hypothetical"], 1)
            self.assertTrue(all(r["source"] == SOURCE_SHADOW for r in exp.list_shadow()))
            self.assertTrue(all(r["source"] == SOURCE_HISTORICAL for r in exp.list_historical()))

    def test_14_synthetic_real_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = synthetic_root(Path(tmp) / SYNTHETIC_NAMESPACE)
            self.assertIn(SYNTHETIC_NAMESPACE, str(root))
            marker = (root / "NAMESPACE.txt").read_text(encoding="utf-8")
            self.assertIn("SYNTHETIC", marker.upper())
            # Must not write into phase18 production data path
            prod = _SRC / "data" / "phase18"
            before = set(p.name for p in prod.glob("*")) if prod.exists() else set()
            run_scenario_lifecycle("SELL_PASS", root=root)
            after = set(p.name for p in prod.glob("*")) if prod.exists() else set()
            self.assertEqual(before, after)

    def test_15_discord_duplicate_prevention(self):
        client = MockDiscordClient()
        event = {"event_id": "e1", "decision_id": "e1", "message_type": "P19_SYNTH_SIGNAL_BUY"}
        r1 = client.deliver(event, {"content": f"{SYNTHETIC_SIGNAL_BANNER}\n{SYNTHETIC_NOT_REAL}"})
        r2 = client.deliver(event, {"content": f"{SYNTHETIC_SIGNAL_BANNER}\n{SYNTHETIC_NOT_REAL}"})
        self.assertEqual(r1["status"], "MOCK_SENT")
        self.assertEqual(r2["status"], "SKIPPED_DUPLICATE")
        self.assertEqual(len(client.sent), 1)

    def test_16_outcome_duplicate_prevention(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Phase18Store(Path(tmp))
            scenario = build_scenario("BUY_PASS")
            rows = create_pending_outcomes(scenario["decision"], atr=scenario["atr"])
            self.assertEqual(store.append_outcomes(rows), 5)
            self.assertEqual(store.append_outcomes(rows), 0)

    def test_17_restart_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            interrupted = run_scenario_lifecycle("SELL_FAIL", root=root, interrupt_after_signal=True)
            self.assertEqual(interrupted["phase"], "interrupted_after_signal")
            self.assertEqual(len(interrupted["pending"]), 5)
            recovered = resume_after_interrupt(
                root=root,
                bars=interrupted["bars"],
                signal_idx=interrupted["signal_idx"],
                atr=interrupted["atr"],
            )
            self.assertEqual(recovered["pending_remaining"], 0)
            self.assertGreater(recovered["finalized_first"], 0)
            self.assertEqual(recovered["finalized_second"], 0)
            self.assertEqual(recovered["experience_after"], recovered["experience_before"] + recovered["finalized_first"])

    def test_18_19_20_daily_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_scenario_lifecycle("BUY_PASS", root=root)
            # Add a WAIT decision manually
            store = Phase18Store(root)
            wait = {
                "decision_id": "p19_wait",
                "observation_id": "p19_wait_obs",
                "source_type": SYNTHETIC_NAMESPACE,
                "decision_timestamp_utc": store.decisions()[0]["decision_timestamp_utc"],
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "model_id": "no_model",
                "model_status": CHAMPION_STATUS,
                "candidate_id": "H13_C_H1_PULLBACK",
                "candidate_status": CANDIDATE_STATUS,
                "experimental_action": "WAIT",
                "raw_action": "WAIT",
                "risk_gate_result": "ALLOW",
                "final_action": "WAIT",
                "decision_reason": "wait",
                "feature_snapshot_json": "{}",
                "selected_horizon": "NOT ESTABLISHED",
                "outcome_status": "n_a_wait",
                "signal_bar_open_utc": "2026-11-09 11:55:00",
                "atr": "",
                "tp_level": "",
                "sl_level": "",
                "is_paper_trade": False,
                "is_paper_execution": False,
                "note": "synthetic wait",
            }
            store.append_decision(wait)
            # Force one PENDING artificially for exclusion check
            outs = store.outcomes()
            if outs:
                outs[0]["status"] = "PENDING"
                store.upsert_outcome(outs[0])
            from phase18.horizons import pkt_calendar_date, parse_utc

            date_pkt = pkt_calendar_date(parse_utc(store.decisions()[0]["decision_timestamp_utc"]))
            report = aggregate_daily(decisions=store.decisions(), outcomes=store.outcomes(), date_pkt=date_pkt)
            self.assertEqual(report["signals"]["WAIT"], 1)
            self.assertEqual(report["signals"]["BUY"], 1)
            # Pending excluded from pass/fail rate
            self.assertEqual(
                report["performance"]["resolved_pass_fail_n"],
                report["performance"]["pass_n"] + report["performance"]["fail_n"],
            )
            # WAIT not in trade R as a trade — buy R only from resolved buy outcomes
            note = report["note"].lower().replace("/", " ").replace("-", " ")
            self.assertIn("pending excluded", note)
            self.assertIn("wait excluded", note)

    def test_21_22_23_24_production_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_scenario_lifecycle("BUY_PASS", root=Path(tmp))
            self.assertEqual(result["final_action"], "WAIT")
            self.assertEqual(result["champion_status"], "NO_MODEL")
            self.assertEqual(result["candidate_status"], "EXPERIMENTAL")
            self.assertEqual(result["broker_orders"], 0)
            self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
            self.assertEqual(CANDIDATE_STATUS, "EXPERIMENTAL")
            self.assertEqual(BROKER_ORDERS, 0)
            self.assertEqual(HOLDOUT_ACCESSES, 0)

    def test_25_integrity_protected_hashes(self):
        report = verify_protected_hashes()
        self.assertTrue(report["all_ok"], msg=json.dumps({k: v for k, v in report["files"].items() if not v["ok"]}, indent=2))
        integ = integrity_report()
        self.assertEqual(integ["holdout_access_count"], 0)
        self.assertEqual(integ["broker_order_count"], 0)
        self.assertFalse(integ["github_push"])
        self.assertFalse(integ["mt5_started"])

    def test_26_signal_payload_labels_and_sides(self):
        for kind in ("BUY_PASS", "SELL_FAIL"):
            scenario = build_scenario(kind)
            payload = build_synthetic_signal_payload(scenario["decision"], scenario["observation"])
            self.assertIn(SYNTHETIC_SIGNAL_BANNER, payload["content"])
            self.assertIn(SYNTHETIC_NOT_REAL, payload["content"])
            self.assertIn(f"Action: {scenario['decision']['experimental_action']}", payload["content"])
            self.assertIn("Production Action: WAIT", payload["content"])

    def test_27_realized_r_matches_barrier_engine(self):
        scenario = build_scenario("BUY_PASS", horizon_bars=3)
        m = market_arrays_from_bars(scenario["bars"])
        trade = simulate_trade_horizon(
            m, BUY, scenario["signal_idx"], scenario["atr"], horizon_bars=3
        )
        self.assertEqual(trade["exit_reason"], "TP")
        self.assertAlmostEqual(trade["net_pnl_r"], scenario["reference_trade"]["net_pnl_r"], places=6)

    def test_28_journal_before_mock_discord(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Phase18Store(root)
            experience = ExperienceStore(root)
            discord = MockDiscordClient()
            scenario = build_scenario("SELL_PASS")
            out = journal_synthetic_signal(
                store=store,
                experience=experience,
                scenario=scenario,
                discord=discord,
                expected_horizon_id="H1",
            )
            self.assertTrue(out["journaled"])
            self.assertEqual(out["delivery"]["status"], "MOCK_SENT")
            self.assertEqual(out["final_action"], "WAIT")
            self.assertEqual(len(store.pending_outcomes()), 5)


if __name__ == "__main__":
    unittest.main()
