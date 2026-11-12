"""Stable evidence identity and idempotency keys."""

from __future__ import annotations

from typing import Any

from phase64_8.constants import JOURNAL_SCHEMA_VERSION, UNKNOWN, canonical_json_sha256, sha256_hex


def account_fingerprint(account: dict[str, Any]) -> str:
    raw = (
        f"{account.get('login')}|{account.get('server')}|"
        f"{account.get('trade_mode')}|{account.get('company')}|{account.get('currency')}"
    )
    return sha256_hex(raw)


def body_hash(payload: dict[str, Any]) -> str:
    return canonical_json_sha256(payload)


def event_id(*, kind: str, stable_key: str, body: str) -> str:
    return sha256_hex(f"{JOURNAL_SCHEMA_VERSION}:{kind}:{stable_key}:{body}")


def stable_key_position(ticket: Any) -> str:
    if ticket in (None, "", 0, "0"):
        return f"obs_position:{UNKNOWN}"
    return f"position:{ticket}"


def stable_key_order(ticket: Any, *, historical: bool = False) -> str:
    prefix = "hist_order" if historical else "order"
    if ticket in (None, "", 0, "0"):
        return f"obs_{prefix}:{UNKNOWN}"
    return f"{prefix}:{ticket}"


def stable_key_deal(ticket: Any) -> str:
    if ticket in (None, "", 0, "0"):
        return f"obs_deal:{UNKNOWN}"
    return f"deal:{ticket}"


def stable_key_account(fingerprint: str, retrieved_at: str) -> str:
    """Account snapshots are observation-level (no durable broker snapshot id)."""
    return f"obs_account:{fingerprint}:{retrieved_at}"


def is_observation_level(stable_key: str) -> bool:
    return stable_key.startswith("obs_")


def identity_class(stable_key: str) -> str:
    return "OBSERVATION" if is_observation_level(stable_key) else "EXECUTION_IDENTITY"
