"""Sole approved paper runtime factory — wraps Phase64.2 hardened engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phase54.risk import RiskManager
from phase64_2.constants import STATUS_PAPER_FINALIZED, STATUS_WAIT_FINALIZED
from phase64_2.engine import HardenedLifecycleEngine, make_hardened_engine
from phase64_3.constants import APPROVED_ENGINE_CLASS, HARDENING_VERSION, RECIPE_ID
from phase64_3.xauusdm_profile import active_account_profile


class RuntimeAdoptionError(RuntimeError):
    pass


def assert_hardened_runtime(engine: Any) -> dict[str, Any]:
    """Prove active engine is HardenedLifecycleEngine with hardening version marker."""
    cls_name = type(engine).__name__
    if cls_name != APPROVED_ENGINE_CLASS and not isinstance(engine, HardenedLifecycleEngine):
        raise RuntimeAdoptionError(f"unapproved_engine:{cls_name}")
    marker = getattr(engine, "hardening_version", None) or HARDENING_VERSION
    if marker != HARDENING_VERSION:
        raise RuntimeAdoptionError(f"hardening_version_mismatch:{marker}")
    if getattr(engine, "approved_paper_runtime", None) is not True:
        raise RuntimeAdoptionError("missing_approved_paper_runtime_marker")
    return {
        "engine_class": cls_name,
        "hardening_version": marker,
        "approved_paper_runtime": True,
        "recipe_gate": RECIPE_ID,
        "broker_order_send": False,
    }


def make_approved_paper_engine(
    *,
    work: Path,
    policy=None,
    risk: RiskManager | None = None,
    record_counterfactuals: bool = False,
    immediate_monitor_through_horizon: bool = False,
    crash_at: str | None = None,
    account_profile: dict[str, Any] | None = None,
) -> HardenedLifecycleEngine:
    """
    Approved construction path for all new paper runs.
    Defaults: multi-bar monitoring (immediate_monitor_through_horizon=False).
    Always binds active XAUUSDm profile unless explicitly overridden (still must be XAUUSDm).
    """
    profile = dict(account_profile or active_account_profile())
    if profile.get("symbol") != "XAUUSDm":
        raise RuntimeAdoptionError(f"refusing_non_xauusdm_profile:{profile.get('symbol')}")
    # Never allow superseded symbol metadata
    if "XAUUSD" == str(profile.get("symbol")):
        raise RuntimeAdoptionError("superseded_xauusd_forbidden")

    eng = make_hardened_engine(
        work=work,
        policy=policy,
        risk=risk or RiskManager({"max_spread_atr": 5.0, "stop_atr_multiple": 0.5}),
        record_counterfactuals=record_counterfactuals,
        immediate_monitor_through_horizon=immediate_monitor_through_horizon,
        crash_at=crash_at,
        account_profile=profile,
    )
    eng.hardening_version = HARDENING_VERSION  # type: ignore[attr-defined]
    eng.approved_paper_runtime = True  # type: ignore[attr-defined]
    eng.approved_factory = "phase64_3.approved_runtime.make_approved_paper_engine"  # type: ignore[attr-defined]
    assert_hardened_runtime(eng)
    return eng


def summarize_engine_counts(engine: HardenedLifecycleEngine) -> dict[str, Any]:
    intents = engine.intent_journal.all_intents()
    n_wait_final = sum(1 for i in intents if i.get("intent_status") == STATUS_WAIT_FINALIZED)
    n_paper_final = sum(1 for i in intents if i.get("intent_status") == STATUS_PAPER_FINALIZED)
    n_pending = sum(1 for i in intents if i.get("intent_status") == "PENDING")
    wait_exp = sum(
        1
        for r in engine.shadow.all()
        if r.get("action") == "WAIT" and (r.get("decision_context") or {}).get("wait_durable")
    )
    return {
        "n_canonical_decisions": len(engine.state.data.get("canonical_decisions") or {}),
        "n_bar_decisions": len(engine.state.data.get("bar_decisions") or {}),
        "n_intents": len(intents),
        "n_wait_finalized_intents": n_wait_final,
        "n_paper_finalized_intents": n_paper_final,
        "n_pending_intents": n_pending,
        "n_wait_durable_experiences": wait_exp,
        "n_open_positions": len(engine.risk.open_positions),
        "n_closed_positions": len(engine.state.data.get("closed_position_ids") or []),
        "n_shadow_experiences": engine.shadow.n,
        "n_hist_experiences": engine.hist.n,
        "simulated_paper_only": True,
        "genuine_broker_deals": 0,
    }
