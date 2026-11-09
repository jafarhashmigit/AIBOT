"""Integrity checks for Phase 8 inputs. Does not rewrite Phase 2/7 files."""

from __future__ import annotations

from pathlib import Path

from phase3.nplib import sha256_file
from phase8.constants import PHASE2_OOS_PATH, PHASE2_OOS_SHA256, RESEARCH_CUTOFF


class Phase8IntegrityError(RuntimeError):
    pass


def confirm_phase2_oos_unchanged() -> dict:
    digest = sha256_file(PHASE2_OOS_PATH)
    if digest != PHASE2_OOS_SHA256:
        raise Phase8IntegrityError("Phase 2 OOS SHA-256 changed; stopping")
    return {"path": str(PHASE2_OOS_PATH), "sha256": digest, "unchanged": True}


def assert_timestamp_allowed(stamp: str) -> None:
    if stamp > RESEARCH_CUTOFF:
        raise Phase8IntegrityError(f"timestamp {stamp} after cutoff")


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise Phase8IntegrityError(f"{label} missing: {path}")
