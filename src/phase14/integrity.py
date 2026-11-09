"""Integrity snapshots for Phase 1–13 protected artifacts."""

from __future__ import annotations

from phase3.nplib import sha256_file
from phase12.validation import PROTECTED_HASHES, PROJECT_ROOT
from phase12c.constants import PHASE12_PROTECTED_HASHES
from phase13.constants import PHASE12C_PROTECTED_HASHES
from phase14.constants import PHASE13_PROTECTED_HASHES


class Phase14IntegrityError(RuntimeError):
    pass


def _snap(mapping: dict) -> dict:
    out = {}
    for rel, expected in mapping.items():
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
            raise Phase14IntegrityError(f"protected artifact changed or missing: {rel}")
    return out


def snapshot_all() -> dict:
    return {
        "phase_1_11": _snap(PROTECTED_HASHES),
        "phase_12_12b": _snap(PHASE12_PROTECTED_HASHES),
        "phase_12c": _snap(PHASE12C_PROTECTED_HASHES),
        "phase_13": _snap(PHASE13_PROTECTED_HASHES),
    }
