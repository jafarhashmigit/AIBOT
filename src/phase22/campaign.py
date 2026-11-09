"""Persistent forward-observation campaign state."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase22.constants import CAMPAIGN_TARGET_CANDLES, DATA_DIR

UTC = timezone.utc
STATE_NAME = "campaign_state.json"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def default_campaign_id(created: str | None = None) -> str:
    stamp = (created or _now()).replace(" ", "T").replace(":", "")
    return f"p22_campaign_{stamp}_{uuid.uuid4().hex[:8]}"


class CampaignStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / STATE_NAME

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            raise FileNotFoundError(f"campaign state missing: {self.path}")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def get_or_create(self, *, target: int = CAMPAIGN_TARGET_CANDLES) -> dict[str, Any]:
        if self.path.is_file():
            state = self.load()
            # Never reset existing campaign
            return state
        created = _now()
        state = {
            "campaign_id": default_campaign_id(created),
            "status": "active",
            "target_candles": int(target),
            "observed_candles": 0,
            "remaining_candles": int(target),
            "last_bar_open_utc": "",
            "sessions": [],
            "created_at_utc": created,
            "updated_at_utc": created,
            "buy_count": 0,
            "sell_count": 0,
            "wait_count": 0,
            "discord_signals_sent": 0,
            "rejected_incomplete": 0,
            "rejected_duplicate": 0,
            "note": "observation target only — not a BUY/SELL guarantee",
        }
        self.save(state)
        return state

    def record_session(
        self,
        *,
        session_id: str,
        candles: int,
        buy: int,
        sell: int,
        wait: int,
        last_bar_open_utc: str,
        discord_sent: int,
        rejected_incomplete: int = 0,
        rejected_duplicate: int = 0,
        started_at_utc: str = "",
        stopped_at_utc: str = "",
    ) -> dict[str, Any]:
        state = self.get_or_create()
        state["observed_candles"] = int(state.get("observed_candles", 0)) + int(candles)
        target = int(state.get("target_candles", CAMPAIGN_TARGET_CANDLES))
        state["remaining_candles"] = max(0, target - int(state["observed_candles"]))
        state["buy_count"] = int(state.get("buy_count", 0)) + int(buy)
        state["sell_count"] = int(state.get("sell_count", 0)) + int(sell)
        state["wait_count"] = int(state.get("wait_count", 0)) + int(wait)
        state["discord_signals_sent"] = int(state.get("discord_signals_sent", 0)) + int(discord_sent)
        state["rejected_incomplete"] = int(state.get("rejected_incomplete", 0)) + int(rejected_incomplete)
        state["rejected_duplicate"] = int(state.get("rejected_duplicate", 0)) + int(rejected_duplicate)
        if last_bar_open_utc:
            state["last_bar_open_utc"] = last_bar_open_utc
        state["updated_at_utc"] = _now()
        if state["observed_candles"] >= target:
            state["status"] = "target_reached"
        sessions = list(state.get("sessions") or [])
        sessions.append(
            {
                "session_id": session_id,
                "candles": candles,
                "BUY": buy,
                "SELL": sell,
                "WAIT": wait,
                "discord_signals_sent": discord_sent,
                "started_at_utc": started_at_utc,
                "stopped_at_utc": stopped_at_utc,
            }
        )
        state["sessions"] = sessions
        self.save(state)
        return state

    def status_view(self) -> dict[str, Any]:
        if not self.exists():
            return {
                "campaign_exists": False,
                "campaign_id": None,
                "target_candles": CAMPAIGN_TARGET_CANDLES,
                "observed_candles": 0,
                "remaining_candles": CAMPAIGN_TARGET_CANDLES,
                "sessions": 0,
                "note": "No campaign started yet. Use --run-bounded to begin a session.",
            }
        state = self.load()
        return {
            "campaign_exists": True,
            "campaign_id": state.get("campaign_id"),
            "status": state.get("status"),
            "target_candles": state.get("target_candles"),
            "observed_candles": state.get("observed_candles"),
            "remaining_candles": state.get("remaining_candles"),
            "last_bar_open_utc": state.get("last_bar_open_utc"),
            "sessions": len(state.get("sessions") or []),
            "BUY": state.get("buy_count", 0),
            "SELL": state.get("sell_count", 0),
            "WAIT": state.get("wait_count", 0),
            "discord_signals_sent": state.get("discord_signals_sent", 0),
            "updated_at_utc": state.get("updated_at_utc"),
            "mt5_started": False,
            "note": state.get("note"),
        }
