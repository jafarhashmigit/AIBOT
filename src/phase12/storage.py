"""Append-safe Phase 12 CSV storage. Never writes Phase 1–11 datasets."""

from __future__ import annotations

from pathlib import Path

from phase3.nplib import read_csv_dicts, write_csv_dicts
from phase12.outcome_observer import observe_outcome
from phase12.validation import DATA_DIR, SRC_DIR, ShadowError

OBS_FIELDS = [
    "observation_id", "source_type", "symbol", "timeframe",
    "bar_open_timestamp_utc", "bar_close_timestamp_utc", "observation_created_at_utc",
    "open", "high", "low", "close", "tick_volume", "spread",
    "data_source", "data_quality_status", "gap_status", "model_status",
    "feature_snapshot_reference", "source_timezone", "conversion", "source_stamp",
    "decision_id",
]
DEC_FIELDS = [
    "decision_id", "observation_id", "source_type", "decision_timestamp_utc",
    "symbol", "timeframe", "model_id", "model_status", "raw_action",
    "risk_gate_result", "final_action", "decision_reason", "outcome_status",
    "is_paper_trade", "is_paper_execution", "note",
]
OUT_FIELDS = [
    "decision_id", "source_type", "outcome_start_timestamp", "outcome_end_timestamp",
    "observed_future_bars", "future_high", "future_low", "future_close",
    "outcome_completeness", "gap_detected", "outcome_status",
    "hypothetical_counterfactual", "note",
]
SES_FIELDS = [
    "session_id", "status", "started_at_utc", "stopped_at_utc", "mode",
    "mt5_connected", "error", "notes",
]


class ShadowStore:
    def __init__(self, root=DATA_DIR, *, read_only: bool = False) -> None:
        self.root = Path(root)
        self.read_only = bool(read_only)
        if not self.read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        self.obs_path = self.root / "shadow_observations.csv"
        self.dec_path = self.root / "shadow_decisions.csv"
        self.out_path = self.root / "shadow_outcomes.csv"
        self.ses_path = self.root / "shadow_sessions.csv"
        self._obs = self._load(self.obs_path)
        self._dec = self._load(self.dec_path)
        self._out = self._load(self.out_path)
        self._ses = self._load(self.ses_path)
        self._obs_ids = {r["observation_id"] for r in self._obs}
        self._dec_ids = {r["decision_id"] for r in self._dec}
        self._open_ts = {r["bar_open_timestamp_utc"] for r in self._obs}

    def _load(self, path) -> list[dict]:
        if not path.exists() or path.stat().st_size == 0:
            return []
        return read_csv_dicts(path)

    def _assert_write_isolated(self, path) -> None:
        if self.read_only:
            raise ShadowError("read-only store cannot write")
        resolved = Path(path).resolve()
        data_root = (SRC_DIR / "data").resolve()
        try:
            resolved.relative_to(data_root)
        except ValueError:
            return
        try:
            resolved.relative_to(DATA_DIR.resolve())
        except ValueError:
            raise ShadowError(f"refusing write outside src/data/phase12: {resolved}")

    def _save(self, path, rows, fields) -> None:
        self._assert_write_isolated(path)
        write_csv_dicts(path, rows, fieldnames=fields)

    def last_open_utc(self) -> str | None:
        if not self._obs:
            return None
        return max(r["bar_open_timestamp_utc"] for r in self._obs)

    def append_observation(self, row: dict) -> None:
        if row["observation_id"] in self._obs_ids:
            raise ShadowError("duplicate observation_id")
        if row["bar_open_timestamp_utc"] in self._open_ts:
            raise ShadowError("duplicate timestamp")
        self._obs.append(row)
        self._obs_ids.add(row["observation_id"])
        self._open_ts.add(row["bar_open_timestamp_utc"])
        self._save(self.obs_path, self._obs, OBS_FIELDS)

    def append_decision(self, row: dict) -> None:
        if row["decision_id"] in self._dec_ids:
            raise ShadowError("duplicate decision_id")
        if row.get("is_paper_trade") in {True, "True", "true"}:
            raise ShadowError("shadow decision cannot be a paper trade")
        self._dec.append(row)
        self._dec_ids.add(row["decision_id"])
        self._save(self.dec_path, self._dec, DEC_FIELDS)

    def upsert_outcome(self, row: dict) -> None:
        existing = {r["decision_id"]: i for i, r in enumerate(self._out)}
        if row["decision_id"] in existing:
            self._out[existing[row["decision_id"]]] = row
        else:
            self._out.append(row)
        self._save(self.out_path, self._out, OUT_FIELDS)

    def append_session(self, row: dict) -> None:
        self._ses.append(row)
        self._save(self.ses_path, self._ses, SES_FIELDS)

    def observations(self) -> list[dict]:
        return list(self._obs)

    def decisions(self) -> list[dict]:
        return list(self._dec)

    def outcomes(self) -> list[dict]:
        return list(self._out)

    def refresh_outcomes(self, as_of_utc: str) -> None:
        bars = [
            {
                "bar_open_timestamp_utc": r["bar_open_timestamp_utc"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
            }
            for r in self._obs
        ]
        for dec in self._dec:
            result = observe_outcome(dec, bars, as_of_utc=as_of_utc)
            self.upsert_outcome(result)
            dec["outcome_status"] = result["outcome_status"]
        self._save(self.dec_path, self._dec, DEC_FIELDS)
