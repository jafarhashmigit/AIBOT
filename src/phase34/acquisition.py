"""Resumable Dukascopy acquisition with seeds, bounds, and full manifests."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase34.bi5 import assert_before_cutoff, bi5_url, decode_ticks
from phase34.constants import (
    DOWNLOAD_HOURS_UTC,
    FETCH_RETRIES,
    FETCH_SLEEP_S,
    FETCH_TIMEOUT_S,
    MAX_NETWORK_HOURS,
    MAX_STORAGE_BYTES,
    MAX_WALL_SECONDS,
    PHASE25_RAW_DIR,
    PHASE33_RAW_DIR,
    RAW_DIR,
    RESEARCH_CUTOFF_UTC,
    SYMBOL,
    TICKS_DIR,
    USER_AGENT,
    select_trading_days,
)
from phase34.progress import write_json

UTC = timezone.utc


def fetch_bi5(url: str) -> dict[str, Any]:
    last_err = None
    for i in range(FETCH_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
                body = resp.read()
                return {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest() if body else "",
                    "body": body,
                    "empty": len(body) == 0,
                    "attempts": i + 1,
                    "source": "network",
                }
        except urllib.error.HTTPError as exc:
            last_err = f"HTTP {exc.code}"
            time.sleep(min(FETCH_SLEEP_S * (2**i), 2.5))
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(min(FETCH_SLEEP_S * (2**i), 2.5))
    return {
        "ok": False,
        "status": None,
        "bytes": 0,
        "sha256": "",
        "body": b"",
        "empty": True,
        "attempts": FETCH_RETRIES,
        "error": last_err,
        "source": "network",
    }


def _seed_body(day: str, hour: int) -> tuple[bytes | None, str | None]:
    """Read-only seed from Phase33 then Phase25. None = not available."""
    for root, label in ((PHASE33_RAW_DIR, "phase33_raw"), (PHASE25_RAW_DIR, "phase25_raw")):
        path = root / day / f"{hour:02d}h_ticks.bi5"
        if path.is_file():
            return path.read_bytes(), label
        empty = root / day / f"{hour:02d}h_ticks.empty"
        if empty.is_file():
            return b"", label + "_empty"
    return None, None


def acquire_hour(
    day: str,
    hour: int,
    day_dir: Path,
    *,
    allow_network: bool,
) -> dict[str, Any]:
    assert_before_cutoff(day, hour)
    url = bi5_url(day, hour)
    path = day_dir / f"{hour:02d}h_ticks.bi5"
    empty_marker = day_dir / f"{hour:02d}h_ticks.empty"
    meta: dict[str, Any] = {
        "day": day,
        "hour": hour,
        "url": url,
        "ok": False,
        "empty": False,
        "bytes": 0,
        "sha256": "",
        "tick_count": 0,
        "source": None,
        "error": None,
        "resumed": False,
        "network_used": False,
    }

    body: bytes | None = None
    if path.is_file():
        body = path.read_bytes()
        meta["resumed"] = True
        meta["source"] = "local_resume"
    elif empty_marker.is_file():
        body = b""
        meta["resumed"] = True
        meta["source"] = "local_resume_empty"
    else:
        seed, seed_label = _seed_body(day, hour)
        if seed is not None:
            body = seed
            meta["source"] = seed_label
            if body:
                path.write_bytes(body)
            else:
                empty_marker.write_text("empty\n", encoding="utf-8")
        elif allow_network:
            result = fetch_bi5(url)
            time.sleep(FETCH_SLEEP_S)
            meta["network_used"] = True
            meta["attempts"] = result["attempts"]
            if result["ok"]:
                body = result["body"]
                meta["source"] = "network"
                if body:
                    path.write_bytes(body)
                else:
                    empty_marker.write_text("empty\n", encoding="utf-8")
            else:
                meta["error"] = result.get("error")
                meta["ok"] = False
                return meta, []
        else:
            meta["error"] = "network_budget_exhausted"
            return meta, []

    assert body is not None
    meta["bytes"] = len(body)
    meta["sha256"] = hashlib.sha256(body).hexdigest() if body else ""
    meta["empty"] = len(body) == 0
    meta["ok"] = True
    ticks: list[dict[str, Any]] = []
    if body:
        ticks = decode_ticks(body, day=day, hour=hour)
        meta["tick_count"] = len(ticks)
    return meta, ticks


DST_PRIORITY_DAYS = [
    "2026-03-06",
    "2026-03-09",
    "2026-03-27",
    "2026-03-30",
]


def _day_priority(day: str) -> tuple[int, int, int, str]:
    """Lower tuple sorts first: DST → seeded → has local files → rest."""
    dst = 0 if day in DST_PRIORITY_DAYS else 1
    seeded = 0 if (PHASE25_RAW_DIR / day).is_dir() else 1
    local = 0 if (RAW_DIR / day).is_dir() else 1
    return (dst, seeded, local, day)


def rebuild_day_from_disk(day: str) -> dict[str, Any]:
    """Decode all local bi5/empty hours for a day — no network."""
    day_dir = RAW_DIR / day
    day_rec: dict[str, Any] = {
        "hours": [],
        "tick_count": 0,
        "failed": 0,
        "empty": 0,
        "ok": 0,
        "status": "NOT_ATTEMPTED",
    }
    day_ticks: list[dict[str, Any]] = []
    if not day_dir.is_dir():
        return {"day_rec": day_rec, "ticks": [], "hash_entries": []}

    hash_entries: list[dict[str, Any]] = []
    missing = 0
    for hour in DOWNLOAD_HOURS_UTC:
        hour_start = f"{day} {hour:02d}:00:00"
        if hour_start > RESEARCH_CUTOFF_UTC:
            day_rec["hours"].append(
                {
                    "day": day,
                    "hour": hour,
                    "ok": True,
                    "empty": True,
                    "skipped_after_cutoff": True,
                    "tick_count": 0,
                    "bytes": 0,
                    "sha256": "",
                    "source": "cutoff_skip",
                }
            )
            continue
        path = day_dir / f"{hour:02d}h_ticks.bi5"
        empty_marker = day_dir / f"{hour:02d}h_ticks.empty"
        if path.is_file():
            body = path.read_bytes()
            sha = hashlib.sha256(body).hexdigest() if body else ""
            ticks = decode_ticks(body, day=day, hour=hour) if body else []
            meta = {
                "day": day,
                "hour": hour,
                "ok": True,
                "empty": len(body) == 0,
                "bytes": len(body),
                "sha256": sha,
                "tick_count": len(ticks),
                "source": "disk_rebuild",
                "resumed": True,
            }
            if body:
                day_rec["ok"] += 1
                day_ticks.extend(ticks)
                hash_entries.append(
                    {
                        "day": day,
                        "hour": hour,
                        "relpath": f"{day}/{hour:02d}h_ticks.bi5",
                        "sha256": sha,
                        "bytes": len(body),
                        "source": "disk_rebuild",
                    }
                )
            else:
                day_rec["empty"] += 1
            day_rec["hours"].append(meta)
        elif empty_marker.is_file():
            day_rec["empty"] += 1
            day_rec["hours"].append(
                {
                    "day": day,
                    "hour": hour,
                    "ok": True,
                    "empty": True,
                    "bytes": 0,
                    "sha256": "",
                    "tick_count": 0,
                    "source": "disk_rebuild_empty",
                    "resumed": True,
                }
            )
        else:
            missing += 1
            day_rec["failed"] += 1
            day_rec["hours"].append(
                {
                    "day": day,
                    "hour": hour,
                    "ok": False,
                    "empty": False,
                    "bytes": 0,
                    "sha256": "",
                    "tick_count": 0,
                    "source": None,
                    "error": "missing_local_hour",
                }
            )

    day_rec["tick_count"] = len(day_ticks)
    attempted = [h for h in day_rec["hours"] if not h.get("skipped_after_cutoff")]
    if attempted and missing == 0 and day_rec["failed"] == 0:
        day_rec["status"] = "COMPLETE"
    elif attempted and (day_rec["ok"] + day_rec["empty"]) > 0:
        day_rec["status"] = "INCOMPLETE"
    else:
        day_rec["status"] = "NOT_ATTEMPTED"

    ticks_path = TICKS_DIR / f"{day}.jsonl"
    TICKS_DIR.mkdir(parents=True, exist_ok=True)
    with ticks_path.open("w", encoding="utf-8") as f:
        for t in day_ticks:
            f.write(json.dumps(t, sort_keys=True) + "\n")
    day_rec["ticks_relpath"] = f"ticks_decoded/{day}.jsonl"
    return {"day_rec": day_rec, "ticks": day_ticks, "hash_entries": hash_entries}


def rebuild_corpus_from_disk(*, days: list[str] | None = None) -> dict[str, Any]:
    """Rebuild manifests + decoded ticks from local raw files only."""
    selected = days or select_trading_days()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TICKS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "recipe": "phase34_extended_bidask_validation_v1",
        "instrument": SYMBOL,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "selected_days": selected,
        "hours_utc": DOWNLOAD_HOURS_UTC,
        "mode": "disk_rebuild",
        "days": {},
        "hash_manifest": [],
        "totals": {
            "requested_hours": 0,
            "ok_hours": 0,
            "empty_hours": 0,
            "failed_hours": 0,
            "network_hours": 0,
            "seeded_hours": 0,
            "resumed_hours": 0,
            "ticks": 0,
            "bytes": 0,
        },
        "stopped_early": False,
        "stop_reason": None,
        "complete_trading_days": [],
        "incomplete_trading_days": [],
    }
    all_ticks: list[dict[str, Any]] = []
    for day in selected:
        built = rebuild_day_from_disk(day)
        day_rec = built["day_rec"]
        manifest["days"][day] = day_rec
        manifest["hash_manifest"].extend(built["hash_entries"])
        all_ticks.extend(built["ticks"])
        for h in day_rec["hours"]:
            if h.get("skipped_after_cutoff"):
                continue
            manifest["totals"]["requested_hours"] += 1
            if h.get("ok") and h.get("empty"):
                manifest["totals"]["empty_hours"] += 1
            elif h.get("ok"):
                manifest["totals"]["ok_hours"] += 1
            else:
                manifest["totals"]["failed_hours"] += 1
            manifest["totals"]["bytes"] += int(h.get("bytes") or 0)
        manifest["totals"]["ticks"] += day_rec["tick_count"]
        if day_rec["status"] == "COMPLETE":
            manifest["complete_trading_days"].append(day)
        else:
            manifest["incomplete_trading_days"].append(day)
        (RAW_DIR / day).mkdir(parents=True, exist_ok=True)
        (RAW_DIR / day / "manifest.json").write_text(
            json.dumps(day_rec, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    manifest["n_complete_trading_days"] = len(manifest["complete_trading_days"])
    manifest["n_selected_days"] = len(selected)
    manifest["ended_utc"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json("acquisition_manifest.json", manifest)
    write_json(
        "hash_manifest.json",
        {"files": manifest["hash_manifest"], "n": len(manifest["hash_manifest"])},
    )
    return {"manifest": manifest, "ticks": all_ticks}


def run_acquisition(*, days: list[str] | None = None) -> dict[str, Any]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TICKS_DIR.mkdir(parents=True, exist_ok=True)
    selected = days or select_trading_days()
    # DST first, then seeded, then local partials — same selected set; no date substitution.
    selected = sorted(selected, key=_day_priority)
    started = datetime.now(UTC)
    start_s = started.strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest: dict[str, Any] = {
        "recipe": "phase34_extended_bidask_validation_v1",
        "instrument": SYMBOL,
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "selected_days": selected,
        "hours_utc": DOWNLOAD_HOURS_UTC,
        "started_utc": start_s,
        "limits": {
            "max_wall_seconds": MAX_WALL_SECONDS,
            "max_network_hours": MAX_NETWORK_HOURS,
            "max_storage_bytes": MAX_STORAGE_BYTES,
        },
        "days": {},
        "hash_manifest": [],
        "totals": {
            "requested_hours": 0,
            "ok_hours": 0,
            "empty_hours": 0,
            "failed_hours": 0,
            "network_hours": 0,
            "seeded_hours": 0,
            "resumed_hours": 0,
            "ticks": 0,
            "bytes": 0,
        },
        "stopped_early": False,
        "stop_reason": None,
        "complete_trading_days": [],
        "incomplete_trading_days": [],
    }

    network_used = 0
    storage = 0
    all_ticks_for_day: list[dict[str, Any]] = []

    for day in selected:
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if elapsed > MAX_WALL_SECONDS:
            manifest["stopped_early"] = True
            manifest["stop_reason"] = "max_wall_seconds"
            # Do not substitute remaining days — record as not attempted.
            for rem in selected[selected.index(day) :]:
                if rem not in manifest["days"]:
                    manifest["days"][rem] = {"status": "NOT_ATTEMPTED", "reason": "wall_budget"}
                    manifest["incomplete_trading_days"].append(rem)
            break
        if storage >= MAX_STORAGE_BYTES:
            manifest["stopped_early"] = True
            manifest["stop_reason"] = "max_storage_bytes"
            for rem in selected[selected.index(day) :]:
                if rem not in manifest["days"]:
                    manifest["days"][rem] = {"status": "NOT_ATTEMPTED", "reason": "storage_budget"}
                    manifest["incomplete_trading_days"].append(rem)
            break

        day_dir = RAW_DIR / day
        day_dir.mkdir(parents=True, exist_ok=True)
        day_rec: dict[str, Any] = {"hours": [], "tick_count": 0, "failed": 0, "empty": 0, "ok": 0}
        day_ticks: list[dict[str, Any]] = []
        hours_complete = True

        for hour in DOWNLOAD_HOURS_UTC:
            # Cutoff day: skip hours starting after cutoff
            hour_start = f"{day} {hour:02d}:00:00"
            if hour_start > RESEARCH_CUTOFF_UTC:
                day_rec["hours"].append(
                    {
                        "day": day,
                        "hour": hour,
                        "ok": True,
                        "empty": True,
                        "skipped_after_cutoff": True,
                        "tick_count": 0,
                        "bytes": 0,
                        "sha256": "",
                        "source": "cutoff_skip",
                    }
                )
                continue

            allow_net = network_used < MAX_NETWORK_HOURS
            meta, ticks = acquire_hour(day, hour, day_dir, allow_network=allow_net)

            manifest["totals"]["requested_hours"] += 1
            if meta.get("network_used"):
                network_used += 1
                manifest["totals"]["network_hours"] += 1
            if meta.get("resumed"):
                manifest["totals"]["resumed_hours"] += 1
            if meta.get("source") and str(meta["source"]).startswith("phase"):
                manifest["totals"]["seeded_hours"] += 1

            storage += int(meta.get("bytes") or 0)
            manifest["totals"]["bytes"] = storage

            if meta.get("ok"):
                if meta.get("empty"):
                    day_rec["empty"] += 1
                    manifest["totals"]["empty_hours"] += 1
                else:
                    day_rec["ok"] += 1
                    manifest["totals"]["ok_hours"] += 1
                    day_ticks.extend(ticks)
                if meta.get("sha256"):
                    manifest["hash_manifest"].append(
                        {
                            "day": day,
                            "hour": hour,
                            "relpath": f"{day}/{hour:02d}h_ticks.bi5",
                            "sha256": meta["sha256"],
                            "bytes": meta["bytes"],
                            "source": meta.get("source"),
                        }
                    )
            else:
                day_rec["failed"] += 1
                manifest["totals"]["failed_hours"] += 1
                hours_complete = False

            day_rec["hours"].append({k: v for k, v in meta.items() if k != "body"})

            elapsed = (datetime.now(UTC) - started).total_seconds()
            if elapsed > MAX_WALL_SECONDS:
                manifest["stopped_early"] = True
                manifest["stop_reason"] = "max_wall_seconds"
                hours_complete = False
                break
            if network_used >= MAX_NETWORK_HOURS and not allow_net:
                # continue with seeds only
                pass
            if storage >= MAX_STORAGE_BYTES:
                manifest["stopped_early"] = True
                manifest["stop_reason"] = "max_storage_bytes"
                hours_complete = False
                break

        day_rec["tick_count"] = len(day_ticks)
        manifest["totals"]["ticks"] += len(day_ticks)

        # Persist decoded ticks for independent recompute
        ticks_path = TICKS_DIR / f"{day}.jsonl"
        with ticks_path.open("w", encoding="utf-8") as f:
            for t in day_ticks:
                f.write(json.dumps(t, sort_keys=True) + "\n")
        day_rec["ticks_relpath"] = f"ticks_decoded/{day}.jsonl"
        (day_dir / "manifest.json").write_text(
            json.dumps(day_rec, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

        # Complete = all non-cutoff hours attempted with ok (empty allowed)
        attempted = [h for h in day_rec["hours"] if not h.get("skipped_after_cutoff")]
        failed = sum(1 for h in attempted if not h.get("ok"))
        if failed == 0 and attempted and hours_complete:
            day_rec["status"] = "COMPLETE"
            manifest["complete_trading_days"].append(day)
        else:
            day_rec["status"] = "INCOMPLETE"
            manifest["incomplete_trading_days"].append(day)
        manifest["days"][day] = day_rec
        all_ticks_for_day.extend(day_ticks)

        if manifest["stopped_early"]:
            # remaining days not attempted
            idx = selected.index(day)
            for rem in selected[idx + 1 :]:
                if rem not in manifest["days"]:
                    manifest["days"][rem] = {"status": "NOT_ATTEMPTED", "reason": manifest["stop_reason"]}
                    manifest["incomplete_trading_days"].append(rem)
            break

    ended = datetime.now(UTC)
    manifest["ended_utc"] = ended.strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["duration_seconds"] = (ended - started).total_seconds()
    manifest["n_complete_trading_days"] = len(manifest["complete_trading_days"])
    manifest["n_selected_days"] = len(selected)
    write_json("acquisition_manifest.json", manifest)
    write_json(
        "hash_manifest.json",
        {"files": manifest["hash_manifest"], "n": len(manifest["hash_manifest"])},
    )
    # Consolidate: rebuild from all local raw for the canonical selected set so
    # prior complete days are never dropped when a partial/priority run stops early.
    full_selected = select_trading_days()
    rebuilt = rebuild_corpus_from_disk(days=full_selected)
    rebuilt["manifest"]["download_pass"] = {
        "started_utc": start_s,
        "ended_utc": manifest["ended_utc"],
        "duration_seconds": manifest["duration_seconds"],
        "stopped_early": manifest["stopped_early"],
        "stop_reason": manifest["stop_reason"],
        "network_hours": manifest["totals"]["network_hours"],
        "days_processed_this_pass": list(manifest["days"].keys()),
    }
    # Preserve wall-budget signal on consolidated manifest
    if manifest["stopped_early"]:
        rebuilt["manifest"]["stopped_early"] = True
        rebuilt["manifest"]["stop_reason"] = manifest["stop_reason"]
    write_json("acquisition_manifest.json", rebuilt["manifest"])
    write_json(
        "hash_manifest.json",
        {"files": rebuilt["manifest"]["hash_manifest"], "n": len(rebuilt["manifest"]["hash_manifest"])},
    )
    return rebuilt
