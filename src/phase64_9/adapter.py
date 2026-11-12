"""
Narrow broker submission adapter boundary.

Distinguishes: adapter exists / tested / authorized / submission enabled.
Real order_send path is hard-disabled. BROKER_SUBMISSION_ENABLED is a source constant.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from phase64_9.constants import (
    ADAPTER_VERSION,
    BROKER_EXECUTION_AUTHORIZED,
    BROKER_SUBMISSION_ENABLED,
    FORBIDDEN_AUTH_ENV,
    ORDER_SEND,
    SIMULATED_LABEL,
    canonical_json_sha256,
)


class SubmissionDisabled(RuntimeError):
    pass


class BrokerBackend(Protocol):
    def submit_order(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class SubmitRequest:
    intent_id: str
    decision_id: str
    symbol: str
    direction: str
    volume: float
    price: float
    sl: float
    tp: float
    deviation: int = 20
    magic: int = 0
    comment: str = ""
    filling_mode: int = 1  # FOK


class BrokerExecutionAdapter:
    """
    Production adapter shell.

    States (independent):
    - exists: True (this class)
    - tested: via FakeBrokerBackend unit tests
    - authorized: BROKER_EXECUTION_AUTHORIZED (False)
    - submission_enabled: BROKER_SUBMISSION_ENABLED (False) — NOT env-toggleable
    """

    def __init__(self, backend: BrokerBackend | None = None, *, synthetic: bool = False):
        self.backend = backend
        self.synthetic = synthetic
        self.adapter_version = ADAPTER_VERSION
        # Freeze constants at init — env cannot flip
        self._submission_enabled = bool(BROKER_SUBMISSION_ENABLED)
        self._authorized = bool(BROKER_EXECUTION_AUTHORIZED)

    @property
    def submission_enabled(self) -> bool:
        return self._submission_enabled

    def status(self) -> dict[str, Any]:
        env_attempts = {k: os.environ.get(k) for k in FORBIDDEN_AUTH_ENV if os.environ.get(k) is not None}
        return {
            "adapter_exists": True,
            "adapter_version": ADAPTER_VERSION,
            "adapter_tested": True,  # suite coverage
            "broker_execution_authorized": self._authorized,
            "broker_submission_enabled": self._submission_enabled,
            "order_send": ORDER_SEND,
            "env_cannot_enable_submission": True,
            "env_keys_ignored": list(FORBIDDEN_AUTH_ENV),
            "env_present_ignored": env_attempts,
            "source_constant_BROKER_SUBMISSION_ENABLED": BROKER_SUBMISSION_ENABLED,
        }

    def submit(self, intent: dict[str, Any] | SubmitRequest) -> dict[str, Any]:
        """
        Entry point for future broker submission.
        Always fail-closed while BROKER_SUBMISSION_ENABLED is False.
        Never calls the MT5 order submission API.
        """
        # Re-read env and ignore — prove env cannot authorize
        for k in FORBIDDEN_AUTH_ENV:
            _ = os.environ.get(k)

        if isinstance(intent, SubmitRequest):
            payload = {
                "intent_id": intent.intent_id,
                "decision_id": intent.decision_id,
                "symbol": intent.symbol,
                "direction": intent.direction,
                "volume": intent.volume,
                "price": intent.price,
                "sl": intent.sl,
                "tp": intent.tp,
            }
        else:
            payload = dict(intent)

        if not self._authorized:
            return self._blocked(payload, "broker_execution_not_authorized")

        if not self._submission_enabled:
            return self._blocked(payload, "broker_submission_disabled_hard_constant")

        # Live path would call order_send here — intentionally unreachable
        return self._blocked(payload, "unreachable_live_submit_guard")

    def submit_synthetic(self, intent: dict[str, Any] | SubmitRequest) -> dict[str, Any]:
        """Test-only path through FakeBrokerBackend — never writes genuine broker evidence."""
        if self.backend is None:
            return self._blocked({}, "no_fake_backend", synthetic=True)
        if isinstance(intent, SubmitRequest):
            req = {
                "intent_id": intent.intent_id,
                "decision_id": intent.decision_id,
                "symbol": intent.symbol,
                "direction": intent.direction,
                "volume": intent.volume,
                "price": intent.price,
                "sl": intent.sl,
                "tp": intent.tp,
                "deviation": intent.deviation,
                "magic": intent.magic,
                "comment": intent.comment,
                "filling_mode": intent.filling_mode,
            }
        else:
            req = dict(intent)
        result = self.backend.submit_order(req)
        result = {
            **result,
            "synthetic": True,
            "evidence_label": SIMULATED_LABEL,
            "store": "SYNTHETIC_FIXTURE",
            "not_genuine_broker_evidence": True,
            "order_send_invoked": False,
            "adapter_version": ADAPTER_VERSION,
        }
        result["sha256"] = canonical_json_sha256({k: v for k, v in result.items() if k != "sha256"})
        return result

    def _blocked(self, payload: dict[str, Any], reason: str, **extra: Any) -> dict[str, Any]:
        out = {
            "status": "BLOCKED",
            "reason": reason,
            "fail_closed": True,
            "reached_order_send": False,
            "order_send_invoked": False,
            "broker_submission_enabled": self._submission_enabled,
            "broker_execution_authorized": self._authorized,
            "payload_keys": sorted(payload.keys()),
            "adapter_version": ADAPTER_VERSION,
            **extra,
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out

    def _live_submit(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Intentionally unimplemented live path.
        Must never be called; exists only as architectural documentation of where
        order_send would enter AFTER Phase65+ multi-gate authorization.
        """
        raise SubmissionDisabled(
            "Live order_send path is permanently disabled in Phase64.9; "
            "BROKER_SUBMISSION_ENABLED=False"
        )
