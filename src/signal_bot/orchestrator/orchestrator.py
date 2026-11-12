"""Unified signal orchestration — NullPolicy default; publication gate enforced."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy, decide
from signal_bot.orchestrator.constants import (
    CHAMPION_STATUS,
    DECISIONS_PATH,
    DEFAULT_MODE,
    ORCHESTRATOR_VERSION,
    PRODUCTION_FINAL_ACTION,
    SYMBOL,
    TIMEFRAME,
)
from signal_bot.orchestrator.contract import decision_to_signal_event, validate_signal_event
from signal_bot.orchestrator.delivery import DeliveryLedger, DeliveryQueue, deliver_signal
from signal_bot.orchestrator.gate import effective_operating_mode, evaluate_publication_gate


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


class SignalOrchestrator:
    """
    Consume closed M5 market_state → decide(policy) → validate → gate → deliver(mode).
    Default policy: NullPolicy. Default mode: SHADOW (no Discord network).
    """

    def __init__(
        self,
        *,
        policy: Any | None = None,
        mode: str | None = None,
        decisions_path: Path | None = None,
        ledger: DeliveryLedger | None = None,
        queue: DeliveryQueue | None = None,
        transport: Any | None = None,
    ) -> None:
        self.policy = policy or NullPolicy()
        self.mode = effective_operating_mode(mode)
        self.decisions_path = Path(decisions_path) if decisions_path else DECISIONS_PATH
        self.ledger = ledger or DeliveryLedger()
        self.queue = queue or DeliveryQueue()
        self.transport = transport
        self.stats = {
            "decisions": 0,
            "buy": 0,
            "sell": 0,
            "wait": 0,
            "blocked": 0,
            "delivered_local": 0,
            "network_calls": 0,
            "duplicates": 0,
            "schema_rejects": 0,
        }
        self.last_decision: dict[str, Any] | None = None
        self.last_signal: dict[str, Any] | None = None
        self.last_blocked: dict[str, Any] | None = None
        self.last_delivery: dict[str, Any] | None = None

    def process_market_state(
        self,
        market_state: dict[str, Any],
        *,
        features: dict[str, Any] | None = None,
        risk_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ms = dict(market_state or {})
        # Closed-bar only
        if ms.get("forming_bar") is True:
            return self._forced_wait(ms, reasons=["FORMING_BAR_REJECTED"])
        if str(ms.get("data_quality_status") or "OK") not in {"OK", "ACCEPTED"}:
            return self._forced_wait(ms, reasons=["DATA_QUALITY_WAIT", str(ms.get("data_quality_status"))])
        if ms.get("stale") is True:
            return self._forced_wait(ms, reasons=["STALE_DATA_REJECTED"])

        # Eligible closed observation only
        if ms.get("symbol") and str(ms.get("symbol")) not in {SYMBOL, "XAUUSD"}:
            return self._forced_wait(ms, reasons=["UNEXPECTED_SYMBOL", str(ms.get("symbol"))])

        decision = decide(
            {
                **ms,
                "symbol": ms.get("symbol") or SYMBOL,
                "timeframe": ms.get("timeframe") or TIMEFRAME,
            },
            features or {},
            None,
            risk_state or {},
            policy=self.policy,
        )
        # Record policy proposal; risk remains UNAPPROVED → publication gate blocks Discord.
        # Production final action stays WAIT (never authorizes broker).
        proposed = str(decision.get("action") or "WAIT")
        decision = {
            **decision,
            "proposed_action": proposed,
            "risk_check_status": "UNAPPROVED",
            "authorizes_execution": False,
            "production_action": PRODUCTION_FINAL_ACTION,
            "reason_codes": list(decision.get("reason_codes") or [])
            + (["RISK_POLICY_UNAPPROVED"] if proposed in ("BUY", "SELL") else []),
        }
        return self._finalize(decision, ms)

    def _forced_wait(self, ms: dict[str, Any], *, reasons: list[str]) -> dict[str, Any]:
        decision = decide(
            {**ms, "symbol": ms.get("symbol") or SYMBOL, "timeframe": TIMEFRAME, "forming_bar": ms.get("forming_bar")},
            {},
            None,
            {},
            policy=NullPolicy(),
        )
        decision = {
            **decision,
            "action": "WAIT",
            "reason_codes": list(decision.get("reason_codes") or []) + list(reasons),
            "risk_check_status": "UNAPPROVED",
        }
        return self._finalize(decision, ms)

    def _finalize(self, decision: dict[str, Any], ms: dict[str, Any]) -> dict[str, Any]:
        signal = decision_to_signal_event(decision, market_state=ms)
        schema = validate_signal_event(signal)
        signal = schema["event"]
        if not schema["ok"]:
            self.stats["schema_rejects"] += 1
            signal = {
                **signal,
                "direction": "WAIT",
                "action": "WAIT",
                "reason_codes": list(signal.get("reason_codes") or []) + [f"schema:{e}" for e in schema["errors"]],
            }

        gate = evaluate_publication_gate(signal, mode=self.mode)
        gated_event = gate["event"]

        action = str(gated_event.get("direction") or "WAIT").upper()
        self.stats["decisions"] += 1
        if action == "BUY":
            self.stats["buy"] += 1
        elif action == "SELL":
            self.stats["sell"] += 1
        else:
            self.stats["wait"] += 1
        if gate["status"] == "BLOCKED" and gate["actionable"]:
            self.stats["blocked"] += 1
            self.last_blocked = {
                "signal_id": gated_event.get("signal_id"),
                "reasons": gate["block_reasons"],
                "at": _utc(),
            }

        delivery = deliver_signal(
            gated_event,
            mode=self.mode,
            ledger=self.ledger,
            queue=self.queue,
            transport=self.transport,
            gate_allowed=bool(gate["allowed"]),
        )
        if delivery.get("status") == "SKIPPED_DUPLICATE":
            self.stats["duplicates"] += 1
        if delivery.get("network_called"):
            self.stats["network_calls"] += 1
        else:
            self.stats["delivered_local"] += 1

        record = {
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "recorded_utc": _utc(),
            "mode": self.mode,
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "decision": {
                "decision_id": decision.get("decision_id"),
                "action": decision.get("action"),
                "proposed_action": decision.get("proposed_action"),
                "reason_codes": decision.get("reason_codes"),
                "policy": getattr(self.policy, "version", None),
            },
            "signal": gated_event,
            "gate": {
                "status": gate["status"],
                "allowed": gate["allowed"],
                "block_reasons": gate["block_reasons"],
            },
            "delivery": {
                "status": delivery.get("status"),
                "network_called": delivery.get("network_called"),
                "dedupe_key": delivery.get("dedupe_key"),
            },
        }
        _append(self.decisions_path, record)
        self.last_decision = record["decision"]
        self.last_signal = gated_event
        self.last_delivery = delivery
        return {
            "ok": True,
            "decision": decision,
            "signal": gated_event,
            "gate": gate,
            "delivery": delivery,
            "mode": self.mode,
            "network_called": bool(delivery.get("network_called")),
        }

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "mode": self.mode,
            "active_policy": getattr(self.policy, "version", type(self.policy).__name__),
            "champion": CHAMPION_STATUS,
            "production": PRODUCTION_FINAL_ACTION,
            "publication_gate": "ENFORCING",
            "stats": dict(self.stats),
            "last_decision": self.last_decision,
            "last_signal_id": (self.last_signal or {}).get("signal_id"),
            "last_signal_direction": (self.last_signal or {}).get("direction"),
            "last_blocked": self.last_blocked,
            "pending_delivery_count": self.queue.pending_count(),
            "discord_actionable_publication": "DISABLED",
        }
