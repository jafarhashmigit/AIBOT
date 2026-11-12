"""Immutable Phase49 chunk storage (isolated from Phase43)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase49.constants import MANIFESTS, RAW_H1, RAW_M5, RAW_TICKS, SOURCE_SERVER_LABEL, SYMBOL

UTC = timezone.utc


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def new_rid() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> bytes:
    text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + ("\n" if rows else "")
    body = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == body:
            return existing
        raise FileExistsError(f"refusing overwrite different content: {path}")
    path.write_bytes(body)
    return body


def _save_manifest(name: str, manifest: dict[str, Any]) -> Path:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS / f"{name}.manifest.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("sha256") != manifest.get("sha256"):
            raise FileExistsError(f"manifest hash conflict: {path}")
        return path
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def m5_done(day: str) -> bool:
    return (RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl").is_file()


def h1_done(day: str) -> bool:
    return (RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl").is_file()


def tick_hour_done(day: str, hour: int) -> bool:
    return (RAW_TICKS / f"ticks_{SYMBOL}_{day}_{hour:02d}h.jsonl").is_file()


def save_m5(day: str, bars: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"m5_{SYMBOL}_{day}.jsonl"
    path = RAW_M5 / name
    rows = [
        {
            **b,
            "symbol": SYMBOL,
            "timeframe": "M5",
            "retrieval_id": rid,
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
        }
        for b in bars
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    _save_manifest(
        name,
        {"kind": "m5", "symbol": SYMBOL, "day": day, "n": len(rows), "sha256": digest, "phase": 49},
    )
    return {"n": len(rows), "sha256": digest, "path": str(path.as_posix())}


def save_h1(day: str, bars: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"h1_{SYMBOL}_{day}_warmup.jsonl"
    path = RAW_H1 / name
    rows = [
        {
            **b,
            "symbol": SYMBOL,
            "timeframe": "H1",
            "retrieval_id": rid,
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
        }
        for b in bars
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    _save_manifest(
        name,
        {"kind": "h1", "symbol": SYMBOL, "day": day, "n": len(rows), "sha256": digest, "phase": 49},
    )
    return {"n": len(rows), "sha256": digest, "path": str(path.as_posix())}


def save_tick_hour(day: str, hour: int, ticks: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"ticks_{SYMBOL}_{day}_{hour:02d}h.jsonl"
    path = RAW_TICKS / name
    rows = [
        {
            **t,
            "symbol": SYMBOL,
            "retrieval_id": rid,
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
        }
        for t in ticks
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    _save_manifest(
        name,
        {
            "kind": "ticks",
            "symbol": SYMBOL,
            "day": day,
            "hour": hour,
            "n": len(rows),
            "sha256": digest,
            "phase": 49,
            "empty_hour": len(rows) == 0,
        },
    )
    return {"n": len(rows), "sha256": digest, "path": str(path.as_posix()), "empty_hour": len(rows) == 0}
