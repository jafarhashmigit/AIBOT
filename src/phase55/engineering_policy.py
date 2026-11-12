"""Deterministic EngineeringTestPolicy — Phase55 only; never production default."""

from __future__ import annotations

from typing import Any

from phase55.constants import ENGINEERING_POLICY_VERSION, ENGINEERING_TAG


class EngineeringTestPolicy:
    """
    Explicit test-only policy. Configurable action sequence. No predictive claim.
    """

    version = ENGINEERING_POLICY_VERSION

    def __init__(self, sequence: list[str] | None = None):
        seq = sequence or ["BUY", "SELL", "WAIT"]
        for a in seq:
            if a not in ("BUY", "SELL", "WAIT"):
                raise ValueError(f"invalid test action: {a}")
        self.sequence = list(seq)
        self._i = 0

    def reset(self) -> None:
        self._i = 0

    def propose(
        self,
        market_state: dict[str, Any],
        features: dict[str, Any],
        model_output: dict[str, Any] | None,
        risk_state: dict[str, Any],
    ) -> dict[str, Any]:
        if self._i >= len(self.sequence):
            action = "WAIT"
            reason = "SEQUENCE_EXHAUSTED_WAIT"
        else:
            action = self.sequence[self._i]
            self._i += 1
            reason = f"ENGINEERING_SEQUENCE_{action}"
        return {
            "action": action,
            "expected_net_r": None,
            "prob_positive": None,
            "calibrated": False,
            "confidence": None,
            "uncertainty": 1.0,
            "reason_codes": [ENGINEERING_TAG, "NO_PREDICTIVE_SKILL", reason],
        }
