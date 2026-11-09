"""Read-only dual-source summaries. Never merges raw records. Never decides."""

from __future__ import annotations

from phase10.constants import RESEARCH_CUTOFF, SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_store import HistoricalExperienceStore
from phase10.paper_store import PaperExperienceStore
from phase10.validation import TemporalSafetyError


class ExperienceIntelligence:
    def __init__(
        self,
        historical: HistoricalExperienceStore,
        paper: PaperExperienceStore,
    ) -> None:
        self._historical = historical
        self._paper = paper

    def summary(self, as_of: str) -> dict:
        if as_of > RESEARCH_CUTOFF:
            raise TemporalSafetyError("intelligence as_of after cutoff")
        hist_rows = self._historical.query(as_of)
        buy = [r for r in hist_rows if r.decision.side == "BUY"]
        sell = [r for r in hist_rows if r.decision.side == "SELL"]
        hist_r = [r.outcome.actual_net_r for r in hist_rows]
        hist_latest = max((r.outcome_end for r in hist_rows), default=None)
        paper_completed = self._paper.query_completed(as_of)
        paper_r = [row["outcome"]["simulated_realized_r"] for row in paper_completed]
        paper_latest = max((row["outcome"]["simulated_exit_timestamp"] for row in paper_completed), default=None)
        return {
            "historical": {
                "source_type": SOURCE_HISTORICAL,
                "record_count": len(hist_rows),
                "buy_count": len(buy),
                "sell_count": len(sell),
                "completed_count": len(hist_rows),
                "mean_net_r": (sum(hist_r) / len(hist_r)) if hist_r else None,
                "latest_outcome_end": hist_latest,
                "note": "hypothetical BUY/SELL paths — not agent paper trades",
            },
            "paper": {
                "source_type": SOURCE_PAPER,
                "record_count": len(paper_completed),
                "decision_count": self._paper.decision_count(),
                "trade_count": self._paper.trade_count(),
                "completed_count": len(paper_completed),
                "mean_net_r": (sum(paper_r) / len(paper_r)) if paper_r else None,
                "latest_outcome_end": paper_latest,
                "note": "agent paper journal; WAIT/BLOCKED never become trades",
            },
            "as_of": as_of,
            "merged_raw_records": False,
            "makes_trading_decisions": False,
            "risk_gate_modified": False,
        }

    def historical_completed(self, as_of: str) -> list[dict]:
        return self._historical.inspect(as_of)

    def paper_completed(self, as_of: str) -> list[dict]:
        return self._paper.query_completed(as_of)

    def assert_read_only(self) -> None:
        if hasattr(self, "append") or hasattr(self, "write") or hasattr(self, "record_decision"):
            raise TemporalSafetyError("intelligence interface must not write")


def load_paper_decisions_from_phase9(rows: list[dict], store: PaperExperienceStore) -> str:
    """Journal Phase 9 replay decisions as paper decisions. Does not open trades."""
    from phase10.paper_schema import PaperDecision
    from phase10.validation import paper_decision_id

    max_ts = ""
    for row in rows:
        t = row["timestamp"]
        if t > max_ts:
            max_ts = t
        raw = str(row["raw_decision"])
        final = str(row["final_decision"])
        gate = str(row.get("gate_status") or "")
        if gate not in {"ALLOW", "BLOCK"}:
            gate = "ALLOW" if final == "WAIT" and raw == "WAIT" else "BLOCK"
        pred_buy = row.get("pred_buy")
        pred_sell = row.get("pred_sell")
        decision = PaperDecision(
            decision_id=paper_decision_id(t),
            source_type=SOURCE_PAPER,
            decision_timestamp=t,
            market_symbol="XAUUSD",
            timeframe="M5",
            model_id="phase9_experience_ridge_v1",
            expected_buy_r=None if pred_buy in ("", None) else float(pred_buy),
            expected_sell_r=None if pred_sell in ("", None) else float(pred_sell),
            uncertainty_buy=0.0,
            uncertainty_sell=0.0,
            raw_proposed_action=raw,
            risk_gate_result=gate,
            final_action=final,
            decision_status="journaled_wait_only_gate",
            provenance="phase9_replay_log.csv",
        )
        store.record_decision(decision)
    return max_ts
