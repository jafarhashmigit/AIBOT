"""Chronological experience replay / adaptive update simulation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from phase50.availability import assert_no_leakage
from phase50.context import build_context, context_id
from phase50.experience_store import ExperienceStore, dual_query, new_experience
from phase50.learner import ShrinkageLearner
from phase50.policies import decide, estimates_from_separated

HORIZON_BARS = 12


def realized_net_r(event: dict[str, Any], action: str) -> float:
    if action == "WAIT":
        return 0.0
    outcome = event["buy"] if action == "BUY" else event["sell"]
    return float(outcome["net_r"])


def exit_ts(event: dict[str, Any]) -> str:
    return str(event["buy"]["exit_timestamp"])


def decision_timestamp(event: dict[str, Any]) -> str:
    return str(event["decision_bar"])


def run_policy_chronological(
    events: list[dict[str, Any]],
    *,
    policy_id: str,
    experience_mode: str,
    outcome_transform=None,
    freeze_estimates_after_experiences: int | None = None,
    delay_release_blocks: int = 0,
    day_to_block: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    Walk events chronologically.
    - outcome_transform: optional fn(list[rec]) -> list[rec] applied to a batch before append (randomized control)
    - freeze_estimates_after_experiences: static control
    - delay_release_blocks: delayed learning control (release hist only after N blocks)
    """
    learner = ShrinkageLearner()
    hist = ExperienceStore("HISTORICAL_HYPOTHETICAL")
    shadow = ExperienceStore("AGENT_SHADOW")
    hist.clear()
    shadow.clear()

    ordered = sorted(events, key=lambda e: (e["day"], e["decision_idx"]))
    day_to_block = day_to_block or {}

    decisions: list[dict[str, Any]] = []
    leakage_flags: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    frozen_est = None
    block_rows: list[dict[str, Any]] = []
    current_block = None

    def release_pending(now_ts: str, now_block: int) -> None:
        nonlocal pending
        ready, stay = [], []
        for rec in pending:
            src_block = int((rec.get("regime_context") or {}).get("block", 0))
            if str(rec["outcome_timestamp_utc"]) < now_ts and (now_block - src_block) >= delay_release_blocks:
                ready.append(rec)
            else:
                stay.append(rec)
        if ready and outcome_transform is not None:
            ready = outcome_transform(ready)
        for rec in ready:
            hist.append(rec)
        pending = stay

    for e in ordered:
        ts = decision_timestamp(e)
        b = int(day_to_block.get(e["day"], 0))
        ctx = build_context(e.get("features") or {})
        mstate = f"{e['day']}|{e['decision_bar']}|{context_id(ctx)}"

        release_pending(ts, b)

        bundles = dual_query(hist, shadow, ts, mode=experience_mode)
        used = (bundles.get("HISTORICAL_HYPOTHETICAL") or []) + (bundles.get("AGENT_SHADOW") or [])
        leak = assert_no_leakage(used, ts)
        if not leak["ok"]:
            leakage_flags.append(leak)

        if frozen_est is not None:
            est, meta = frozen_est, {
                "n_historical": len(bundles["HISTORICAL_HYPOTHETICAL"]),
                "n_shadow": len(bundles["AGENT_SHADOW"]),
                "mode": experience_mode,
                "static": True,
            }
        else:
            est, meta = estimates_from_separated(learner, bundles, experience_mode)
            if (
                freeze_estimates_after_experiences is not None
                and (hist.n + shadow.n) >= freeze_estimates_after_experiences
                and experience_mode != "none"
            ):
                frozen_est = est

        q = learner.q_values(est, ctx) if experience_mode != "none" else None
        decision = decide(policy_id=policy_id, q=q, experience_count=len(used))
        action = decision["action"]
        realized = realized_net_r(e, action)

        decisions.append(
            {
                "day": e["day"],
                "decision_bar": e["decision_bar"],
                "decision_timestamp_utc": ts,
                "action": action,
                "realized_net_r": realized,
                "reason": decision["reason"],
                "experience_count": decision["experience_count"],
                "n_historical_available": meta.get("n_historical", 0) if experience_mode != "none" else 0,
                "n_shadow_available": meta.get("n_shadow", 0) if experience_mode != "none" else 0,
                "q_detail": decision.get("q"),
                "context": ctx,
                "block": b,
            }
        )

        # Queue counterfactual HISTORICAL experiences (not AGENT_SHADOW)
        ot = exit_ts(e)
        for a in ("BUY", "SELL", "WAIT"):
            nr = realized_net_r(e, a)
            rec = new_experience(
                source="HISTORICAL_HYPOTHETICAL",
                decision_timestamp_utc=ts,
                market_state_id=mstate,
                action=a,
                decision_context=ctx,
                actual_costed_outcome_net_r=nr,
                outcome_horizon_bars=HORIZON_BARS,
                outcome_timestamp_utc=ot,
                regime_context={"day": e["day"], "block": b, "overlap": ctx.get("overlap")},
            )
            pending.append(rec)

        if current_block is not None and b != current_block:
            block_rows.append(_block_summary(decisions, current_block, hist.n, shadow.n))
        current_block = b

    # End: do not force-release beyond chronology for final metrics on decisions already made
    if current_block is not None:
        block_rows.append(_block_summary(decisions, current_block, hist.n, shadow.n))

    hist.flush()
    shadow.flush()

    return {
        "policy_id": policy_id,
        "experience_mode": experience_mode,
        "decisions": decisions,
        "n_decisions": len(decisions),
        "hist_n": hist.n,
        "shadow_n": shadow.n,
        "pending_unreleased": len(pending),
        "leakage_ok": len(leakage_flags) == 0,
        "leakage_flags": leakage_flags[:5],
        "block_rows": block_rows,
        "agent_shadow_empty": shadow.n == 0,
        "action_counts": dict(Counter(d["action"] for d in decisions)),
    }


def _block_summary(decisions: list[dict[str, Any]], block: int, hist_n: int, shadow_n: int) -> dict[str, Any]:
    subset = [d for d in decisions if d.get("block") == block]
    if not subset:
        return {"block": block, "n": 0}
    c = Counter(d["action"] for d in subset)
    rs = [float(d["realized_net_r"]) for d in subset]
    return {
        "block": block,
        "n": len(subset),
        "action_counts": dict(c),
        "mean_net_r": sum(rs) / len(rs),
        "hist_n_end": hist_n,
        "shadow_n_end": shadow_n,
    }
