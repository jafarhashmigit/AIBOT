"""Outcome lifecycle — reuse Phase 18 definitions; AGENT_SHADOW only."""

from __future__ import annotations

from typing import Any

from phase18.experience import ExperienceStore
from phase18.outcomes import atr_at_signal, create_pending_outcomes, evaluate_horizon_outcome
from phase28.journals import OutcomeStore
from phase29.constants import SOURCE_HISTORICAL, SOURCE_SHADOW


def pending_from_decision(decision: dict[str, Any], *, atr: float | None) -> list[dict[str, Any]]:
    if not decision.get("accepted"):
        return []
    action = str(decision.get("experimental_action", "WAIT")).upper()
    if action not in {"BUY", "SELL"}:
        return []
    rows = create_pending_outcomes(
        {
            "decision_id": decision["decision_id"],
            "decision_timestamp_utc": decision["decision_timestamp_utc"],
            "experimental_action": action,
            "symbol": decision.get("symbol", "XAUUSD"),
        },
        atr=atr if atr is not None else decision.get("atr"),
    )
    for r in rows:
        r["observer_id"] = decision["observer_id"]
        r["experience_source"] = SOURCE_SHADOW
        r["signal_bar_open_utc"] = decision.get("signal_bar_open_utc")
        if decision.get("tp_level") is not None:
            r["tp_level"] = f"{float(decision['tp_level']):.8f}"
        if decision.get("sl_level") is not None:
            r["sl_level"] = f"{float(decision['sl_level']):.8f}"
    return rows


def resolve_observer_outcomes(
    *,
    decisions: list[dict[str, Any]],
    outcome_store: OutcomeStore,
    experience: ExperienceStore,
    bars: list[dict[str, Any]],
    as_of: str,
) -> dict[str, Any]:
    sorted_bars = sorted(bars, key=lambda b: b["bar_open_timestamp_utc"])
    if not sorted_bars:
        return {"finalized": [], "experience_added": 0, "still_pending": 0}

    existing = {r["outcome_event_id"]: r for r in outcome_store.read_all()}
    dec_by_id = {d["decision_id"]: d for d in decisions}
    for d in decisions:
        if not d.get("accepted"):
            continue
        try:
            opens = [b["bar_open_timestamp_utc"] for b in sorted_bars]
            signal_pos = opens.index(d["signal_bar_open_utc"])
            atr = atr_at_signal(sorted_bars, signal_pos)
        except Exception:
            atr = d.get("atr")
        for row in pending_from_decision(d, atr=float(atr) if atr is not None else None):
            if row["outcome_event_id"] not in existing:
                outcome_store.append(row)
                existing[row["outcome_event_id"]] = row

    finalized = []
    exp_added = 0
    still_pending = 0
    for pending in list(outcome_store.read_all()):
        if pending.get("status") != "PENDING":
            continue
        dec = dec_by_id.get(pending["decision_id"])
        if not dec:
            still_pending += 1
            continue
        signal_open = pending.get("signal_bar_open_utc") or dec.get("signal_bar_open_utc")
        if not signal_open:
            still_pending += 1
            continue
        try:
            opens = [b["bar_open_timestamp_utc"] for b in sorted_bars]
            signal_pos = opens.index(signal_open)
            atr = atr_at_signal(sorted_bars, signal_pos)
        except Exception:
            still_pending += 1
            continue
        updated = evaluate_horizon_outcome(
            pending,
            bars=sorted_bars,
            signal_bar_open_utc=signal_open,
            atr=atr,
            as_of_utc=as_of,
        )
        if updated.get("status") == "PENDING":
            still_pending += 1
            continue
        if (updated.get("experience_source") or SOURCE_SHADOW) == SOURCE_HISTORICAL:
            raise RuntimeError("HARD FAILURE: forward outcome tagged HISTORICAL_HYPOTHETICAL")
        outcome_store.upsert_status(updated["outcome_event_id"], updated)
        finalized.append(updated)
        if str(updated.get("experience_recorded", "0")) != "1":
            row = experience.add_shadow_from_outcome(
                updated,
                feature_context_ref=dec.get("decision_id", ""),
                selected_horizon="NOT ESTABLISHED",
            )
            if row is not None:
                outcome_store.upsert_status(
                    updated["outcome_event_id"],
                    {**updated, "experience_recorded": "1"},
                )
                exp_added += 1
    return {"finalized": finalized, "experience_added": exp_added, "still_pending": still_pending}


def summarize_outcomes(outcome_rows: list[dict[str, Any]]) -> dict[str, Any]:
    matured = [r for r in outcome_rows if r.get("status") not in {None, "PENDING", ""}]
    pending = [r for r in outcome_rows if r.get("status") == "PENDING"]
    h12 = [r for r in matured if r.get("horizon_id") == "H12"]
    rs = []
    for r in h12:
        try:
            rs.append(float(r.get("realized_r")))
        except (TypeError, ValueError):
            pass
    return {
        "n_outcome_rows": len(outcome_rows),
        "n_pending": len(pending),
        "n_matured": len(matured),
        "n_matured_h12": len(h12),
        "mean_realized_r_h12": (sum(rs) / len(rs)) if rs else None,
        "sample_size_h12": len(rs),
    }
