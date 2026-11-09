"""Phase 2 OOS integrity. Stop if the frozen artifact changed."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from phase3.nplib import sha256_file
from phase7.constants import (
    EXPECTED_PER_SIDE,
    EXPECTED_ROWS,
    OOS_PATH,
    PHASE2_OOS_SHA256,
    RESEARCH_CUTOFF,
)


class IntegrityError(RuntimeError):
    pass


def file_sha256(path: Path = OOS_PATH) -> str:
    return sha256_file(path)


def audit_rows(rows: list[dict]) -> dict:
    n = len(rows)
    sides = Counter(r["side"] for r in rows)
    folds = Counter(r["fold_id"] for r in rows)
    times = [r["decision_time"] for r in rows]
    after = sum(1 for t in times if t > RESEARCH_CUTOFF)
    digest = file_sha256()
    report = {
        "n": n,
        "sides": dict(sides),
        "folds": dict(folds),
        "min_timestamp": min(times) if times else None,
        "max_timestamp": max(times) if times else None,
        "after_cutoff": after,
        "sha256": digest,
        "expected_sha256": PHASE2_OOS_SHA256,
        "unchanged": digest == PHASE2_OOS_SHA256,
    }
    if digest != PHASE2_OOS_SHA256:
        raise IntegrityError("Phase 2 OOS SHA-256 differs from the frozen artifact; stopping")
    if n != EXPECTED_ROWS:
        raise IntegrityError(f"Phase 2 OOS row count {n} != {EXPECTED_ROWS}")
    if sides.get("BUY") != EXPECTED_PER_SIDE or sides.get("SELL") != EXPECTED_PER_SIDE:
        raise IntegrityError(f"Phase 2 OOS side counts {dict(sides)}")
    if after:
        raise IntegrityError(f"{after} OOS rows after cutoff")
    return report
