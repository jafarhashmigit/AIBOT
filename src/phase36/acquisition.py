"""Bounded Dukascopy acquisition for Phase 36 independent dates."""

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

from phase36.constants import (
    DUKASCOPY_BASE,
    EXCLUDED_EVAL_DAYS,
    FETCH_SLEEP_S,
    FETCH_TIMEOUT_S,
    MAX_CONSECUTIVE_NETWORK_FAILURES,
    MAX_RETRIES_PER_HOUR,
    MAX_WALL_SECONDS,
    PHASE34_RAW,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
    SEED_RAW_DIRS,
    SYMBOL,
    TICKS_DIR,
    USER_AGENT,
    XAUUSD_PRICE_SCALE,
)
from phase36.progress import write_json

UTC = timezone.utc
TICK_STRUCT = struct.Struct(">IIIff")
HOURS = list(range(24))


def bi5_url(day: str, hour: int) -> str:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
    return f"{DUKASCOPY_BASE}/{SYMBOL}/{dt.year}/{dt.month - 1:02d}/{dt.day:02d}/{hour:02d}h_ticks.bi5"


def decode_ticks(body: bytes, *, day: str, hour: int) -> list[dict[str, Any]]:
    if not body:
        return []
    raw = lzma.decompress(body)
    if len(raw) % TICK_STRUCT.size != 0:
        raise ValueError(f"bad bi5 length {len(raw)}")
    hour_start = datetime.strptime(f"{day} {hour:02d}:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    out = []
    for off in range(0, len(raw), TICK_STRUCT.size):
        ms, ask_i, bid_i, ask_vol, bid_vol = TICK_STRUCT.unpack_from(raw, off)
        ts = hour_start + timedelta(milliseconds=ms)
        ts_s = ts.strftime("%Y-%m-%d %H:%M:%S")
        if ts_s > RESEARCH_CUTOFF_UTC:
            continue
        ask = ask_i / XAUUSD_PRICE_SCALE
        bid = bid_i / XAUUSD_PRICE_SCALE
        out.append(
            {
                "timestamp_utc": ts_s,
                "epoch_ms": int(ts.timestamp() * 1000),
                "bid": bid,
                "ask": ask,
                "spread": ask - bid,
                "ask_volume": float(ask_vol),
                "bid_volume": float(bid_vol),
            }
        )
    return out


def fetch_bi5(url: str) -> dict[str, Any]:
    last_err = None
    for i in range(MAX_RETRIES_PER_HOUR):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
                body = resp.read()
                return {
                    "ok": True,
                    "body": body,
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest() if body else "",
                    "empty": len(body) == 0,
                    "attempts": i + 1,
                    "error": None,
                }
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
            time.sleep(min(FETCH_SLEEP_S * (2**i), 2.0))
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(min(FETCH_SLEEP_S * (2**i), 2.0))
    return {"ok": False, "body": b"", "bytes": 0, "sha256": "", "empty": True, "attempts": MAX_RETRIES_PER_HOUR, "error": last_err}


def _seed(day: str, hour: int) -> tuple[bytes, str] | None:
    """Read-only seed from prior phase raw if day is not an excluded eval day."""
    if day in EXCLUDED_EVAL_DAYS:
        return None  # never use excluded eval-day content for replication corpus
    for root in SEED_RAW_DIRS:
        path = root / day / f"{hour:02d}h_ticks.bi5"
        if path.is_file():
            return path.read_bytes(), f"{root.parent.name}_raw_seed_non_excluded"
        empty = root / day / f"{hour:02d}h_ticks.empty"
        if empty.is_file():
            return b"", f"{root.parent.name}_raw_seed_empty_non_excluded"
    return None


def acquire_hour(day: str, hour: int, day_dir: Path, *, allow_network: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if f"{day} {hour:02d}:00:00" > RESEARCH_CUTOFF_UTC:
        return (
            {
                "ok": True,
                "empty": True,
                "skipped_after_cutoff": True,
                "tick_count": 0,
                "bytes": 0,
                "sha256": "",
                "source": "cutoff",
                "day": day,
                "hour": hour,
            },
            [],
        )
    path = day_dir / f"{hour:02d}h_ticks.bi5"
    empty_marker = day_dir / f"{hour:02d}h_ticks.empty"
    meta: dict[str, Any] = {"day": day, "hour": hour, "url": bi5_url(day, hour)}

    body: bytes | None = None
    if path.is_file():
        body = path.read_bytes()
        meta["source"] = "local_resume"
    elif empty_marker.is_file():
        body = b""
        meta["source"] = "local_resume_empty"
    else:
        seeded = _seed(day, hour)
        if seeded is not None:
            body, src = seeded
            meta["source"] = src
            if body:
                path.write_bytes(body)
            else:
                empty_marker.write_text("empty\n", encoding="utf-8")
        elif allow_network:
            result = fetch_bi5(meta["url"])
            time.sleep(FETCH_SLEEP_S)
            meta["attempts"] = result["attempts"]
            meta["network"] = True
            if result["ok"]:
                body = result["body"]
                meta["source"] = "network"
                if body:
                    path.write_bytes(body)
                else:
                    empty_marker.write_text("empty\n", encoding="utf-8")
            else:
                meta.update(
                    {
                        "ok": False,
                        "error": result["error"],
                        "empty": True,
                        "tick_count": 0,
                        "bytes": 0,
                        "sha256": "",
                    }
                )
                return meta, []
        else:
            meta.update(
                {
                    "ok": False,
                    "error": "network_disabled_or_stall_stop",
                    "empty": True,
                    "tick_count": 0,
                    "bytes": 0,
                    "sha256": "",
                }
            )
            return meta, []

    assert body is not None
    ticks = decode_ticks(body, day=day, hour=hour) if body else []
    meta.update(
        {
            "ok": True,
            "empty": len(body) == 0,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest() if body else "",
            "tick_count": len(ticks),
        }
    )
    return meta, ticks


def validate_ticks(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(ticks)
    if n == 0:
        return {"pass": False, "reason": "no_ticks", "n": 0}
    epochs = [int(t["epoch_ms"]) for t in ticks]
    unordered = sum(1 for i in range(1, n) if epochs[i] < epochs[i - 1])
    crossed = sum(1 for t in ticks if float(t["bid"]) > float(t["ask"]))
    neg = sum(1 for t in ticks if float(t["ask"]) - float(t["bid"]) < 0)
    nonpos = sum(1 for t in ticks if float(t["bid"]) <= 0 or float(t["ask"]) <= 0)
    after = sum(1 for t in ticks if t["timestamp_utc"] > RESEARCH_CUTOFF_UTC)
    hard = unordered or crossed or neg or nonpos or after
    return {
        "pass": not hard,
        "n": n,
        "unordered": unordered,
        "crossed": crossed,
        "negative_spread": neg,
        "nonpositive": nonpos,
        "after_cutoff": after,
    }


def _local_hour_coverage(day: str) -> int:
    """Count existing local hour files (phase36 then prior-phase non-excluded seeds)."""
    n = 0
    for hour in HOURS:
        if (RAW_DIR / day / f"{hour:02d}h_ticks.bi5").is_file() or (
            RAW_DIR / day / f"{hour:02d}h_ticks.empty"
        ).is_file():
            n += 1
            continue
        if day in EXCLUDED_EVAL_DAYS:
            continue
        for root in SEED_RAW_DIRS:
            if (root / day / f"{hour:02d}h_ticks.bi5").is_file() or (
                root / day / f"{hour:02d}h_ticks.empty"
            ).is_file():
                n += 1
                break
    return n


def rebuild_corpus_from_disk(days: list[str], *, allow_network: bool = True) -> dict[str, Any]:
    """Classify selected days from local files (optionally filling gaps via network)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TICKS_DIR.mkdir(parents=True, exist_ok=True)
    days = sorted(days, key=lambda d: (-_local_hour_coverage(d), d))
    started = datetime.now(UTC)
    manifest: dict[str, Any] = {
        "started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected_dates": days,
        "excluded_eval_days_blocked": sorted(EXCLUDED_EVAL_DAYS),
        "days": {},
        "complete_trading_days": [],
        "incomplete_trading_days": [],
        "failed_dates": [],
        "stopped_early": False,
        "stop_reason": None,
        "allow_network": allow_network,
        "totals": {"ok_hours": 0, "empty_hours": 0, "failed_hours": 0, "ticks": 0, "network_hours": 0},
    }
    consec_fail = 0

    for day in days:
        if day in EXCLUDED_EVAL_DAYS:
            manifest["days"][day] = {"status": "BLOCKED_EXCLUDED_EVAL_DAY"}
            manifest["failed_dates"].append({"day": day, "reason": "excluded_eval_day"})
            continue
        if allow_network and (datetime.now(UTC) - started).total_seconds() > MAX_WALL_SECONDS:
            manifest["stopped_early"] = True
            manifest["stop_reason"] = "max_wall_seconds"
            for rem in days[days.index(day) :]:
                if rem not in manifest["days"]:
                    manifest["days"][rem] = {"status": "NOT_ATTEMPTED", "reason": "wall_budget"}
                    manifest["incomplete_trading_days"].append(rem)
            break

        day_dir = RAW_DIR / day
        day_dir.mkdir(parents=True, exist_ok=True)
        day_ticks: list[dict[str, Any]] = []
        day_rec: dict[str, Any] = {"hours": [], "ok": 0, "empty": 0, "failed": 0, "tick_count": 0}
        hours_ok = True

        for hour in HOURS:
            if f"{day} {hour:02d}:00:00" > RESEARCH_CUTOFF_UTC:
                day_rec["hours"].append({"hour": hour, "ok": True, "empty": True, "skipped_after_cutoff": True})
                continue
            allow_net = allow_network and consec_fail < MAX_CONSECUTIVE_NETWORK_FAILURES
            meta, ticks = acquire_hour(day, hour, day_dir, allow_network=allow_net)
            day_rec["hours"].append({k: v for k, v in meta.items() if k != "body"})
            if meta.get("network"):
                manifest["totals"]["network_hours"] += 1
            if meta.get("ok"):
                if allow_network:
                    consec_fail = 0
                if meta.get("empty") or meta.get("skipped_after_cutoff"):
                    day_rec["empty"] += 1
                    manifest["totals"]["empty_hours"] += 1
                else:
                    day_rec["ok"] += 1
                    manifest["totals"]["ok_hours"] += 1
                    day_ticks.extend(ticks)
            else:
                day_rec["failed"] += 1
                manifest["totals"]["failed_hours"] += 1
                hours_ok = False
                if allow_network and (meta.get("network") or meta.get("error")):
                    consec_fail += 1
                    if consec_fail >= MAX_CONSECUTIVE_NETWORK_FAILURES:
                        manifest["stopped_early"] = True
                        manifest["stop_reason"] = f"consecutive_network_failures>={MAX_CONSECUTIVE_NETWORK_FAILURES}"
                        break
            if allow_network and (datetime.now(UTC) - started).total_seconds() > MAX_WALL_SECONDS:
                manifest["stopped_early"] = True
                manifest["stop_reason"] = "max_wall_seconds"
                hours_ok = False
                break

        q = validate_ticks(day_ticks)
        day_rec["quality"] = q
        day_rec["tick_count"] = len(day_ticks)
        ticks_path = TICKS_DIR / f"{day}.jsonl"
        with ticks_path.open("w", encoding="utf-8") as f:
            for t in day_ticks:
                f.write(json.dumps(t, sort_keys=True) + "\n")
        day_rec["ticks_relpath"] = f"ticks_decoded/{day}.jsonl"

        attempted = [h for h in day_rec["hours"] if not h.get("skipped_after_cutoff")]
        failed = sum(1 for h in attempted if not h.get("ok"))
        if failed == 0 and attempted and hours_ok and q.get("pass") and day_rec["tick_count"] > 0:
            day_rec["status"] = "COMPLETE"
            manifest["complete_trading_days"].append(day)
        else:
            day_rec["status"] = "INCOMPLETE"
            manifest["incomplete_trading_days"].append(day)
        manifest["days"][day] = day_rec

        if manifest["stopped_early"]:
            idx = days.index(day)
            for rem in days[idx + 1 :]:
                if rem not in manifest["days"]:
                    manifest["days"][rem] = {"status": "NOT_ATTEMPTED", "reason": manifest["stop_reason"]}
                    manifest["incomplete_trading_days"].append(rem)
            break

    all_ticks: list[dict[str, Any]] = []
    for day in manifest["complete_trading_days"]:
        path = TICKS_DIR / f"{day}.jsonl"
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_ticks.append(json.loads(line))
    all_ticks.sort(key=lambda t: int(t["epoch_ms"]))
    manifest["totals"]["ticks"] = len(all_ticks)
    manifest["n_complete_trading_days"] = len(manifest["complete_trading_days"])
    manifest["ended_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["duration_seconds"] = (datetime.now(UTC) - started).total_seconds()
    write_json("acquisition_manifest.json", manifest)
    return {"manifest": manifest, "ticks": all_ticks}


def acquire_selected_days(days: list[str]) -> dict[str, Any]:
    return rebuild_corpus_from_disk(days, allow_network=True)
