"""Manual session start/stop. No automatic startup. No concurrent sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from phase12.decision_recorder import record_shadow_decision
from phase12.market_data_reader import SyntheticReader
from phase12.observation_builder import build_observation
from phase12.storage import ShadowStore
from phase12.validation import DATA_DIR, ShadowError

UTC = timezone.utc
LOCK_NAME = "session.lock"


class SessionManager:
    def __init__(self, root: Path | None = None, *, read_only: bool = False) -> None:
        self.root = Path(root) if root is not None else DATA_DIR
        self.read_only = bool(read_only)
        if not self.read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / LOCK_NAME
        self.store = ShadowStore(self.root, read_only=self.read_only)

    def _now(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def status(self) -> dict:
        running = self.lock_path.exists()
        lock_text = self.lock_path.read_text(encoding="utf-8") if running else ""
        return {
            "running": running,
            "lock": lock_text.strip(),
            "observations": len(self.store.observations()),
            "decisions": len(self.store.decisions()),
            "outcomes": len(self.store.outcomes()),
        }

    def start(self, *, session_id: str, mode: str) -> dict:
        if self.read_only:
            raise ShadowError("read-only session manager cannot start")
        if self.lock_path.exists():
            raise ShadowError("concurrent session rejected")
        if mode == "live_mt5":
            raise ShadowError("Stage B live MT5 start is manual-only and not executed by Stage A")
        self.lock_path.write_text(f"{session_id}\t{mode}\t{self._now()}\n", encoding="utf-8")
        row = {
            "session_id": session_id,
            "status": "running",
            "started_at_utc": self._now(),
            "stopped_at_utc": "",
            "mode": mode,
            "mt5_connected": False,
            "error": "",
            "notes": "manual start",
        }
        self.store.append_session(row)
        return row

    def stop(self) -> dict:
        if self.read_only:
            raise ShadowError("read-only session manager cannot stop")
        if not self.lock_path.exists():
            raise ShadowError("no running session")
        lock = self.lock_path.read_text(encoding="utf-8").strip()
        self.lock_path.unlink()
        row = {
            "session_id": lock.split("\t")[0] if lock else "unknown",
            "status": "stopped",
            "started_at_utc": "",
            "stopped_at_utc": self._now(),
            "mode": "offline",
            "mt5_connected": False,
            "error": "",
            "notes": "graceful manual stop",
        }
        self.store.append_session(row)
        return row

    def record_interrupted(self, error: str = "process_interrupted") -> dict:
        if self.read_only:
            raise ShadowError("read-only session manager cannot record interrupt")
        if not self.lock_path.exists():
            raise ShadowError("no running session")
        lock = self.lock_path.read_text(encoding="utf-8").strip()
        row = {
            "session_id": lock.split("\t")[0] if lock else "unknown",
            "status": "interrupted",
            "started_at_utc": "",
            "stopped_at_utc": self._now(),
            "mode": "offline",
            "mt5_connected": False,
            "error": error,
            "notes": "interrupted session recorded; lock kept until stop; journals preserved",
        }
        self.store.append_session(row)
        return row

    def ingest_synthetic(self, bars: list[dict], *, as_of_utc: str, created_at_utc: str) -> dict:
        try:
            reader = SyntheticReader(bars)
            completed = reader.poll_completed(as_of_utc=as_of_utc, previous_open_utc=None)
            n_new = 0
            skipped_dup = 0
            for bar in completed:
                obs = build_observation(bar, created_at_utc=created_at_utc)
                try:
                    self.store.append_observation(obs)
                except ShadowError as exc:
                    if "duplicate" in str(exc):
                        skipped_dup += 1
                        continue
                    raise
                dec = record_shadow_decision(obs)
                self.store.append_decision(dec)
                n_new += 1
            self.store.refresh_outcomes(as_of_utc)
            return {
                "new_observations": n_new,
                "duplicate_skipped": skipped_dup,
                "reader_errors": list(reader.errors),
                "status": self.status(),
            }
        except Exception:
            if self.lock_path.exists() and not self.read_only:
                self.record_interrupted("ingest_exception")
            raise
