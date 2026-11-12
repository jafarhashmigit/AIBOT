"""Kill switch model — blocks new submissions immediately; design-only (always blocks in 64.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class KillSwitch:
    """
    Operational kill switch. In Phase64.4 the switch defaults to ENGAGED (blocking).
    Disengage requires explicit method call with reason — still does not enable order_send.
    """

    state: str = "ENGAGED"
    reason: str = "phase64_4_default_engaged"
    history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.history.append({"at": _utc(), "state": self.state, "reason": self.reason})

    @property
    def blocks_submission(self) -> bool:
        return self.state != "DISENGAGED"

    def engage(self, *, reason: str) -> None:
        self.state = "ENGAGED"
        self.reason = reason
        self.history.append({"at": _utc(), "state": self.state, "reason": reason})

    def disengage(self, *, reason: str) -> None:
        """
        Design note: even when DISENGAGED, Phase64.4 authorization gate still requires
        all other gates + human approval, and SUBMISSION_PATH_EXISTS remains False.
        """
        self.state = "DISENGAGED"
        self.reason = reason
        self.history.append({"at": _utc(), "state": self.state, "reason": reason})

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "blocks_submission": self.blocks_submission,
            "reason": self.reason,
            "operational": True,
            "phase64_4_note": "Disengage does not create an order_send path",
        }
