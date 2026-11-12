"""Immutable chunk storage + manifests (never silent overwrite)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase38.constants import (
    CANONICAL_DIR,
    MANIFESTS_DIR,
    RAW_M5_DIR,
    RAW_TICKS_DIR,
    REJECTED_DIR,
    SOURCE_SERVER_LABEL,
    SYMBOL,
    TERMINAL_PATH,
)

UTC = timezone.utc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def new_retrieval_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> bytes:
    text = "\n".join(json.dumps(r, sort_keys=True) for r in rows) + ("\n" if rows else "")
    body = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == body:
            return existing  # identical reuse
        raise FileExistsError(f"refusing overwrite different content: {path}")
    path.write_bytes(body)
    return body


def save_rejected(kind: str, retrieval_id: str, rejected: list[dict[str, Any]]) -> str | None:
    if not rejected:
        return None
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    path = REJECTED_DIR / f"{kind}_{retrieval_id}.jsonl"
    _write_jsonl(path, rejected)
    return str(path)


def save_m5_chunk(
    bars: list[dict[str, Any]],
    *,
    day: str,
    requested_start: str,
    requested_end: str,
    actual_start: str | None,
    actual_end: str | None,
    validation: dict[str, Any],
    terminal_build: Any,
    server: str | None,
    mt5_error: Any,
    elapsed_s: float,
) -> dict[str, Any]:
    rid = new_retrieval_id()
    raw_name = f"m5_{SYMBOL}_{day}.jsonl"
    raw_path = RAW_M5_DIR / raw_name
    # enrich canonical rows
    canon_rows = []
    for b in bars:
        canon_rows.append(
            {
                "symbol": SYMBOL,
                "timeframe": "M5",
                "timestamp_utc": b.get("timestamp_utc") or b.get("time_utc"),
                "time_epoch": b.get("time_epoch"),
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "tick_volume": b.get("tick_volume"),
                "spread": b.get("spread"),
                "real_volume": b.get("real_volume"),
                "source_server": server or SOURCE_SERVER_LABEL,
                "source_terminal_build": terminal_build,
                "retrieval_id": rid,
            }
        )
    body = _write_jsonl(raw_path, canon_rows)
    digest = sha256_bytes(body)
    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    canon_path = CANONICAL_DIR / f"m5_{SYMBOL}_{day}.jsonl"
    if not canon_path.exists():
        canon_path.write_bytes(body)
    elif sha256_file(canon_path) != digest:
        raise FileExistsError(f"canonical mismatch: {canon_path}")

    rejected_path = save_rejected("m5", rid, validation.get("rejected") or [])
    manifest = {
        "retrieval_id": rid,
        "kind": "m5",
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "server": server or SOURCE_SERVER_LABEL,
        "symbol": SYMBOL,
        "timeframe": "M5",
        "requested_utc_interval": [requested_start, requested_end],
        "actual_utc_interval": [actual_start, actual_end],
        "record_count": len(canon_rows),
        "file_path": str(raw_path).replace("\\", "/"),
        "sha256": digest,
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation": {k: v for k, v in validation.items() if k not in {"accepted", "rejected"}},
        "rejected_path": rejected_path,
        "mt5_error": mt5_error,
        "elapsed_s": elapsed_s,
        "terminal_build": terminal_build,
    }
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    man_path = MANIFESTS_DIR / f"{raw_name}.manifest.json"
    if man_path.exists():
        old = json.loads(man_path.read_text(encoding="utf-8"))
        if old.get("sha256") != digest:
            raise FileExistsError(f"manifest exists with different hash: {man_path}")
    else:
        man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": manifest, "path": str(raw_path), "sha256": digest, "retrieval_id": rid}


def save_ticks_chunk(
    ticks: list[dict[str, Any]],
    *,
    day: str,
    hour_tag: str,
    requested_start: str,
    requested_end: str,
    actual_start: str | None,
    actual_end: str | None,
    validation: dict[str, Any],
    terminal_build: Any,
    server: str | None,
    mt5_error: Any,
    elapsed_s: float,
) -> dict[str, Any]:
    rid = new_retrieval_id()
    raw_name = f"ticks_{SYMBOL}_{day}_{hour_tag}.jsonl"
    raw_path = RAW_TICKS_DIR / raw_name
    canon_rows = []
    for t in ticks:
        msc = t.get("timestamp_msc") or t.get("time_msc")
        canon_rows.append(
            {
                "timestamp_utc": t.get("timestamp_utc"),
                "timestamp_msc": msc,
                "bid": t.get("bid"),
                "ask": t.get("ask"),
                "last": t.get("last"),
                "volume": t.get("volume"),
                "volume_real": t.get("volume_real"),
                "flags": t.get("flags"),
                "source_server": server or SOURCE_SERVER_LABEL,
                "source_terminal_build": terminal_build,
                "retrieval_id": rid,
            }
        )
    body = _write_jsonl(raw_path, canon_rows)
    digest = sha256_bytes(body)
    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    canon_path = CANONICAL_DIR / raw_name
    if not canon_path.exists():
        canon_path.write_bytes(body)
    elif sha256_file(canon_path) != digest:
        raise FileExistsError(f"canonical mismatch: {canon_path}")

    rejected_path = save_rejected("ticks", rid, validation.get("rejected") or [])
    manifest = {
        "retrieval_id": rid,
        "kind": "ticks",
        "source": "MT5",
        "terminal_path": TERMINAL_PATH,
        "server": server or SOURCE_SERVER_LABEL,
        "symbol": SYMBOL,
        "timeframe": "TICK",
        "requested_utc_interval": [requested_start, requested_end],
        "actual_utc_interval": [actual_start, actual_end],
        "record_count": len(canon_rows),
        "file_path": str(raw_path).replace("\\", "/"),
        "sha256": digest,
        "retrieval_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "validation": {k: v for k, v in validation.items() if k not in {"accepted", "rejected"}},
        "rejected_path": rejected_path,
        "mt5_error": mt5_error,
        "elapsed_s": elapsed_s,
        "terminal_build": terminal_build,
    }
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    man_path = MANIFESTS_DIR / f"{raw_name}.manifest.json"
    if man_path.exists():
        old = json.loads(man_path.read_text(encoding="utf-8"))
        if old.get("sha256") != digest:
            raise FileExistsError(f"manifest exists with different hash: {man_path}")
    else:
        man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": manifest, "path": str(raw_path), "sha256": digest, "retrieval_id": rid}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows
