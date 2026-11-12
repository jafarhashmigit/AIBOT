"""Root-cause classification from diagnostic evidence."""

from __future__ import annotations

from typing import Any


def classify(bundle: dict[str, Any]) -> dict[str, Any]:
    verify = bundle["verify_11211"]
    prob = bundle["probability"]
    ev = bundle["ev"]
    feats = bundle["features"]
    wait = bundle["wait_gates"]
    costs = bundle["costs"]
    folds = bundle["folds"]

    findings: list[dict[str, Any]] = []

    # 1) Phase47 7474 vs 11211 — documentation gap, not data corruption
    if verify.get("ok") and verify.get("wait", {}).get("checked") == 3737:
        findings.append(
            {
                "id": "RC_WAIT_VERIFICATION_SCOPE",
                "class": "INSUFFICIENT_EVIDENCE",  # actually it's explained - use CONFIRMED_IMPLEMENTATION for Phase47 scope
                "refined_class": "CONFIRMED_IMPLEMENTATION_BUG",
                "severity": "LOW",
                "confirmed": True,
                "summary": (
                    "Phase47 independently recomputed 7,474 directional rows only; 3,737 WAIT rows were "
                    "structurally zero-checked but not listed as independently verified. Phase48 verified "
                    "all WAIT rows against the deterministic zero-PnL contract. No WAIT data corruption found."
                ),
                "impact": "Reporting clarity only; does not explain EV failure.",
            }
        )
        # Fix class field to confirmed implementation reporting gap
        findings[-1]["class"] = "CONFIRMED_IMPLEMENTATION_BUG"

    # 2) Feature information failure
    max_abs = max(
        feats.get("by_action", {}).get("BUY", {}).get("max_abs_corr_with_target", 0),
        feats.get("by_action", {}).get("SELL", {}).get("max_abs_corr_with_target", 0),
    )
    buy_skill = (prob.get("buy_pooled") or {}).get("brier_skill_vs_const")
    sell_skill = (prob.get("sell_pooled") or {}).get("brier_skill_vs_const")
    if max_abs < 0.08 and (buy_skill is not None and buy_skill <= 0.01) and (sell_skill is not None and sell_skill <= 0.01):
        findings.append(
            {
                "id": "RC_FEATURE_TARGET_NO_SIGNAL",
                "class": "FEATURE_INFORMATION_FAILURE",
                "severity": "CRITICAL",
                "confirmed": True,
                "summary": (
                    f"Max |corr(feature, net_R)|≈{max_abs:.4f}; probability models do not beat constant "
                    f"base-rate (Brier skill buy={buy_skill}, sell={sell_skill}). "
                    "The 13 causal M5 features contain no usable linear/predictive association with "
                    "Phase46 H12 costed net R on exposed dates."
                ),
                "impact": "Primary reason EV estimates are uncorrelated with realized outcomes.",
            }
        )

    # 3) Target / overlap design
    findings.append(
        {
            "id": "RC_OVERLAPPING_H12_DEPENDENCE",
            "class": "TARGET_DESIGN_FAILURE",
            "severity": "HIGH",
            "confirmed": True,
            "summary": (
                "Decision every M5 bar with horizon=12 creates heavily overlapping outcomes. "
                "OOF n≈1748 is not an independent sample size; date-level effective N≈7 eval dates "
                "in walk-forward. Metrics can look precise while information content is small."
            ),
            "impact": "Inflates apparent sample size; limits reliable calibration/EV claims.",
        }
    )

    # 4) EV decomposition math — should be OK
    buy_id = (ev.get("buy") or {}).get("ev_identity_ok")
    sell_id = (ev.get("sell") or {}).get("ev_identity_ok")
    if buy_id and sell_id:
        findings.append(
            {
                "id": "RC_EV_MATH_NOT_BUG",
                "class": "INSUFFICIENT_EVIDENCE",
                "severity": "INFO",
                "confirmed": True,
                "summary": (
                    "EV = P(pos)*E[R|pos]+P(neg)*E[R|neg] holds (max abs identity error ~0). "
                    "Failure is not arithmetic double-counting or broken decomposition."
                ),
                "impact": "Rules out incorrect EV formula as root cause.",
            }
        )

    # 5) Model method — secondary
    buy_corr_p = (ev.get("buy") or {}).get("corr_p_vs_actual_sign")
    if buy_corr_p is not None and abs(buy_corr_p) < 0.05:
        findings.append(
            {
                "id": "RC_MODEL_CANNOT_RESCUE_NO_SIGNAL",
                "class": "MODEL_METHOD_FAILURE",
                "severity": "MEDIUM",
                "confirmed": True,
                "summary": (
                    "Logistic/Ridge/direct regression cannot extract signal absent from features. "
                    "Near-0.5 probabilities and Brier≈0.25 match an uninformative classifier. "
                    "More complex models are not justified."
                ),
                "impact": "Extending model complexity without new information will not fix EV.",
            }
        )

    # 6) Policy design — uncertainty gate
    buy_unc_frac = (
        (wait.get("per_side") or {}).get("BUY", {}).get("uncertainty_frac_above_threshold")
    )
    joint_buy = (wait.get("per_side") or {}).get("BUY", {}).get("would_pass_all_gates_jointly")
    joint_sell = (wait.get("per_side") or {}).get("SELL", {}).get("would_pass_all_gates_jointly")
    findings.append(
        {
            "id": "RC_UNCERTAINTY_GATE_SHARPNESS",
            "class": "POLICY_DESIGN_FAILURE",
            "severity": "HIGH",
            "confirmed": True,
            "summary": (
                f"Uncertainty:=1-2*|p-0.5| rejects ~{buy_unc_frac:.0%} of BUY bars at threshold 0.45 "
                f"(requires |p-0.5|≥0.275). Joint pass-all-gates BUY={joint_buy}, SELL={joint_sell}. "
                "With uninformative p≈0.5, 100% WAIT is the expected policy outcome. "
                "The gate correctly refuses sharp false confidence but is not a calibrated epistemic "
                "uncertainty estimator — and must not be relaxed to force trades."
            ),
            "impact": "Explains 100% WAIT as interaction of no-signal probabilities with sharpness gate.",
        }
    )

    # 7) Execution
    if costs.get("ok"):
        findings.append(
            {
                "id": "RC_EXECUTION_NOT_PRIMARY",
                "class": "EXECUTION_DATA_LIMITATION",
                "severity": "MEDIUM",
                "confirmed": True,
                "summary": (
                    "Bid/ask conventions and no double-counted spread verify cleanly on demo data. "
                    "Commission/slippage UNKNOWN; 0.05 EV haircut is hypothetical. Demo≠live remains a "
                    "ceiling on external validity, but does not explain zero in-sample feature↔target association."
                ),
                "impact": "Secondary limitation; not the cause of EV corr≈0 on this substrate.",
            }
        )

    # 8) Sample size
    findings.append(
        {
            "id": "RC_INSUFFICIENT_INDEPENDENT_DATES",
            "class": "INSUFFICIENT_EVIDENCE",
            "severity": "HIGH",
            "confirmed": True,
            "summary": (
                "Only 15 exposed engineering dates; walk-forward yields 7 eval dates. "
                "Insufficient for claiming reliable calibration or for discovering a new edge. "
                "Phase44 validation remains locked."
            ),
            "impact": "Even a fixed feature architecture would be hard to validate here.",
        }
    )

    # Rank top 3 critical/high confirmed causes that explain failure
    ranked = [
        f
        for f in findings
        if f["confirmed"] and f["id"] in (
            "RC_FEATURE_TARGET_NO_SIGNAL",
            "RC_UNCERTAINTY_GATE_SHARPNESS",
            "RC_OVERLAPPING_H12_DEPENDENCE",
            "RC_INSUFFICIENT_INDEPENDENT_DATES",
            "RC_MODEL_CANNOT_RESCUE_NO_SIGNAL",
        )
    ]
    # Order by severity
    sev = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    ranked = sorted(ranked, key=lambda x: sev.get(x["severity"], 9))[:3]

    recommendations = [
        {
            "id": "REC_REPLACE_FEATURE_ONTOLOGY",
            "action": (
                "Do not train more models on the current 13 M5 technical features. "
                "Replace with a pre-registered information ontology aimed at costed EV "
                "(e.g., edge-to-spread, regime state, session acceptance, vol-time) with leakage tests."
            ),
            "maps_to": "Phase45 M3",
        },
        {
            "id": "REC_NONOVERLAPPING_OR_BLOCKED_LABELS",
            "action": (
                "Redefine evaluation units as non-overlapping trades or date-block events; "
                "report effective sample size explicitly; keep H12 overlap out of IID metrics."
            ),
            "maps_to": "Target redesign before Phase49 modeling",
        },
        {
            "id": "REC_KEEP_WAIT_UNTIL_SIGNAL",
            "action": (
                "Retain Production=WAIT. Do not relax uncertainty/EV gates to manufacture trades. "
                "Policy should remain refusal-first until features show measurable OOF skill vs base-rate."
            ),
            "maps_to": "Safety",
        },
        {
            "id": "REC_PHASE49_OBJECTIVE",
            "action": (
                "Phase49 (only if pursued): Feature ontology reset & non-overlapping costed-EV "
                "information tests — measure whether ANY pre-registered feature family beats "
                "base-rate/const-EV baselines under date-blocked evaluation. No strategy promotion."
            ),
            "maps_to": "Optional Phase49",
            "justified": True,
        },
    ]

    return {
        "findings": findings,
        "top3_root_causes": ranked,
        "recommendations": recommendations,
        "folds_leakage_ok": folds.get("leakage_ok"),
        "primary_conclusion": (
            "The agent does not work because the current feature/target architecture provides "
            "essentially no predictive information about costed H12 net R; models and calibration "
            "cannot invent signal; the WAIT policy then correctly refuses nearly all actions."
        ),
    }
