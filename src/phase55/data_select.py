"""Select a small bounded archive sample with verified bid/ask coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.archive_loader import list_archived_m5_days, load_h1, load_m5, load_ticks, ticks_by_m5_bar
from phase54.constants import HORIZON_BARS
from phase54.constants import SYMBOL
from phase55.constants import ARCHIVE_ROOT, REPORTS_DIR, file_sha256
from phase55.progress import write_json


def _manifest_sha(archive_root: Path, name: str) -> str | None:
    # Phase53 manifests live under src/data/phase53/manifests
    man_root = archive_root.parents[1] / "manifests"
    p = man_root / f"{name}.manifest.json"
    if not p.is_file():
        return None
    import json

    return json.loads(p.read_text(encoding="utf-8")).get("sha256")


def verify_day(archive_root: Path, day: str, *, decision_idx: int = 48) -> dict[str, Any]:
    m5 = load_m5(archive_root, day)
    h1 = load_h1(archive_root, day)
    ticks = load_ticks(archive_root, day)
    by = ticks_by_m5_bar(ticks)
    errors = []
    if len(m5) < decision_idx + 1 + HORIZON_BARS:
        errors.append("insufficient_bars")
    # chronological
    ts = [str(b["timestamp_utc"]) for b in m5]
    if ts != sorted(ts):
        errors.append("m5_not_chronological")
    # entry+exit path ticks
    entry_idx = decision_idx + 1
    exit_idx = entry_idx + HORIZON_BARS - 1
    missing = []
    for j in range(entry_idx, min(exit_idx + 1, len(m5))):
        bar_t = str(m5[j]["timestamp_utc"])
        tt = by.get(bar_t) or []
        if not tt:
            missing.append(bar_t)
            continue
        for t in tt:
            if t.get("bid") is None or t.get("ask") is None or float(t["ask"]) < float(t["bid"]):
                errors.append(f"invalid_tick:{bar_t}")
                break
    if missing:
        errors.append(f"missing_path_ticks_n={len(missing)}")

    m5_name = f"m5_{SYMBOL}_{day}.jsonl"
    m5_path = archive_root / "m5" / m5_name
    file_digest = file_sha256(m5_path) if m5_path.is_file() else None
    man_digest = _manifest_sha(archive_root, m5_name)

    return {
        "day": day,
        "ok": len(errors) == 0 and not missing,
        "errors": errors,
        "m5_n": len(m5),
        "h1_n": len(h1),
        "tick_n": len(ticks),
        "bars_with_ticks": sum(1 for b in m5 if by.get(str(b["timestamp_utc"]))),
        "decision_idx": decision_idx,
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
        "m5_file_sha256": file_digest,
        "m5_manifest_sha256": man_digest,
        "sha_match": (file_digest == man_digest) if (file_digest and man_digest) else None,
    }


def select_verification_sample(
    archive_root: Path | None = None,
    *,
    max_days: int = 3,
) -> dict[str, Any]:
    root = Path(archive_root or ARCHIVE_ROOT)
    days = list_archived_m5_days(root)
    selected = []
    rejected = []
    for day in days:
        if len(selected) >= max_days:
            break
        v = verify_day(root, day, decision_idx=48)
        if v["ok"]:
            selected.append(v)
        else:
            rejected.append(v)
    report = {
        "archive_root": str(root),
        "pool_n": len(days),
        "selected": selected,
        "rejected_sample": rejected[:5],
        "purpose": "software_integration_testing_only",
        "not_for": ["strategy_discovery", "training", "calibration", "profitability"],
    }
    write_json(REPORTS_DIR / "archive_sample.json", report)
    return report
