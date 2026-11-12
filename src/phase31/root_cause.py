"""Root-cause classification and final verdict synthesis."""

from __future__ import annotations

from typing import Any

from phase31.constants import PRODUCTION_FINAL_ACTION, VALID_VERDICTS


def build_root_cause_matrix(artifacts: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    data = artifacts.get("data_integrity") or {}
    if data.get("internally_valid"):
        findings.append(
            {
                "id": "DATA_INTERNAL_VALIDITY",
                "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
                "severity": "info",
                "evidence": "OHLC/ATR/order/duplicates clean on research slice",
                "affected_phases": ["1", "2", "25-30"],
                "changes_previous_conclusions": False,
            }
        )
    else:
        findings.append(
            {
                "id": "DATA_QUALITY",
                "class": "CONFIRMED_DATA_QUALITY_ISSUE",
                "severity": "high",
                "evidence": data,
                "affected_phases": ["1", "2"],
                "changes_previous_conclusions": True,
            }
        )

    lab = artifacts.get("label_reconstruction") or {}
    if lab.get("reconstruction_agrees"):
        findings.append(
            {
                "id": "LABEL_CONTRACT_OK",
                "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
                "severity": "info",
                "evidence": f"sample mismatches={lab.get('mismatch_count')}",
                "affected_phases": ["2", "14", "25-30"],
                "changes_previous_conclusions": False,
            }
        )
    else:
        findings.append(
            {
                "id": "LABEL_MISMATCH",
                "class": "CONFIRMED_IMPLEMENTATION_DEFECT",
                "severity": "critical",
                "evidence": lab.get("mismatch_categories"),
                "affected_phases": ["2"],
                "changes_previous_conclusions": True,
            }
        )

    exe = artifacts.get("execution_cost_audit") or {}
    if not exe.get("execution_realism_fully_established", True):
        findings.append(
            {
                "id": "NO_HISTORICAL_BIDASK",
                "class": "CONFIRMED_EXECUTION_MODEL_LIMITATION",
                "severity": "medium",
                "evidence": "UNAVAILABLE historical bid/ask; idealized barrier fills",
                "affected_phases": ["2", "14", "18", "25-30"],
                "changes_previous_conclusions": False,
            }
        )
    if exe.get("findings"):
        findings.append(
            {
                "id": "COST_ARITHMETIC",
                "class": "CONFIRMED_IMPLEMENTATION_DEFECT",
                "severity": "high",
                "evidence": exe["findings"],
                "affected_phases": ["2"],
                "changes_previous_conclusions": True,
            }
        )

    stat = artifacts.get("statistical_audit") or {}
    mt = (stat.get("multiple_testing_audit") or {})
    if mt.get("phase30_used_log_n_composite_penalty") and not mt.get("phase30_used_formal_correction"):
        findings.append(
            {
                "id": "MULTIPLE_TESTING_HEURISTIC",
                "class": "CONFIRMED_STATISTICAL_METHOD_ISSUE",
                "severity": "medium",
                "evidence": "Phase30 used log(n) composite penalty, not Holm/BH",
                "affected_phases": ["30"],
                "changes_previous_conclusions": False,
                "note": "Does not overturn negative mean-R results; affects ranking confidence language.",
            }
        )
    findings.append(
        {
            "id": "PERMUTATION_SIGN_RANDOMIZATION",
            "class": "CONFIRMED_STATISTICAL_METHOD_ISSUE",
            "severity": "low",
            "evidence": (stat.get("phase30_permutation_audit") or {}).get("limitation"),
            "affected_phases": ["30"],
            "changes_previous_conclusions": False,
        }
    )

    cost = artifacts.get("cost_sensitivity") or {}
    for sid, block in (cost.get("recomputed") or {}).items():
        if block.get("negative_even_before_approx_cost_addback"):
            findings.append(
                {
                    "id": f"PRECOST_NEGATIVE_{sid}",
                    "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
                    "severity": "high",
                    "evidence": {
                        "approx_pre_cost_mean_r": block.get("approx_pre_cost_mean_r"),
                        "baseline_1x_mean_r": block.get("baseline_1x_mean_r"),
                    },
                    "affected_phases": ["30"],
                    "affected_strategies": [sid],
                    "changes_previous_conclusions": False,
                }
            )

    buy = artifacts.get("buy_sell_diagnostics") or {}
    if (buy.get("n_both_directions_weak") or 0) >= 3:
        findings.append(
            {
                "id": "BOTH_SIDES_WEAK",
                "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
                "severity": "high",
                "evidence": buy.get("summary"),
                "affected_phases": ["25-30"],
                "changes_previous_conclusions": False,
            }
        )

    pred = artifacts.get("prediction_diagnostics") or {}
    if pred.get("ok") and pred.get("pred_r_rf_corr_actual_net_r") is not None:
        corr = pred["pred_r_rf_corr_actual_net_r"]
        if abs(corr) < 0.05:
            findings.append(
                {
                    "id": "WEAK_PREDICTIVE_CORRELATION",
                    "class": "GENUINE_NEGATIVE_STRATEGY_EVIDENCE",
                    "severity": "medium",
                    "evidence": {"pred_r_rf_corr_actual_net_r": corr},
                    "affected_phases": ["2"],
                    "changes_previous_conclusions": False,
                }
            )

    # Biggest root cause selection
    priority = {
        "CONFIRMED_IMPLEMENTATION_DEFECT": 0,
        "CONFIRMED_DATA_QUALITY_ISSUE": 1,
        "CONFIRMED_EXECUTION_MODEL_LIMITATION": 3,
        "CONFIRMED_STATISTICAL_METHOD_ISSUE": 4,
        "GENUINE_NEGATIVE_STRATEGY_EVIDENCE": 2,
        "UNRESOLVED": 5,
    }
    defects = [f for f in findings if f["class"] == "CONFIRMED_IMPLEMENTATION_DEFECT"]
    data_issues = [f for f in findings if f["class"] == "CONFIRMED_DATA_QUALITY_ISSUE"]
    genuine = [f for f in findings if f["class"] == "GENUINE_NEGATIVE_STRATEGY_EVIDENCE" and f["severity"] in {"high", "medium"}]

    if defects and data_issues:
        verdict = "MULTIPLE_ROOT_CAUSES_FOUND"
    elif defects:
        verdict = "CONFIRMED_DEFECT_REQUIRES_RESEARCH_REASSESSMENT"
    elif data_issues:
        verdict = "CONFIRMED_DEFECT_REQUIRES_RESEARCH_REASSESSMENT"
    elif any(f["class"] == "CONFIRMED_STATISTICAL_METHOD_ISSUE" and f["severity"] == "high" for f in findings):
        verdict = "STATISTICAL_METHODOLOGY_REQUIRES_REVISION"
    elif any(f["id"] == "NO_HISTORICAL_BIDASK" for f in findings) and not genuine:
        verdict = "EXECUTION_MODEL_INSUFFICIENTLY_VALIDATED"
    elif genuine and not defects:
        # Execution limitation exists but primary story is negative strategy evidence
        verdict = "NO_CONFIRMED_IMPLEMENTATION_DEFECT"
    else:
        verdict = "INCONCLUSIVE"

    assert verdict in VALID_VERDICTS

    # Biggest confirmed root cause narrative
    if defects:
        biggest = defects[0]
    elif genuine:
        biggest = next((g for g in genuine if g["id"].startswith("PRECOST") or g["id"] == "BOTH_SIDES_WEAK"), genuine[0])
    else:
        biggest = findings[0] if findings else {"id": "NONE", "class": "UNRESOLVED"}

    return {
        "findings": findings,
        "biggest_root_cause": biggest,
        "phase_verdict": verdict,
        "production_final_action": PRODUCTION_FINAL_ACTION,
        "previous_conclusions_materially_invalidated": any(f.get("changes_previous_conclusions") for f in findings),
        "note": "Confirmed execution-model limitations do not by themselves invent a profitable edge.",
    }
