"""Dukascopy historical bi5 acquisition via stdlib only (no new packages)."""

from __future__ import annotations

import hashlib
import json
import lzma
import struct
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from phase25.constants import (
    DUKASCOPY_BASE,
    DOWNLOAD_HOURS_UTC,
    PARITY_DAYS,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
    SYMBOL,
    USER_AGENT,
    XAUUSD_PRICE_SCALE,
)

UTC = timezone.utc
TICK_STRUCT = struct.Struct(">IIIff")  # ms, ask, bid, ask_vol, bid_vol


def assert_before_cutoff(day: str, hour: int) -> None:
    ts = f"{day} {hour:02d}:00:00"
    if ts > RESEARCH_CUTOFF_UTC:
        raise RuntimeError(f"refusing download at/after research cutoff: {ts}")


def bi5_url(day: str, hour: int) -> str:
    """Build Dukascopy URL. Month in path is zero-based."""
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    y = dt.year
    m0 = dt.month - 1  # zero-based month
    d = dt.day
    return f"{DUKASCOPY_BASE}/{SYMBOL}/{y}/{m0:02d}/{d:02d}/{hour:02d}h_ticks.bi5"


def fetch_bi5(url: str, *, retries: int = 6, sleep_s: float = 1.5) -> dict[str, Any]:
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
                return {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "url": url,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest() if body else "",
                    "body": body,
                    "empty": len(body) == 0,
                    "attempts": i + 1,
                }
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
            # 404 rare; 429/503 backoff
            time.sleep(sleep_s * (2**i))
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(sleep_s * (2**i))
    return {
        "ok": False,
        "status": None,
        "url": url,
        "bytes": 0,
        "sha256": "",
        "body": b"",
        "empty": True,
        "error": last_err,
        "attempts": retries,
    }


def decode_ticks(body: bytes, *, day: str, hour: int) -> list[dict[str, Any]]:
    if not body:
        return []
    raw = lzma.decompress(body)
    if len(raw) % TICK_STRUCT.size != 0:
        raise ValueError(f"unexpected bi5 payload length {len(raw)}")
    hour_start = datetime.strptime(f"{day} {hour:02d}:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    out: list[dict[str, Any]] = []
    for off in range(0, len(raw), TICK_STRUCT.size):
        ms, ask_i, bid_i, ask_vol, bid_vol = TICK_STRUCT.unpack_from(raw, off)
        ts = hour_start + timedelta(milliseconds=ms)
        ask = ask_i / XAUUSD_PRICE_SCALE
        bid = bid_i / XAUUSD_PRICE_SCALE
        out.append(
            {
                "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "epoch_ms": int(ts.timestamp() * 1000),
                "bid": bid,
                "ask": ask,
                "mid": (bid + ask) / 2.0,
                "spread": ask - bid,
                "ask_volume": float(ask_vol),
                "bid_volume": float(bid_vol),
            }
        )
    return out


def download_day(day: str, *, raw_dir: Path | None = None, hours: list[int] | None = None) -> dict[str, Any]:
    root = Path(raw_dir) if raw_dir is not None else RAW_DIR
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    hours = list(range(24)) if hours is None else hours
    manifest = {
        "day": day,
        "symbol": SYMBOL,
        "source": DUKASCOPY_BASE,
        "month_indexing": "zero_based_in_url",
        "price_scale": XAUUSD_PRICE_SCALE,
        "files": [],
        "tick_count": 0,
        "errors": [],
    }
    all_ticks: list[dict[str, Any]] = []
    for hour in hours:
        assert_before_cutoff(day, hour)
        url = bi5_url(day, hour)
        fname = f"{hour:02d}h_ticks.bi5"
        path = day_dir / fname
        # Resume: reuse existing bi5 bytes (including empty placeholders marked .empty)
        empty_marker = day_dir / f"{hour:02d}h_ticks.empty"
        if path.is_file():
            body = path.read_bytes()
            result = {
                "ok": True,
                "status": 200,
                "url": url,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest() if body else "",
                "body": body,
                "empty": len(body) == 0,
                "attempts": 0,
                "resumed": True,
            }
        elif empty_marker.is_file():
            result = {
                "ok": True,
                "status": 200,
                "url": url,
                "bytes": 0,
                "sha256": "",
                "body": b"",
                "empty": True,
                "attempts": 0,
                "resumed": True,
            }
        else:
            result = fetch_bi5(url)
            time.sleep(0.8)
        meta = {
            "hour": hour,
            "url": url,
            "ok": result["ok"],
            "status": result.get("status"),
            "bytes": result["bytes"],
            "sha256": result["sha256"],
            "empty": result.get("empty"),
            "attempts": result.get("attempts"),
            "error": result.get("error"),
            "resumed": result.get("resumed", False),
            "tick_count": 0,
        }
        if result["ok"]:
            if not result.get("resumed"):
                if result["body"]:
                    path.write_bytes(result["body"])
                else:
                    empty_marker.write_text("empty\n", encoding="utf-8")
            if result["body"]:
                ticks = decode_ticks(result["body"], day=day, hour=hour)
                meta["tick_count"] = len(ticks)
                all_ticks.extend(ticks)
            # empty body = no quotes that hour (documented behavior) — not fabricated
        else:
            manifest["errors"].append(meta)
        manifest["files"].append(meta)
        manifest["files"][-1]["relpath"] = f"{day}/{fname}"

    manifest["tick_count"] = len(all_ticks)
    ticks_path = day_dir / "ticks_decoded.jsonl"
    with ticks_path.open("w", encoding="utf-8") as f:
        for t in all_ticks:
            f.write(json.dumps(t, sort_keys=True) + "\n")
    manifest["ticks_decoded_relpath"] = f"{day}/ticks_decoded.jsonl"
    (day_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": manifest, "ticks": all_ticks, "day_dir": day_dir}


def download_parity_days(*, days: list[str] | None = None) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    selected = days or PARITY_DAYS
    summary = {"days": {}, "total_ticks": 0, "failed_hours": 0, "empty_hours": 0, "ok_hours": 0}
    for day in selected:
        # Refuse any day after cutoff date
        if day > RESEARCH_CUTOFF_UTC[:10]:
            raise RuntimeError(f"day after cutoff refused: {day}")
        result = download_day(day, hours=DOWNLOAD_HOURS_UTC)
        man = result["manifest"]
        summary["days"][day] = {
            "tick_count": man["tick_count"],
            "errors": len(man["errors"]),
            "empty_hours": sum(1 for x in man["files"] if x.get("empty")),
            "ok_hours": sum(1 for x in man["files"] if x.get("ok") and not x.get("empty")),
            "failed_hours": sum(1 for x in man["files"] if not x.get("ok")),
        }
        summary["total_ticks"] += man["tick_count"]
        summary["failed_hours"] += summary["days"][day]["failed_hours"]
        summary["empty_hours"] += summary["days"][day]["empty_hours"]
        summary["ok_hours"] += summary["days"][day]["ok_hours"]
    summary["raw_dir"] = str(RAW_DIR)
    summary["separated_from_mt5"] = True
    summary["fabricated_candles"] = False
    (RAW_DIR / "download_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
