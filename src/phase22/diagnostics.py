"""Rich per-candle diagnostics for Phase 22 (frozen thresholds unchanged)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from phase22.constants import FROZEN_WF3_CUTS, SELECTED_HORIZON_DISPLAY


DIAG_FIELDS = [
    "decision_id",
    "bar_open_timestamp_utc",
    "bar_close_timestamp_utc",
    "candle_timestamp_pkt",
    "open",
    "high",
    "low",
    "close",
    "h1_trend",
    "close_to_ema_20",
    "ema_9_20_spread",
    "frozen_close_ema_low",
    "frozen_close_ema_high",
    "buy_pullback",
    "sell_extension",
    "spread_gt_0",
    "spread_lt_0",
    "buy_condition",
    "sell_condition",
    "experimental_action",
    "wait_reason",
    "final_action",
    "data_quality_status",
    "pending_outcomes",
    "completed_outcomes_at_decision",
    "selected_horizon",
    "campaign_id",
    "session_id",
]


def build_condition_diagnostics(pred: dict[str, Any]) -> dict[str, Any]:
    cuts = FROZEN_WF3_CUTS
    feat = pred.get("feature_snapshot") or {}
    h1 = pred.get("h1_context") or {}
    try:
        c2e = float(feat.get("close_to_ema_20")) if feat else None
        spread = float(feat.get("ema_9_20_spread")) if feat else None
    except (TypeError, ValueError):
        c2e = None
        spread = None
    h1_trend = h1.get("h1_trend") if h1 else None
    buy_pullback = c2e is not None and c2e <= float(cuts["close_ema_low"])
    sell_ext = c2e is not None and c2e >= float(cuts["close_ema_high"])
    spread_gt = spread is not None and spread > 0
    spread_lt = spread is not None and spread < 0
    buy_cond = h1_trend == "up" and buy_pullback and spread_gt
    sell_cond = h1_trend == "down" and sell_ext and spread_lt
    return {
        "h1_trend": h1_trend or "",
        "close_to_ema_20": "" if c2e is None else f"{c2e:.12f}",
        "ema_9_20_spread": "" if spread is None else f"{spread:.12f}",
        "frozen_close_ema_low": f"{float(cuts['close_ema_low']):.12f}",
        "frozen_close_ema_high": f"{float(cuts['close_ema_high']):.12f}",
        "buy_pullback": buy_pullback,
        "sell_extension": sell_ext,
        "spread_gt_0": spread_gt,
        "spread_lt_0": spread_lt,
        "buy_condition": buy_cond,
        "sell_condition": sell_cond,
        "selected_horizon": SELECTED_HORIZON_DISPLAY,
    }


class DiagnosticJournal:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.root / "observation_diagnostics.csv"
        self.jsonl_path = self.root / "observation_diagnostics.jsonl"

    def append(self, row: dict[str, Any]) -> None:
        flat = {k: row.get(k, "") for k in DIAG_FIELDS}
        write_header = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=DIAG_FIELDS, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow(flat)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def rows(self) -> list[dict[str, Any]]:
        if not self.csv_path.is_file():
            return []
        with self.csv_path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
