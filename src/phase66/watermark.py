"""Collection watermark persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase66.constants import WATERMARK_PATH, canonical_json_sha256
from phase66.schema import utc_now


def load_watermark(path: Path | None = None) -> dict[str, Any]:
    p = path or WATERMARK_PATH
    if not p.is_file():
        return {
            "last_quote_server_ts": None,
            "last_m5_server_ts": None,
            "last_success_utc": None,
            "n_quotes": 0,
            "n_m5": 0,
            "n_rejected": 0,
            "n_duplicates": 0,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_watermark(wm: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    p = path or WATERMARK_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    wm = {**wm, "updated_utc": utc_now()}
    wm["sha256"] = canonical_json_sha256({k: v for k, v in wm.items() if k != "sha256"})
    p.write_text(json.dumps(wm, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return wm


def advance_watermark(
    wm: dict[str, Any],
    *,
    quote_ts: str | None = None,
    m5_ts: str | None = None,
    ingested: int = 0,
    duplicates: int = 0,
    rejected: int = 0,
) -> dict[str, Any]:
    out = dict(wm)
    if quote_ts:
        prev = out.get("last_quote_server_ts")
        if prev is None or quote_ts >= prev:
            out["last_quote_server_ts"] = quote_ts
        out["n_quotes"] = int(out.get("n_quotes") or 0) + ingested
    if m5_ts:
        prev = out.get("last_m5_server_ts")
        if prev is None or m5_ts >= prev:
            out["last_m5_server_ts"] = m5_ts
        out["n_m5"] = int(out.get("n_m5") or 0) + (1 if ingested else 0)
    out["n_duplicates"] = int(out.get("n_duplicates") or 0) + duplicates
    out["n_rejected"] = int(out.get("n_rejected") or 0) + rejected
    if ingested:
        out["last_success_utc"] = utc_now()
    return out
