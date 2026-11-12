"""Canonical decision identity stability — one logical decision per bar."""

from __future__ import annotations

from typing import Any

from phase64_2.constants import DECISIONS_PER_BAR_POLICY, canonical_json_sha256


class IdentityConflictError(ValueError):
    pass


def bar_key(day: str, idx: int) -> str:
    return f"{day}:{idx}"


def register_or_reuse_bar_decision(
    state_map: dict[str, Any],
    *,
    day: str,
    idx: int,
    canonical_decision_id: str,
    snapshot_hash: str,
    proposed_action: str | None,
) -> dict[str, Any]:
    """
    Policy: ONE_LOGICAL_DECISION_PER_BAR.
    Same bar + same snapshot_hash → reuse.
    Same bar + different snapshot_hash → conflict (no accidental duplicate decision).
    Historical IDs never rewritten.
    """
    key = bar_key(day, idx)
    existing = state_map.get(key)
    if existing is None:
        entry = {
            "canonical_decision_id": canonical_decision_id,
            "snapshot_hash": snapshot_hash,
            "proposed_action": proposed_action,
            "n_registrations": 1,
        }
        state_map[key] = entry
        return {"status": "REGISTERED", "entry": entry, "policy": DECISIONS_PER_BAR_POLICY}

    if existing.get("snapshot_hash") != snapshot_hash:
        raise IdentityConflictError(
            f"conflicting_snapshot_same_bar:{key}:"
            f"{existing.get('snapshot_hash')}!={snapshot_hash}"
        )
    if existing.get("canonical_decision_id") != canonical_decision_id:
        # Same snapshot must yield same canonical id — if not, identity bug
        raise IdentityConflictError(
            f"canonical_id_mismatch_same_snapshot:{key}:"
            f"{existing.get('canonical_decision_id')}!={canonical_decision_id}"
        )
    if (
        proposed_action is not None
        and existing.get("proposed_action") not in (None, proposed_action)
    ):
        raise IdentityConflictError(
            f"conflicting_action_same_bar:{key}:"
            f"{existing.get('proposed_action')}!={proposed_action}"
        )
    existing["n_registrations"] = int(existing.get("n_registrations") or 1) + 1
    return {"status": "REUSED", "entry": existing, "policy": DECISIONS_PER_BAR_POLICY}


def identity_stability_report(
    *,
    duplicate_obs_same_id: bool,
    restart_replay_same_id: bool,
    changed_hash_rejected: bool,
    one_intent_per_decision: bool,
) -> dict[str, Any]:
    out = {
        "policy": DECISIONS_PER_BAR_POLICY,
        "permits_multiple_decisions_per_bar": False,
        "duplicate_observation_stable_id": duplicate_obs_same_id,
        "restart_replay_stable_id": restart_replay_same_id,
        "changed_snapshot_hash_rejected": changed_hash_rejected,
        "one_intent_per_logical_decision": one_intent_per_decision,
        "historical_ids_rewritten": False,
        "pass": all(
            [
                duplicate_obs_same_id,
                restart_replay_same_id,
                changed_hash_rejected,
                one_intent_per_decision,
            ]
        ),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
