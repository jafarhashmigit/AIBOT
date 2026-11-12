"""Immutable local MT5 cache + manifests (no credentials)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase37.constants import BARS_DIR, MANIFESTS_DIR, PROJECT_ROOT, TICKS_DIR, TERMINAL_PATH

UTC = timezone.utc


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_bars_sample(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    requested_start: str,
    requested_end: str,
    server: str | None,
    validation: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    BARS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = BARS_DIR / filename
    if path.exists():
        # immutable: do not overwrite
        body = path.read_bytes()
    else:
        text = "\n".join(json.dumps(b, sort_keys=True) for b in bars) + ("\n" if bars else "")
        body = text.encode("utf-8")
        path.write_bytes(body)
    digest = _sha256_bytes(body)
    actual_start = bars[0]["time_utc"] if bars else None
    actual_end = bars[-1]["time_utc"] if bars else None
    manifest = {
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "broker_server": server,
        "symbol": symbol,
        "timeframe": "M5",
        "requested_utc_range": [requested_start, requested_end],
        "actual_utc_range": [actual_start, actual_end],
        "row_count": len(bars),
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_validation_result": validation,
        "file_hash_sha256": digest,
        "schema": ["time_epoch", "time_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"],
        "relpath": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    man_path = MANIFESTS_DIR / f"{filename}.manifest.json"
    if not man_path.exists():
        man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "manifest": manifest, "manifest_path": str(man_path)}


def save_ticks_sample(
    ticks: list[dict[str, Any]],
    *,
    symbol: str,
    requested_start: str,
    requested_end: str,
    server: str | None,
    validation: dict[str, Any],
    filename: str,
) -> dict[str, Any]:
    TICKS_DIR.mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TICKS_DIR / filename
    if path.exists():
        body = path.read_bytes()
    else:
        text = "\n".join(json.dumps(t, sort_keys=True) for t in ticks) + ("\n" if ticks else "")
        body = text.encode("utf-8")
        path.write_bytes(body)
    digest = _sha256_bytes(body)
    actual_start = ticks[0].get("timestamp_utc") if ticks else None
    actual_end = ticks[-1].get("timestamp_utc") if ticks else None
    manifest = {
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "broker_server": server,
        "symbol": symbol,
        "timeframe": "TICK",
        "requested_utc_range": [requested_start, requested_end],
        "actual_utc_range": [actual_start, actual_end],
        "tick_count": len(ticks),
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_validation_result": validation,
        "file_hash_sha256": digest,
        "schema": [
            "time_epoch",
            "time_msc",
            "timestamp_utc",
            "bid",
            "ask",
            "last",
            "volume",
            "volume_real",
            "flags",
            "spread",
        ],
        "relpath": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }
    man_path = MANIFESTS_DIR / f"{filename}.manifest.json"
    if not man_path.exists():
        man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "manifest": manifest, "manifest_path": str(man_path)}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
