"""Protected-artifact hashes and temporal assertions."""

from __future__ import annotations

from pathlib import Path

from phase3.nplib import sha256_file
from phase9.constants import PROJECT_ROOT, PROTECTED_HASHES


class IntegrityError(RuntimeError):
    pass


def snapshot_protected() -> dict:
    out = {}
    for rel, expected in PROTECTED_HASHES.items():
        path = PROJECT_ROOT / rel
        actual = sha256_file(path) if path.exists() else None
        out[rel] = {
            "expected": expected,
            "actual": actual,
            "unchanged": actual == expected,
            "exists": path.exists(),
        }
        if path.exists() and actual != expected:
            raise IntegrityError(f"HARD FAILURE: protected artifact changed: {rel}")
        if not path.exists():
            raise IntegrityError(f"HARD FAILURE: protected artifact missing: {rel}")
    return out
