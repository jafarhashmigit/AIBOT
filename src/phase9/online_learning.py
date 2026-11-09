"""Expanding-window online updates. No preload. outcome_end < T only."""

from __future__ import annotations

from dataclasses import dataclass

from phase8.experience_schema import outcome_end_for
from phase9.constants import RESEARCH_CUTOFF
from phase9.learner import ExperienceRidge, features_from_pair


@dataclass
class Pending:
    pair: dict
    eval_row: dict
    outcome_end: str


class OnlineLoop:
    def __init__(self, ridge: ExperienceRidge) -> None:
        self.ridge = ridge
        self.pending: list[Pending] = []
        self.completed = 0
        self.fallbacks = 0
        self.fits_available = 0

    def complete_due(self, t: str) -> None:
        still = []
        for item in self.pending:
            if item.outcome_end < t:
                if item.outcome_end > RESEARCH_CUTOFF:
                    raise RuntimeError("HARD FAILURE: training outcome after cutoff")
                feat = features_from_pair(item.pair)
                self.ridge.observe(
                    feat,
                    float(item.eval_row["actual_net_r_BUY"]),
                    float(item.eval_row["actual_net_r_SELL"]),
                    timestamp=item.pair["timestamp"],
                    outcome_end=item.outcome_end,
                )
                self.completed += 1
                if self.ridge.available():
                    if (self.ridge.buy.latest_outcome_end or "") >= t:
                        raise RuntimeError("HARD FAILURE: max_training_outcome_end >= T")
                    if (self.ridge.sell.latest_outcome_end or "") >= t:
                        raise RuntimeError("HARD FAILURE: max_training_outcome_end >= T")
            else:
                still.append(item)
        self.pending = still

    def enqueue(self, pair: dict, eval_row: dict) -> None:
        self.pending.append(Pending(pair, eval_row, outcome_end_for(pair["timestamp"])))
