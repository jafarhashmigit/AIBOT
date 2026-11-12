"""Phase 29 forward campaign state with persistent watermark and targets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase29.constants import (
    MIN_BUY_SELL_DECISIONS,
    MIN_FORWARD_CANDLES,
    MIN_MATURED_OUTCOMES,
)


class CampaignStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "campaign_state.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "campaign_id": "phase29_forward_shadow_v1",
                "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "forward_observation_start_utc": None,
                "new_candles_processed": 0,
                "last_candle_close_utc": None,
                "processed_keys": [],
                "batches": [],
                "targets": {
                    "min_forward_candles": MIN_FORWARD_CANDLES,
                    "min_buy_sell_decisions": MIN_BUY_SELL_DECISIONS,
                    "min_matured_outcomes": MIN_MATURED_OUTCOMES,
                },
                "discord_signals_sent": 0,
                "discord_wait_sent": 0,
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def status_view(self) -> dict[str, Any]:
        st = self.load()
        return {
            "campaign_id": st.get("campaign_id"),
            "forward_observation_start_utc": st.get("forward_observation_start_utc"),
            "new_candles_processed": int(st.get("new_candles_processed") or 0),
            "last_candle_close_utc": st.get("last_candle_close_utc"),
            "n_batches": len(st.get("batches") or []),
            "targets": st.get("targets") or {},
            "discord_signals_sent": st.get("discord_signals_sent", 0),
            "discord_wait_sent": st.get("discord_wait_sent", 0),
            "evidence": evidence_status(
                n_candles=int(st.get("new_candles_processed") or 0),
            ),
        }


def evidence_status(
    *,
    n_candles: int = 0,
    n_buy_sell: int = 0,
    n_matured: int = 0,
    n_days: int = 0,
) -> dict[str, Any]:
    gates = {
        "min_forward_candles": MIN_FORWARD_CANDLES,
        "min_buy_sell_decisions": MIN_BUY_SELL_DECISIONS,
        "min_matured_outcomes": MIN_MATURED_OUTCOMES,
    }
    checks = {
        "min_forward_candles": n_candles >= gates["min_forward_candles"],
        "min_buy_sell_decisions": n_buy_sell >= gates["min_buy_sell_decisions"],
        "min_matured_outcomes": n_matured >= gates["min_matured_outcomes"],
    }
    ok = all(checks.values())
    return {
        "status": "EVIDENCE_GATES_MET" if ok else "INSUFFICIENT_FORWARD_EVIDENCE",
        "checks": checks,
        "gates": gates,
        "observed": {
            "n_candles": n_candles,
            "n_buy_sell": n_buy_sell,
            "n_matured": n_matured,
            "n_days": n_days,
        },
    }


def campaign_targets_met(evidence: dict[str, Any]) -> bool:
    return evidence.get("status") == "EVIDENCE_GATES_MET"
