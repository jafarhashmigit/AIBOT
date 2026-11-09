"""Append-only historical hypothetical store. Rejects paper records."""

from __future__ import annotations

from bisect import bisect_left

from phase10.constants import RESEARCH_CUTOFF, SOURCE_HISTORICAL, SOURCE_PAPER
from phase10.historical_schema import (
    HistoricalDecisionFields,
    HistoricalExperience,
    HistoricalOutcomeFields,
)
from phase10.validation import (
    SourceSeparationError,
    TemporalSafetyError,
    historical_id,
    is_visible,
    outcome_end_for,
    require_source,
)


class HistoricalExperienceStore:
    def __init__(self) -> None:
        self._records: list[HistoricalExperience] = []
        self._ends: list[str] = []
        self._ids: set[str] = set()
        self._last_decision_ts: str | None = None

    def __len__(self) -> int:
        return len(self._records)

    def append(self, record: HistoricalExperience) -> None:
        if getattr(record, "source_type", None) == SOURCE_PAPER:
            raise SourceSeparationError("cannot write AGENT_PAPER into HistoricalExperienceStore")
        if not isinstance(record, HistoricalExperience):
            raise SourceSeparationError("HistoricalExperienceStore accepts only HistoricalExperience")
        require_source(record.source_type, SOURCE_HISTORICAL)
        if record.experience_id in self._ids:
            raise SourceSeparationError(f"duplicate historical id {record.experience_id}")
        if record.experience_id.startswith("paper:"):
            raise SourceSeparationError("cross-source identifier collision")
        if self._last_decision_ts is not None and record.decision_timestamp < self._last_decision_ts:
            raise TemporalSafetyError("historical append is not chronological; backdating rejected")
        if record.outcome.outcome_status != "completed":
            raise TemporalSafetyError("incomplete historical outcome cannot be stored")
        if record.outcome_end > RESEARCH_CUTOFF:
            raise TemporalSafetyError("historical outcome_end after cutoff")
        end = record.outcome_end
        if not self._ends or end >= self._ends[-1]:
            self._ends.append(end)
            self._records.append(record)
        else:
            i = bisect_left(self._ends, end)
            self._ends.insert(i, record.outcome_end)
            self._records.insert(i, record)
        self._ids.add(record.experience_id)
        self._last_decision_ts = record.decision_timestamp

    def query(self, as_of: str) -> list[HistoricalExperience]:
        if as_of > RESEARCH_CUTOFF:
            raise TemporalSafetyError("query as_of after cutoff")
        i = bisect_left(self._ends, as_of)
        return list(self._records[:i])

    def inspect(self, as_of: str) -> list[dict]:
        return [r.to_mapping() for r in self.query(as_of)]


def build_historical_experience(pair: dict, eval_row: dict, side: str) -> HistoricalExperience:
    stamp = pair["timestamp"]
    snap = pair["buy"] if side == "BUY" else pair["sell"]
    key_r = f"actual_net_r_{side}"
    key_pnl = f"actual_net_pnl_{side}"
    key_ex = f"actual_exit_reason_{side}"
    decision = HistoricalDecisionFields(
        experience_id=historical_id(stamp, side),
        source_type=SOURCE_HISTORICAL,
        decision_timestamp=stamp,
        side=side,
        fold_id=str(pair["fold_id"]),
        model_id="phase2_rf_oos",
        p_tp_rf=float(snap["p_tp_rf"]),
        p_sl_rf=float(snap["p_sl_rf"]),
        p_time_rf=float(snap["p_time_rf"]),
        pred_r_rf=float(snap["pred_r_rf"]),
        pred_r_ridge=float(snap["pred_r_ridge"]),
        provenance="phase2_oos_predictions.csv",
        hypothetical_entry_reference=None,
    )
    outcome = HistoricalOutcomeFields(
        outcome_end=outcome_end_for(stamp),
        exit_reason=str(eval_row[key_ex]),
        actual_net_r=float(eval_row[key_r]),
        realized_pnl=float(eval_row[key_pnl]),
        outcome_status="completed",
    )
    return HistoricalExperience(decision, outcome)


def load_completed_historical(
    pairs: list[dict],
    eval_rows: list[dict],
    *,
    as_of: str,
) -> tuple[HistoricalExperienceStore, int, int]:
    """Load only hypotheticals whose outcome_end is strictly before as_of. No preload of later rows into retrieval."""
    store = HistoricalExperienceStore()
    ev = {e["timestamp"]: e for e in eval_rows}
    skipped = 0
    max_ts = ""
    for pair in pairs:
        t = pair["timestamp"]
        if t > max_ts:
            max_ts = t
        end = outcome_end_for(t)
        if not is_visible(end, as_of):
            skipped += 2
            continue
        for side in ("BUY", "SELL"):
            store.append(build_historical_experience(pair, ev[t], side))
    return store, skipped, max_ts
