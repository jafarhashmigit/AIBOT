"""Integrity snapshots for Phase 1–11 and Phase 12/12B protected files."""

from __future__ import annotations

from phase3.nplib import sha256_file
from phase12.validation import PROTECTED_HASHES, PROJECT_ROOT
from phase12c.constants import PHASE12_PROTECTED_HASHES


class Phase12CIntegrityError(RuntimeError):
    pass


def snapshot_phase1_11() -> dict:
    out = {}
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        actual = sha256_file(path) if path.exists() else None
        unchanged = actual == expected
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "unchanged": unchanged,
            "exists": path.exists(),
        }
        if not path.exists() or not unchanged:
            raise Phase12CIntegrityError(f"protected Phase 1–11 artifact changed or missing: {rel}")
    return out


def snapshot_phase12_12b() -> dict:
    out = {}
    for rel, expected in PHASE12_PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        actual = sha256_file(path) if path.exists() else None
        unchanged = actual == expected
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "unchanged": unchanged,
            "exists": path.exists(),
        }
        if not path.exists() or not unchanged:
            raise Phase12CIntegrityError(f"protected Phase 12/12B artifact changed or missing: {rel}")
    return out
