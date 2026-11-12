"""Campaign state for Phase 28 forward batches."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase28.constants import CAMPAIGN_TARGET_CANDLES, EVIDENCE_GATES


class CampaignStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "campaign_state.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "campaign_id": "phase28_forward_shadow_v1",
                "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "new_candles_processed": 0,
                "last_candle_close_utc": None,
                "processed_keys": [],
                "target_candles": CAMPAIGN_TARGET_CANDLES,
                "batches": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def status_view(self) -> dict[str, Any]:
        st = self.load()
        n = int(st.get("new_candles_processed") or 0)
        return {
            "campaign_id": st.get("campaign_id"),
            "new_candles_processed": n,
            "target_candles": st.get("target_candles"),
            "last_candle_close_utc": st.get("last_candle_close_utc"),
            "forward_observation_start_utc": st.get("forward_observation_start_utc"),
            "n_batches": len(st.get("batches") or []),
            "evidence_status": evidence_status(n_candles=n),
        }


def evidence_status(
    *,
    n_candles: int = 0,
    n_baseline_decisions: int = 0,
    n_high_accepted: int = 0,
    n_matured_h12: int = 0,
    n_days: int = 0,
) -> dict[str, Any]:
    gates = EVIDENCE_GATES
    checks = {
        "min_new_forward_candles": n_candles >= gates["min_new_forward_candles"],
        "min_baseline_buy_sell_decisions": n_baseline_decisions >= gates["min_baseline_buy_sell_decisions"],
        "min_high_only_accepted_decisions": n_high_accepted >= gates["min_high_only_accepted_decisions"],
        "min_matured_outcomes_h12": n_matured_h12 >= gates["min_matured_outcomes_h12"],
        "min_distinct_trading_days": n_days >= gates["min_distinct_trading_days"],
    }
    ok = all(checks.values())
    return {
        "status": "EVIDENCE_GATES_MET" if ok else "INSUFFICIENT_FORWARD_EVIDENCE",
        "checks": checks,
        "gates": gates,
        "observed": {
            "n_candles": n_candles,
            "n_baseline_decisions": n_baseline_decisions,
            "n_high_accepted": n_high_accepted,
            "n_matured_h12": n_matured_h12,
            "n_days": n_days,
        },
    }
