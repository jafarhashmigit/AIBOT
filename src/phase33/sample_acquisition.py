"""Bounded Dukascopy bi5 sample acquisition — stdlib only, no accounts."""

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

from phase33.constants import (
    DUKASCOPY_BASE,
    PHASE25_RAW_DIR,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
    SAMPLE_DAYS,
    SAMPLE_HOURS_UTC,
    SYMBOL,
    USER_AGENT,
    XAUUSD_PRICE_SCALE,
)
from phase33.progress import load_progress, save_progress, write_json

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
    m0 = dt.month - 1
    d = dt.day
    return f"{DUKASCOPY_BASE}/{SYMBOL}/{y}/{m0:02d}/{d:02d}/{hour:02d}h_ticks.bi5"


def fetch_bi5(url: str, *, retries: int = 3, sleep_s: float = 0.8) -> dict[str, Any]:
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=45) as resp:
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
            # Cap backoff — do not artificially extend runtime on persistent 503s.
            time.sleep(min(sleep_s * (2**i), 3.0))
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(min(sleep_s * (2**i), 3.0))
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


def _try_phase25_seed(day: str, hour: int) -> bytes | None:
    """Read-only reuse of prior Phase25 bi5 bytes when present (no Phase25 mutation)."""
    path = PHASE25_RAW_DIR / day / f"{hour:02d}h_ticks.bi5"
    if path.is_file():
        return path.read_bytes()
    empty = PHASE25_RAW_DIR / day / f"{hour:02d}h_ticks.empty"
    if empty.is_file():
        return b""
    return None


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
        if ts.strftime("%Y-%m-%d %H:%M:%S") > RESEARCH_CUTOFF_UTC:
            continue  # hard cutoff enforcement
        ask = ask_i / XAUUSD_PRICE_SCALE
        bid = bid_i / XAUUSD_PRICE_SCALE
        out.append(
            {
                "timestamp_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp_utc_ms": ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}",
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


def acquisition_preamble(day: str, hour: int) -> dict[str, Any]:
    return {
        "exact_source": DUKASCOPY_BASE,
        "download_method": "HTTP GET urllib (stdlib) of hourly LZMA .bi5",
        "file_format": "bi5 (LZMA + 20-byte big-endian ticks)",
        "instrument": SYMBOL,
        "day": day,
        "hour_utc": hour,
        "date_range": f"{day} {hour:02d}:00–{hour:02d}:59 UTC (hour archive)",
        "timestamp_convention": "ms offset from hour start; reconstructed as UTC",
        "bid_ask_field_definitions": {
            "ask": "uint32 / 1000 → USD ask",
            "bid": "uint32 / 1000 → USD bid",
            "ask_vol": "float32 quote-size field (NOT traded volume)",
            "bid_vol": "float32 quote-size field (NOT traded volume)",
        },
        "retrieval_time_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
    }


def download_hour(day: str, hour: int, day_dir: Path) -> dict[str, Any]:
    assert_before_cutoff(day, hour)
    meta = acquisition_preamble(day, hour)
    url = bi5_url(day, hour)
    fname = f"{hour:02d}h_ticks.bi5"
    path = day_dir / fname
    empty_marker = day_dir / f"{hour:02d}h_ticks.empty"
    meta["url"] = url

    if path.is_file():
        body = path.read_bytes()
        result = {
            "ok": True,
            "status": 200,
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
            "bytes": 0,
            "sha256": "",
            "body": b"",
            "empty": True,
            "attempts": 0,
            "resumed": True,
        }
    else:
        # Prefer prior Phase25 raw bytes when present (read-only) to avoid rate-limit stalls.
        # Network probe is performed separately for free-access evidence.
        seed = _try_phase25_seed(day, hour)
        if seed is not None:
            result = {
                "ok": True,
                "status": 200,
                "bytes": len(seed),
                "sha256": hashlib.sha256(seed).hexdigest() if seed else "",
                "body": seed,
                "empty": len(seed) == 0,
                "attempts": 0,
                "resumed": False,
                "seeded_from_phase25_raw": True,
            }
        else:
            result = fetch_bi5(url, retries=2, sleep_s=0.5)
            time.sleep(0.2)
            result["seeded_from_phase25_raw"] = False
        if result["ok"]:
            if result["body"]:
                path.write_bytes(result["body"])
            else:
                empty_marker.write_text("empty\n", encoding="utf-8")

    meta.update(
        {
            "ok": result["ok"],
            "status": result.get("status"),
            "file_size_bytes": result["bytes"],
            "sha256": result["sha256"],
            "empty": result.get("empty"),
            "attempts": result.get("attempts"),
            "error": result.get("error"),
            "resumed": result.get("resumed", False),
            "seeded_from_phase25_raw": result.get("seeded_from_phase25_raw", False),
            "network_error_before_seed": result.get("network_error_before_seed"),
            "tick_count": 0,
            "blocker": None,
        }
    )
    ticks: list[dict[str, Any]] = []
    if result["ok"] and result.get("body"):
        ticks = decode_ticks(result["body"], day=day, hour=hour)
        meta["tick_count"] = len(ticks)
    elif not result["ok"]:
        meta["blocker"] = result.get("error") or "download_failed"
    return meta, ticks


def network_access_probe() -> dict[str, Any]:
    """Single bounded live GET to prove free public access without downloading the full sample."""
    day, hour = "2026-02-17", 1
    url = bi5_url(day, hour)
    t0 = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = fetch_bi5(url, retries=2, sleep_s=0.5)
    return {
        "retrieved_utc": t0,
        "url": url,
        "ok": result["ok"],
        "status": result.get("status"),
        "bytes": result.get("bytes"),
        "empty": result.get("empty"),
        "error": result.get("error"),
        "attempts": result.get("attempts"),
        "account_required": False if result["ok"] else "UNKNOWN",
        "evidence_class": "DIRECTLY_OBSERVED" if result["ok"] or result.get("error") else "UNVERIFIED",
    }


def run_sample_acquisition(
    *,
    days: list[str] | None = None,
    hours: list[int] | None = None,
) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    selected_days = days or SAMPLE_DAYS
    selected_hours = hours if hours is not None else SAMPLE_HOURS_UTC
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    probe = network_access_probe()
    log: dict[str, Any] = {
        "started_utc": started,
        "policy": {
            "accounts": False,
            "credentials": False,
            "paid_apis": False,
            "package_install": False,
            "full_history": False,
            "bounded_diagnostic_sample": True,
            "fabricate_bid_ask": False,
            "phase25_raw_seed_allowed_read_only": True,
        },
        "network_access_probe": probe,
        "days": {},
        "attempts": [],
        "total_ticks": 0,
        "total_bytes": 0,
        "failed_hours": 0,
        "empty_hours": 0,
        "ok_hours": 0,
        "blockers": [],
        "raw_dir": str(RAW_DIR),
    }

    prog = load_progress()
    prog["download_attempts"] = []
    prog["download_results"] = []
    save_progress(prog)

    all_ticks: list[dict[str, Any]] = []
    for day in selected_days:
        if day > RESEARCH_CUTOFF_UTC[:10]:
            log["blockers"].append({"day": day, "blocker": "after_cutoff"})
            continue
        day_dir = RAW_DIR / day
        day_dir.mkdir(parents=True, exist_ok=True)
        day_ticks: list[dict[str, Any]] = []
        day_meta = {"files": [], "tick_count": 0, "errors": []}
        for hour in selected_hours:
            attempt_rec = {"day": day, "hour": hour, "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
            prog["download_attempts"].append(attempt_rec)
            save_progress(prog)
            meta, ticks = download_hour(day, hour, day_dir)
            log["attempts"].append({k: v for k, v in meta.items() if k != "body"})
            prog["download_results"].append(
                {
                    "day": day,
                    "hour": hour,
                    "ok": meta["ok"],
                    "bytes": meta["file_size_bytes"],
                    "ticks": meta["tick_count"],
                    "empty": meta.get("empty"),
                    "error": meta.get("error"),
                }
            )
            save_progress(prog)
            day_meta["files"].append(meta)
            log["total_bytes"] += int(meta.get("file_size_bytes") or 0)
            if meta.get("blocker"):
                log["failed_hours"] += 1
                log["blockers"].append(meta)
                day_meta["errors"].append(meta)
            elif meta.get("empty"):
                log["empty_hours"] += 1
            elif meta.get("ok"):
                log["ok_hours"] += 1
                day_ticks.extend(ticks)
        day_meta["tick_count"] = len(day_ticks)
        ticks_path = day_dir / "ticks_decoded.jsonl"
        with ticks_path.open("w", encoding="utf-8") as f:
            for t in day_ticks:
                f.write(json.dumps(t, sort_keys=True) + "\n")
        (day_dir / "manifest.json").write_text(
            json.dumps(day_meta, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        log["days"][day] = {
            "tick_count": day_meta["tick_count"],
            "errors": len(day_meta["errors"]),
            "empty_hours": sum(1 for x in day_meta["files"] if x.get("empty")),
            "ok_hours": sum(1 for x in day_meta["files"] if x.get("ok") and not x.get("empty")),
            "failed_hours": sum(1 for x in day_meta["files"] if not x.get("ok")),
        }
        log["total_ticks"] += day_meta["tick_count"]
        all_ticks.extend(day_ticks)

    log["ended_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    log["sample_acquired"] = log["total_ticks"] > 0
    log["instrument"] = SYMBOL
    log["bid_ask_present"] = log["sample_acquired"]
    write_json("acquisition_log.json", log)
    return {"log": log, "ticks": all_ticks}
