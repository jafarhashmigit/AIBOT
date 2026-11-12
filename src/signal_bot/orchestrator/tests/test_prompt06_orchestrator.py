"""Prompt 6 — signal orchestrator / publication gate / Discord isolation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase54.decision import NullPolicy
from signal_bot.asia_london_mss.constants import HYPOTHESIS_ID
from signal_bot.asia_london_mss.policy import AsiaLondonMssPolicy
from signal_bot.orchestrator.constants import (
    CHAMPION_STATUS,
    DEFAULT_MODE,
    MODE_AUTHORIZED,
    MODE_DRY_RUN,
    MODE_SHADOW,
    ORDER_SEND,
)
from signal_bot.orchestrator.contract import (
    build_signal_event,
    to_pkt,
    validate_signal_event,
)
from signal_bot.orchestrator.delivery import DeliveryLedger, deliver_signal
from signal_bot.orchestrator.formatter import format_signal_message
from signal_bot.orchestrator.gate import effective_operating_mode, evaluate_publication_gate
from signal_bot.orchestrator.orchestrator import SignalOrchestrator


def _buy_event(**kwargs):
    base = dict(
        action="BUY",
        decision_id="dec_buy_1",
        strategy_id=HYPOTHESIS_ID,
        strategy_version="h70_v1",
        entry_reference=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        reward_risk=2.0,
        expiry_utc="2099-01-01T00:00:00Z",
        invalidation="close < SL",
        validation_status="UNVALIDATED",
        risk_check_status="UNAPPROVED",
        evidence_classification="BROKER_OBSERVED_LIVE_BAR",
        market_data_provenance="BROKER_OBSERVED_LIVE_BAR",
        reason_codes=["TEST_BUY"],
        calibrated=False,
    )
    base.update(kwargs)
    return build_signal_event(**base)


class TestContract(unittest.TestCase):
    def test_wait_schema_ok(self):
        e = build_signal_event(
            action="WAIT",
            decision_id="d1",
            strategy_id="NULL_POLICY",
            strategy_version="v1",
            reason_codes=["NO_MODEL"],
        )
        v = validate_signal_event(e)
        self.assertTrue(v["ok"])

    def test_buy_requires_prices(self):
        e = build_signal_event(
            action="BUY",
            decision_id="d1",
            strategy_id="X",
            strategy_version="v1",
        )
        v = validate_signal_event(e)
        self.assertFalse(v["ok"])
        self.assertTrue(any("actionable_missing" in x for x in v["errors"]))

    def test_invalid_buy_order(self):
        e = _buy_event(stop_loss=2010.0, take_profit=1990.0)
        v = validate_signal_event(e)
        self.assertFalse(v["ok"])
        self.assertIn("buy_price_order_invalid", v["errors"])

    def test_uncalibrated_confidence_cleared(self):
        e = _buy_event(confidence=0.9, calibrated=False)
        v = validate_signal_event(e)
        self.assertIsNone(v["event"]["confidence"])

    def test_pkt_formatting(self):
        pkt = to_pkt("2026-11-12T08:00:00Z")
        self.assertIsNotNone(pkt)
        self.assertIn("+05:00", pkt)


class TestPublicationGate(unittest.TestCase):
    def test_h70_blocked(self):
        e = _buy_event()
        g = evaluate_publication_gate(e, mode=MODE_SHADOW)
        self.assertFalse(g["allowed"])
        self.assertTrue(any("H70" in r for r in g["block_reasons"]))

    def test_champion_no_model_blocks(self):
        e = _buy_event(strategy_id="SOME_APPROVED", validation_status="INDEPENDENTLY_VALIDATED")
        g = evaluate_publication_gate(
            e,
            mode=MODE_AUTHORIZED,
            publication_authorization_enabled=True,
            approved_strategies={"SOME_APPROVED"},
            cost_model_status="APPROVED",
            risk_policy_status="APPROVED",
            swap_status="APPROVED",
            margin_status="APPROVED",
        )
        # Still blocked: champion NO_MODEL + discord actionable disabled + risk_check on event
        self.assertFalse(g["allowed"])
        self.assertIn("champion_NO_MODEL_blocks_actionable", g["block_reasons"])

    def test_unknown_cost_blocks(self):
        e = _buy_event(
            strategy_id="X",
            validation_status="INDEPENDENTLY_VALIDATED",
            risk_check_status="APPROVED",
        )
        g = evaluate_publication_gate(
            e,
            champion="X",
            approved_strategies={"X"},
            cost_model_status="UNKNOWN",
            risk_policy_status="APPROVED",
            mode=MODE_AUTHORIZED,
            publication_authorization_enabled=True,
        )
        self.assertIn("cost_model_unknown", g["block_reasons"])

    def test_authorized_mode_clamped(self):
        self.assertEqual(effective_operating_mode(MODE_AUTHORIZED), MODE_SHADOW)

    def test_stale_and_forming(self):
        e = _buy_event(stale=True)
        g = evaluate_publication_gate(e)
        self.assertIn("signal_stale", g["block_reasons"])
        e2 = _buy_event(forming_bar=True)
        g2 = evaluate_publication_gate(e2)
        self.assertIn("forming_bar", g2["block_reasons"])


class TestOrchestrator(unittest.TestCase):
    def test_null_policy_wait(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            orch = SignalOrchestrator(
                policy=NullPolicy(),
                mode=MODE_SHADOW,
                decisions_path=root / "dec.jsonl",
                ledger=DeliveryLedger(root / "led.jsonl"),
            )
            out = orch.process_market_state(
                {
                    "symbol": "XAUUSDm",
                    "timeframe": "M5",
                    "forming_bar": False,
                    "data_quality_status": "OK",
                    "bar_timestamp_utc": "2026-11-12T10:00:00Z",
                }
            )
            self.assertEqual(out["signal"]["direction"], "WAIT")
            self.assertFalse(out["network_called"])
            self.assertEqual(out["mode"], MODE_SHADOW)

    def test_forming_bar_rejected(self):
        orch = SignalOrchestrator(mode=MODE_DRY_RUN)
        out = orch.process_market_state({"symbol": "XAUUSDm", "forming_bar": True, "data_quality_status": "OK"})
        self.assertIn("FORMING_BAR_REJECTED", out["decision"]["reason_codes"])
        self.assertEqual(out["signal"]["direction"], "WAIT")

    def test_stale_rejected(self):
        orch = SignalOrchestrator(mode=MODE_SHADOW)
        out = orch.process_market_state(
            {"symbol": "XAUUSDm", "forming_bar": False, "data_quality_status": "OK", "stale": True}
        )
        self.assertIn("STALE_DATA_REJECTED", " ".join(out["decision"]["reason_codes"]))

    def test_h70_policy_shadow_no_network(self):
        """H70 may propose BUY on synthetic geometry; Discord stays local/blocked."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Minimal market state that won't fire H70 BUY — still WAIT — ensure no network
            orch = SignalOrchestrator(
                policy=AsiaLondonMssPolicy(),
                mode=MODE_SHADOW,
                decisions_path=root / "d.jsonl",
                ledger=DeliveryLedger(root / "l.jsonl"),
            )
            out = orch.process_market_state(
                {
                    "symbol": "XAUUSDm",
                    "timeframe": "M5",
                    "forming_bar": False,
                    "data_quality_status": "OK",
                    "bars": [],
                }
            )
            self.assertFalse(out["network_called"])
            self.assertEqual(out["delivery"].get("status") in {"SHADOW_RECORDED", "DRY_RUN", "BLOCKED_RECORDED", "SKIPPED_DUPLICATE"}, True)

    def test_duplicate_delivery_suppressed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            led = DeliveryLedger(root / "led.jsonl")
            e = _buy_event()
            g = evaluate_publication_gate(e, mode=MODE_SHADOW)
            r1 = deliver_signal(g["event"], mode=MODE_SHADOW, ledger=led, gate_allowed=False)
            r2 = deliver_signal(g["event"], mode=MODE_SHADOW, ledger=led, gate_allowed=False)
            self.assertNotEqual(r1["status"], "SKIPPED_DUPLICATE")
            self.assertEqual(r2["status"], "SKIPPED_DUPLICATE")

    def test_shadow_never_calls_transport(self):
        calls = []

        def boom(url, body, timeout):
            calls.append(1)
            return 200, "ok"

        e = _buy_event()
        g = evaluate_publication_gate(e, mode=MODE_SHADOW)
        with tempfile.TemporaryDirectory() as td:
            led = DeliveryLedger(Path(td) / "l.jsonl")
            deliver_signal(g["event"], mode=MODE_SHADOW, ledger=led, transport=boom, gate_allowed=False)
            deliver_signal(g["event"], mode=MODE_DRY_RUN, ledger=DeliveryLedger(Path(td) / "l2.jsonl"), transport=boom, gate_allowed=False)
        self.assertEqual(calls, [])

    def test_authorized_path_still_blocked_without_gate(self):
        """Even if mode string is AUTHORIZED, effective clamp + gate block network."""
        e = _buy_event()
        mode = effective_operating_mode(MODE_AUTHORIZED)
        self.assertEqual(mode, MODE_SHADOW)
        g = evaluate_publication_gate(e, mode=MODE_AUTHORIZED, publication_authorization_enabled=True)
        self.assertFalse(g["allowed"])

    def test_formatter_non_actionable(self):
        e = _buy_event()
        g = evaluate_publication_gate(e)
        msg = format_signal_message(g["event"], gated=True)
        self.assertIn("NOT", msg["content"].upper())
        self.assertIn("Signal ID", msg["content"])

    def test_secret_redaction_in_delivery_error(self):
        from phase16b.secrets import redact_secrets

        dirty = "fail https://discord.com/api/webhooks/123/abc-secret"
        clean = redact_secrets(dirty)
        self.assertNotIn("abc-secret", clean)
        self.assertIn("REDACTED", clean)

    def test_safety_invariants(self):
        self.assertEqual(CHAMPION_STATUS, "NO_MODEL")
        self.assertEqual(ORDER_SEND, "PROHIBITED")
        self.assertEqual(DEFAULT_MODE, MODE_SHADOW)
        self.assertIn("order_send", PROHIBITED_MT5_API)


class TestRetryIsolation(unittest.TestCase):
    def test_rate_limit_retry_mocked(self):
        from phase16b.client import post_webhook

        attempts = {"n": 0}

        def transport(url, body, timeout):
            attempts["n"] += 1
            if attempts["n"] < 3:
                return 429, "rate"
            return 200, "ok"

        sleeps: list[float] = []
        out = post_webhook(
            "https://discord.com/api/webhooks/x/y",
            {"content": "test"},
            transport=transport,
            sleep_fn=lambda s: sleeps.append(s),
            max_attempts=3,
            backoff=(0.01, 0.01, 0.01),
        )
        self.assertEqual(out["status"], "SENT")
        self.assertEqual(attempts["n"], 3)
        self.assertTrue(sleeps)


if __name__ == "__main__":
    unittest.main()
