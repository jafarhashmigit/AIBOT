"""Phase 13 reference comparator ONLY. Not the independent validation path."""

from __future__ import annotations

from phase13.data_loader import load_research_bundle
from phase13.h1_context import build_h1_lookup
from phase13.hypotheses import generate_decisions


def phase13_reference_trades() -> dict:
    """Rebuild Phase 13 H13_C decisions via Phase 13 modules for mismatch audit."""
    bundle = load_research_bundle()
    generated = generate_decisions(bundle)
    decisions = generated["decisions"]["H13_C_H1_PULLBACK"]
    trades = []
    for t, action in decisions.items():
        if action == "WAIT":
            continue
        outcome = bundle["outcomes"].get((t, action))
        if outcome is None:
            continue
        from phase13.data_loader import fold_of
        trades.append({
            "decision_time": t,
            "side": action,
            "fold_id": fold_of(t),
            "net_r": outcome["net_r"],
            "net_pnl": outcome["net_pnl"],
            "initial_risk": outcome["initial_risk"],
            "entry_fill": None,
        })
    return {
        "source": "phase13.generate_decisions[H13_C_H1_PULLBACK]",
        "role": "reference_comparator_only",
        "n_trades": len(trades),
        "trades": trades,
        "h1_coverage": generated["h1_coverage"],
        "cuts_by_fold": {
            fid: {
                "close_ema_p25": generated["cuts_by_fold"][fid]["close_ema_p25"],
                "close_ema_p75": generated["cuts_by_fold"][fid]["close_ema_p75"],
                "n_train_rows": generated["cuts_by_fold"][fid]["n_train_rows"],
            }
            for fid in generated["cuts_by_fold"]
        },
        # Keep lookup construction exercised for audit completeness
        "h1_lookup_len": len(build_h1_lookup(bundle["h1_rows"])),
    }


def compare_trade_sets(independent: list[dict], reference: list[dict]) -> dict:
    ind = {(r["decision_time"], r["side"]): r for r in independent}
    ref = {(r["decision_time"], r["side"]): r for r in reference}
    only_ind = sorted(set(ind) - set(ref))
    only_ref = sorted(set(ref) - set(ind))
    both = sorted(set(ind) & set(ref))
    r_mismatches = []
    for key in both:
        a = ind[key]["net_r"]
        b = ref[key]["net_r"]
        if abs(a - b) > 1e-12:
            r_mismatches.append({"key": key, "independent_net_r": a, "reference_net_r": b})
    return {
        "n_independent": len(ind),
        "n_reference": len(ref),
        "n_intersection": len(both),
        "only_independent": [{"decision_time": k[0], "side": k[1]} for k in only_ind[:50]],
        "only_reference": [{"decision_time": k[0], "side": k[1]} for k in only_ref[:50]],
        "only_independent_count": len(only_ind),
        "only_reference_count": len(only_ref),
        "net_r_mismatches": r_mismatches[:50],
        "net_r_mismatch_count": len(r_mismatches),
        "exact_set_match": len(only_ind) == 0 and len(only_ref) == 0,
        "exact_economic_match": len(only_ind) == 0 and len(only_ref) == 0 and len(r_mismatches) == 0,
    }
