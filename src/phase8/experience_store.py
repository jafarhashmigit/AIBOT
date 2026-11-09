"""Append-only experience store. Retrieval is strictly outcome_end < T."""

from __future__ import annotations

from bisect import bisect_left

from phase8.constants import RESEARCH_CUTOFF
from phase8.experience_schema import ExperienceRecord, ExperienceSummary


class ExperienceStoreError(ValueError):
    pass


class ExperienceStore:
    def __init__(self) -> None:
        self._records: list[ExperienceRecord] = []
        self._ends: list[str] = []
        self._n_buy = 0
        self._n_sell = 0
        self._n_wait = 0
        self._selected: list[float] = []
        self._latest_end: str | None = None

    def __len__(self) -> int:
        return len(self._records)

    def append(self, record: ExperienceRecord) -> None:
        if record.outcome_fields is None:
            raise ExperienceStoreError("cannot append an incomplete experience")
        if record.outcome_end > RESEARCH_CUTOFF:
            raise ExperienceStoreError("outcome_end exceeds research cutoff")
        if record.timestamp > RESEARCH_CUTOFF:
            raise ExperienceStoreError("decision timestamp exceeds cutoff")
        if not self._ends or record.outcome_end >= self._ends[-1]:
            self._ends.append(record.outcome_end)
            self._records.append(record)
        else:
            i = bisect_left(self._ends, record.outcome_end)
            self._ends.insert(i, record.outcome_end)
            self._records.insert(i, record)
        action = record.decision_time_fields.final_decision
        if action == "BUY":
            self._n_buy += 1
        elif action == "SELL":
            self._n_sell += 1
        else:
            self._n_wait += 1
        sel = record.outcome_fields.selected_realized_r
        if sel is not None:
            self._selected.append(sel)
        if self._latest_end is None or record.outcome_end > self._latest_end:
            self._latest_end = record.outcome_end

    def query(self, decision_time: str) -> list[ExperienceRecord]:
        """Experiences whose outcome completed strictly before decision_time."""
        if decision_time > RESEARCH_CUTOFF:
            raise ExperienceStoreError("query timestamp exceeds cutoff")
        i = bisect_left(self._ends, decision_time)
        return self._records[:i]

    def inspect(self, decision_time: str) -> list[dict]:
        return [r.to_mapping() for r in self.query(decision_time)]

    def _summarize(self, rows: list[ExperienceRecord], decision_time: str) -> ExperienceSummary:
        actions = [r.decision_time_fields.final_decision for r in rows]
        selected = [
            r.outcome_fields.selected_realized_r
            for r in rows
            if r.outcome_fields.selected_realized_r is not None
        ]
        n_win = sum(1 for v in selected if v > 0)
        n_loss = sum(1 for v in selected if v <= 0)
        mean_r = (sum(selected) / len(selected)) if selected else None
        median_r = None
        if selected:
            ordered = sorted(selected)
            mid = len(ordered) // 2
            median_r = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        latest = max((r.outcome_end for r in rows), default=None)
        return ExperienceSummary(
            n=len(rows),
            n_buy=sum(1 for a in actions if a == "BUY"),
            n_sell=sum(1 for a in actions if a == "SELL"),
            n_wait=sum(1 for a in actions if a == "WAIT"),
            mean_selected_r=mean_r,
            median_selected_r=median_r,
            n_win=n_win,
            n_loss=n_loss,
            latest_outcome_end=latest,
            as_of=decision_time,
        )

    def summary(self, decision_time: str) -> ExperienceSummary:
        if decision_time > RESEARCH_CUTOFF:
            raise ExperienceStoreError("query timestamp exceeds cutoff")
        i = bisect_left(self._ends, decision_time)
        if i == len(self._records):
            selected = self._selected
            n_win = sum(1 for v in selected if v > 0)
            n_loss = sum(1 for v in selected if v <= 0)
            mean_r = (sum(selected) / len(selected)) if selected else None
            median_r = None
            if selected:
                ordered = sorted(selected)
                mid = len(ordered) // 2
                median_r = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
            return ExperienceSummary(
                n=i,
                n_buy=self._n_buy,
                n_sell=self._n_sell,
                n_wait=self._n_wait,
                mean_selected_r=mean_r,
                median_selected_r=median_r,
                n_win=n_win,
                n_loss=n_loss,
                latest_outcome_end=self._latest_end,
                as_of=decision_time,
            )
        return self._summarize(self._records[:i], decision_time)

    def snapshot_ids(self) -> tuple[str, ...]:
        return tuple(r.decision_time_fields.experience_id for r in self._records)
