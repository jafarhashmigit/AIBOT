"""Stable MarketSnapshot commit — exclude ephemeral fields from hash identity."""

from __future__ import annotations

from typing import Any

from phase64_1.market_snapshot import MarketSnapshotStore, build_snapshot_from_observation


def commit_stable_observation_snapshot(
    store: MarketSnapshotStore,
    obs: dict[str, Any],
    *,
    account_profile: dict[str, Any] | None = None,
    source_domain: str = "AGENT_SHADOW",
) -> dict[str, Any]:
    """
    Snapshot hash must be stable across retries of the same logical bar.
    Ephemeral observation_id / created_iso must not create a new canonical decision.
    """
    stable_obs = dict(obs)
    # Bind ephemeral IDs to bar identity for hashing/storage consistency
    bar_anchor = (
        str(obs.get("market_state_id") or "")
        or f"{obs.get('symbol')}:{obs.get('timeframe')}:{obs.get('bar_timestamp_utc')}"
    )
    stable_obs["observation_id"] = bar_anchor or "UNKNOWN"
    stable_obs["created_iso"] = str(obs.get("bar_timestamp_utc") or "UNKNOWN")
    stable_obs["observation_timestamp_utc"] = str(obs.get("bar_timestamp_utc") or "UNKNOWN")
    body = build_snapshot_from_observation(
        stable_obs, account_profile=account_profile, source_domain=source_domain
    )
    # Preserve real observation_id in a non-hashed extension after commit by storing in payload note
    # (hash already computed inside build/commit from body without extra fields)
    rec = store.commit(body)
    # Annotate without mutating immutable hash identity (append-only note on in-memory copy only)
    out = dict(rec)
    out["ephemeral_observation_id"] = obs.get("observation_id")
    return out
