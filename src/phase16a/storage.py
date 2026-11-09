"""Dedicated Phase 16A shadow storage under src/data/phase16a."""

from __future__ import annotations

import csv
from pathlib import Path

from phase12.outcome_observer import observe_outcome
from phase16a.constants import DATA_DIR, SRC_DIR, SOURCE_TYPE

OBS_FIELDS = [
    "observation_id", "source_type", "symbol", "timeframe",
    "bar_open_timestamp_utc", "bar_close_timestamp_utc", "observation_created_at_utc",
    "open", "high", "low", "close", "tick_volume", "spread",
    "data_source", "data_quality_status", "gap_status", "model_status",
    "feature_snapshot_reference", "source_timezone", "conversion", "source_stamp",
    "decision_id", "candidate_id", "candidate_status", "market_regime",
]
DEC_FIELDS = [
    "decision_id", "observation_id", "source_type", "decision_timestamp_utc",
    "symbol", "timeframe", "model_id", "model_status", "candidate_id",
    "candidate_status", "experimental_action", "raw_action",
    "risk_gate_result", "final_action", "decision_reason", "feature_snapshot_json",
    "outcome_status", "is_paper_trade", "is_paper_execution", "note",
]
OUT_FIELDS = [
    "decision_id", "source_type", "outcome_start_timestamp", "outcome_end_timestamp",
    "observed_future_bars", "future_high", "future_low", "future_close",
    "outcome_completeness", "gap_detected", "outcome_status",
    "hypothetical_counterfactual", "cost_aware_note", "note",
]
SES_FIELDS = [
    "session_id", "status", "started_at_utc", "stopped_at_utc", "mode",
    "mt5_connected", "error", "notes",
]

LOCK_NAME = "session.lock"


class ShadowStoreError(RuntimeError):
    pass


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


class Phase16aShadowStore:
    def __init__(self, root: Path | None = None, *, read_only: bool = False) -> None:
        self.root = Path(root) if root is not None else DATA_DIR
        self.read_only = bool(read_only)
        if not self.read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / LOCK_NAME
        self.obs_path = self.root / "shadow_observations.csv"
        self.dec_path = self.root / "shadow_decisions.csv"
        self.out_path = self.root / "shadow_outcomes.csv"
        self.ses_path = self.root / "shadow_sessions.csv"
        self._obs = _read_csv(self.obs_path)
        self._dec = _read_csv(self.dec_path)
        self._out = _read_csv(self.out_path)
        self._ses = _read_csv(self.ses_path)
        self._obs_ids = {r["observation_id"] for r in self._obs}
        self._dec_ids = {r["decision_id"] for r in self._dec}
        self._open_ts = {r["bar_open_timestamp_utc"] for r in self._obs}

    def _assert_isolated(self, path: Path) -> None:
        if self.read_only:
            raise ShadowStoreError("read-only store cannot write")
        resolved = path.resolve()
        allowed = self.root.resolve()
        try:
            resolved.relative_to(allowed)
        except ValueError as exc:
            raise ShadowStoreError(f"refusing write outside {allowed}") from exc
        # Never write into Phase 12 store or holdout tree unexpectedly
        phase12 = (SRC_DIR / "data" / "phase12").resolve()
        try:
            resolved.relative_to(phase12)
            raise ShadowStoreError("refusing write into phase12 storage")
        except ValueError:
            pass

    def _save(self, path: Path, rows: list[dict], fields: list[str]) -> None:
        self._assert_isolated(path)
        _write_csv(path, rows, fields)

    def has_lock(self) -> bool:
        return self.lock_path.exists()

    def write_lock(self, session_id: str, mode: str, started_at: str) -> None:
        if self.has_lock():
            raise ShadowStoreError("concurrent session rejected")
        self._assert_isolated(self.lock_path)
        self.lock_path.write_text(f"{session_id}\t{mode}\t{started_at}\n", encoding="utf-8")

    def clear_lock(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def last_open_utc(self) -> str | None:
        if not self._open_ts:
            return None
        return max(self._open_ts)

    def append_observation(self, row: dict) -> None:
        if row["observation_id"] in self._obs_ids:
            raise ShadowStoreError("duplicate observation_id")
        if row["bar_open_timestamp_utc"] in self._open_ts:
            raise ShadowStoreError("duplicate timestamp")
        self._obs.append(row)
        self._obs_ids.add(row["observation_id"])
        self._open_ts.add(row["bar_open_timestamp_utc"])
        self._save(self.obs_path, self._obs, OBS_FIELDS)

    def append_decision(self, row: dict) -> None:
        if row["decision_id"] in self._dec_ids:
            raise ShadowStoreError("duplicate decision_id")
        if row.get("is_paper_trade") in {True, "True", "true"}:
            raise ShadowStoreError("shadow decision cannot be a paper trade")
        if row.get("final_action") in {"BUY", "SELL"}:
            raise ShadowStoreError("production final_action BUY/SELL forbidden under NO_MODEL")
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

    def refresh_outcomes(self, subsequent_bars: list[dict], *, as_of_utc: str) -> dict:
        pending = 0
        completed = 0
        for dec in self._dec:
            if dec.get("experimental_action") not in {"BUY", "SELL"}:
                continue
            payload = {
                "decision_id": dec["decision_id"],
                "decision_timestamp_utc": dec["decision_timestamp_utc"],
            }
            out = observe_outcome(payload, subsequent_bars, as_of_utc=as_of_utc)
            out["source_type"] = SOURCE_TYPE
            out["cost_aware_note"] = (
                "market-path observation only; frozen cost-aware net_r not fabricated as paper P&L; "
                "cost methodology deferred to post-complete research scoring using SPREAD_FLOOR"
            )
            if out.get("outcome_status") == "complete":
                completed += 1
            else:
                pending += 1
            self.upsert_outcome(out)
        return {"pending": pending, "completed": completed}
