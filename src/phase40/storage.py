"""Immutable Phase40 chunk storage + manifests."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase40.constants import (
    CANONICAL,
    MANIFESTS,
    RAW_H1,
    RAW_M5,
    RAW_TICKS,
    SOURCE_SERVER_LABEL,
    SYMBOL,
    TERMINAL_PATH,
)

UTC = timezone.utc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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


def save_m5(day: str, bars: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"m5_{SYMBOL}_{day}.jsonl"
    path = RAW_M5 / name
    rows = [
        {
            **b,
            "symbol": SYMBOL,
            "timeframe": "M5",
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
            "source_terminal_build": meta.get("terminal_build"),
            "retrieval_id": rid,
        }
        for b in bars
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    CANONICAL.mkdir(parents=True, exist_ok=True)
    cpath = CANONICAL / name
    if not cpath.exists():
        cpath.write_bytes(body)
    manifest = {
        "retrieval_id": rid,
        "kind": "m5",
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "server": meta.get("server") or SOURCE_SERVER_LABEL,
        "terminal_build": meta.get("terminal_build"),
        "symbol": SYMBOL,
        "timeframe": "M5",
        "requested_utc_interval": [meta.get("requested_start"), meta.get("requested_end")],
        "actual_utc_interval": [meta.get("actual_start"), meta.get("actual_end")],
        "record_count": len(rows),
        "file_path": str(path).replace("\\", "/"),
        "sha256": digest,
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation_status": meta.get("validation_status"),
        "mt5_error": meta.get("mt5_error"),
        "elapsed_s": meta.get("elapsed_s"),
    }
    _save_manifest(name, manifest)
    return {"path": str(path), "sha256": digest, "retrieval_id": rid, "n": len(rows)}


def save_h1(day: str, bars: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"h1_{SYMBOL}_{day}_warmup.jsonl"
    path = RAW_H1 / name
    rows = [
        {
            **b,
            "symbol": SYMBOL,
            "timeframe": "H1",
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
            "source_terminal_build": meta.get("terminal_build"),
            "retrieval_id": rid,
        }
        for b in bars
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    CANONICAL.mkdir(parents=True, exist_ok=True)
    cpath = CANONICAL / name
    if not cpath.exists():
        cpath.write_bytes(body)
    manifest = {
        "retrieval_id": rid,
        "kind": "h1",
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "server": meta.get("server") or SOURCE_SERVER_LABEL,
        "terminal_build": meta.get("terminal_build"),
        "symbol": SYMBOL,
        "timeframe": "H1",
        "requested_utc_interval": [meta.get("requested_start"), meta.get("requested_end")],
        "actual_utc_interval": [meta.get("actual_start"), meta.get("actual_end")],
        "record_count": len(rows),
        "n_warmup_available": meta.get("n_warmup_available"),
        "warmup_sufficient": meta.get("warmup_sufficient"),
        "file_path": str(path).replace("\\", "/"),
        "sha256": digest,
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation_status": meta.get("validation_status"),
        "mt5_error": meta.get("mt5_error"),
        "elapsed_s": meta.get("elapsed_s"),
    }
    _save_manifest(name, manifest)
    return {"path": str(path), "sha256": digest, "retrieval_id": rid, "n": len(rows)}


def save_tick_hour(day: str, hour: int, ticks: list[dict], meta: dict[str, Any]) -> dict[str, Any]:
    rid = new_rid()
    name = f"ticks_{SYMBOL}_{day}_{hour:02d}h.jsonl"
    path = RAW_TICKS / name
    # empty hour: write empty file + empty marker note in manifest
    rows = [
        {
            **t,
            "symbol": SYMBOL,
            "source_server": meta.get("server") or SOURCE_SERVER_LABEL,
            "source_terminal_build": meta.get("terminal_build"),
            "retrieval_id": rid,
        }
        for t in ticks
    ]
    body = _write_jsonl(path, rows)
    digest = sha256_bytes(body)
    CANONICAL.mkdir(parents=True, exist_ok=True)
    cpath = CANONICAL / name
    if not cpath.exists():
        cpath.write_bytes(body)
    manifest = {
        "retrieval_id": rid,
        "kind": "ticks",
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "server": meta.get("server") or SOURCE_SERVER_LABEL,
        "terminal_build": meta.get("terminal_build"),
        "symbol": SYMBOL,
        "timeframe": "TICK",
        "hour_utc": hour,
        "requested_utc_interval": [meta.get("requested_start"), meta.get("requested_end")],
        "actual_utc_interval": [meta.get("actual_start"), meta.get("actual_end")],
        "record_count": len(rows),
        "empty_hour": len(rows) == 0,
        "file_path": str(path).replace("\\", "/"),
        "sha256": digest,
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation_status": meta.get("validation_status"),
        "bid_ask_ok": meta.get("bid_ask_ok"),
        "mt5_error": meta.get("mt5_error"),
        "elapsed_s": meta.get("elapsed_s"),
    }
    _save_manifest(name, manifest)
    return {"path": str(path), "sha256": digest, "retrieval_id": rid, "n": len(rows), "empty": len(rows) == 0}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def tick_hour_done(day: str, hour: int) -> bool:
    return (RAW_TICKS / f"ticks_{SYMBOL}_{day}_{hour:02d}h.jsonl").is_file()


def m5_done(day: str) -> bool:
    return (RAW_M5 / f"m5_{SYMBOL}_{day}.jsonl").is_file()


def h1_done(day: str) -> bool:
    return (RAW_H1 / f"h1_{SYMBOL}_{day}_warmup.jsonl").is_file()
