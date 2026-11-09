"""Phase 18 dedicated storage for decisions, multi-horizon outcomes, daily reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from phase18.constants import DATA_DIR, SRC_DIR

DEC_FIELDS = [
    "decision_id",
    "observation_id",
    "source_type",
    "decision_timestamp_utc",
    "symbol",
    "timeframe",
    "model_id",
    "model_status",
    "candidate_id",
    "candidate_status",
    "experimental_action",
    "raw_action",
    "risk_gate_result",
    "final_action",
    "decision_reason",
    "feature_snapshot_json",
    "selected_horizon",
    "outcome_status",
    "signal_bar_open_utc",
    "atr",
    "tp_level",
    "sl_level",
    "is_paper_trade",
    "is_paper_execution",
    "note",
]

OBS_FIELDS = [
    "observation_id",
    "source_type",
    "symbol",
    "timeframe",
    "bar_open_timestamp_utc",
    "bar_close_timestamp_utc",
    "observation_created_at_utc",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "data_source",
    "data_quality_status",
    "gap_status",
    "model_status",
    "decision_id",
    "candidate_id",
    "candidate_status",
]

OUT_FIELDS = [
    "outcome_event_id",
    "decision_id",
    "horizon_id",
    "horizon_label",
    "horizon_bars",
    "side",
    "symbol",
    "decision_timestamp_utc",
    "expected_check_utc",
    "status",
    "exit_reason",
    "realized_r",
    "net_pnl",
    "costs",
    "atr",
    "tp_level",
    "sl_level",
    "entry_fill",
    "exit_fill",
    "exit_timestamp_utc",
    "outcome_timestamp_utc",
    "discord_notified",
    "experience_recorded",
    "note",
]

SES_FIELDS = [
    "session_id",
    "status",
    "started_at_utc",
    "stopped_at_utc",
    "mode",
    "mt5_connected",
    "error",
    "notes",
]

DAILY_FIELDS = [
    "report_id",
    "date_pkt",
    "generated_at_utc",
    "discord_status",
    "payload_sha256",
    "note",
]

LOCK_NAME = "session.lock"


class Phase18StoreError(RuntimeError):
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


class Phase18Store:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / LOCK_NAME
        self.obs_path = self.root / "shadow_observations.csv"
        self.dec_path = self.root / "shadow_decisions.csv"
        self.out_path = self.root / "horizon_outcomes.csv"
        self.ses_path = self.root / "shadow_sessions.csv"
        self.daily_path = self.root / "daily_reports.csv"
        self.bars_path = self.root / "bar_cache.jsonl"
        self._obs = _read_csv(self.obs_path)
        self._dec = _read_csv(self.dec_path)
        self._out = _read_csv(self.out_path)
        self._ses = _read_csv(self.ses_path)
        self._daily = _read_csv(self.daily_path)
        self._obs_ids = {r["observation_id"] for r in self._obs}
        self._dec_ids = {r["decision_id"] for r in self._dec}
        self._out_ids = {r["outcome_event_id"] for r in self._out}
        self._open_ts = {r["bar_open_timestamp_utc"] for r in self._obs}
        self._daily_ids = {r["report_id"] for r in self._daily}

    def _assert_isolated(self, path: Path) -> None:
        resolved = path.resolve()
        allowed = self.root.resolve()
        try:
            resolved.relative_to(allowed)
        except ValueError as exc:
            raise Phase18StoreError(f"refusing write outside {allowed}") from exc
        for banned in ("phase12", "phase16a", "phase16b", "phase17"):
            other = (SRC_DIR / "data" / banned).resolve()
            try:
                resolved.relative_to(other)
                raise Phase18StoreError(f"refusing write into {banned} storage")
            except ValueError:
                pass

    def _save(self, path: Path, rows: list[dict], fields: list[str]) -> None:
        self._assert_isolated(path)
        _write_csv(path, rows, fields)

    def has_lock(self) -> bool:
        return self.lock_path.exists()

    def write_lock(self, session_id: str, mode: str, started: str) -> None:
        self._assert_isolated(self.lock_path)
        self.lock_path.write_text(
            json.dumps({"session_id": session_id, "mode": mode, "started_at_utc": started}),
            encoding="utf-8",
        )

    def clear_lock(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def last_open_utc(self) -> str | None:
        if not self._obs:
            return None
        return max(r["bar_open_timestamp_utc"] for r in self._obs)

    def append_observation(self, row: dict[str, Any]) -> bool:
        oid = row["observation_id"]
        if oid in self._obs_ids:
            return False
        self._obs.append(row)
        self._obs_ids.add(oid)
        self._open_ts.add(row["bar_open_timestamp_utc"])
        self._save(self.obs_path, self._obs, OBS_FIELDS)
        return True

    def append_decision(self, row: dict[str, Any]) -> bool:
        did = row["decision_id"]
        if did in self._dec_ids:
            return False
        self._dec.append(row)
        self._dec_ids.add(did)
        self._save(self.dec_path, self._dec, DEC_FIELDS)
        return True

    def append_outcomes(self, rows: list[dict[str, Any]]) -> int:
        added = 0
        for row in rows:
            oid = row["outcome_event_id"]
            if oid in self._out_ids:
                continue
            self._out.append(row)
            self._out_ids.add(oid)
            added += 1
        if added:
            self._save(self.out_path, self._out, OUT_FIELDS)
        return added

    def upsert_outcome(self, row: dict[str, Any]) -> None:
        oid = row["outcome_event_id"]
        for i, existing in enumerate(self._out):
            if existing["outcome_event_id"] == oid:
                self._out[i] = row
                self._save(self.out_path, self._out, OUT_FIELDS)
                return
        self._out.append(row)
        self._out_ids.add(oid)
        self._save(self.out_path, self._out, OUT_FIELDS)

    def append_session(self, row: dict[str, Any]) -> None:
        self._ses.append(row)
        self._save(self.ses_path, self._ses, SES_FIELDS)

    def append_daily_report(self, row: dict[str, Any]) -> bool:
        rid = row["report_id"]
        if rid in self._daily_ids:
            return False
        self._daily.append(row)
        self._daily_ids.add(rid)
        self._save(self.daily_path, self._daily, DAILY_FIELDS)
        return True

    def decisions(self) -> list[dict]:
        return list(self._dec)

    def outcomes(self) -> list[dict]:
        return list(self._out)

    def pending_outcomes(self) -> list[dict]:
        return [r for r in self._out if r.get("status") == "PENDING"]

    def decision_by_id(self, decision_id: str) -> dict | None:
        for r in self._dec:
            if r["decision_id"] == decision_id:
                return r
        return None

    def cache_bars(self, bars: list[dict[str, Any]]) -> None:
        """Merge bar snapshots for restart recovery / outcome evaluation."""
        existing: dict[str, dict] = {}
        if self.bars_path.is_file():
            for line in self.bars_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = row.get("bar_open_timestamp_utc")
                if key:
                    existing[key] = row
        for b in bars:
            key = b.get("bar_open_timestamp_utc")
            if key:
                existing[str(key)] = b
        self._assert_isolated(self.bars_path)
        with self.bars_path.open("w", encoding="utf-8") as f:
            for key in sorted(existing):
                f.write(json.dumps(existing[key], sort_keys=True, default=str) + "\n")

    def load_cached_bars(self) -> list[dict[str, Any]]:
        if not self.bars_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.bars_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return sorted(rows, key=lambda r: r["bar_open_timestamp_utc"])
