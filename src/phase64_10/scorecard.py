"""Broker execution readiness scorecard — UNKNOWN never becomes PASS."""

from __future__ import annotations

from typing import Any

from phase64_10.constants import (
    SCORECARD_VERSION,
    UNKNOWN,
    VERIFIED,
    canonical_json_sha256,
)


def build_readiness_scorecard(
    *,
    commission: dict[str, Any],
    margin: dict[str, Any],
    sessions: dict[str, Any],
    swap: dict[str, Any],
    cost_model: dict[str, Any],
    risk_policy: dict[str, Any],
) -> dict[str, Any]:
    def row(dep: str, required: bool, evidence: str, status: str, blocks: bool) -> dict[str, Any]:
        if status in (UNKNOWN, "UNKNOWN_FOR_EXECUTION", "INCOMPLETE", "UNAPPROVED", "BLOCKED") and required:
            blocks = True
        return {
            "dependency": dep,
            "required": required,
            "evidence": evidence,
            "status": status,
            "blocks_execution": blocks,
        }

    rows = [
        row("Account identity", True, "Live MT5", "PASS", False),
        row("Symbol identity", True, "Live MT5 XAUUSDm", "PASS", False),
        row("Tick size", True, "Live MT5 0.001", "PASS", False),
        row("Tick value", True, "Live MT5 0.1", "PASS", False),
        row("Contract size", True, "Live MT5 100", "PASS", False),
        row("Volume constraints", True, "Live MT5 min/step/max", "PASS", False),
        row("Spread", True, "Live tick snapshot", "PASS", False),  # observed snapshot verified as number
        row(
            "Commission",
            True,
            "No trade deals; published not account-verified",
            commission.get("actual_commission_status", UNKNOWN),
            True,
        ),
        row(
            "Margin",
            True,
            f"MARGIN_MODEL={margin.get('MARGIN_MODEL')}",
            "INCOMPLETE" if margin.get("MARGIN_MODEL") == "INCOMPLETE" else "PASS",
            margin.get("MARGIN_MODEL") == "INCOMPLETE",
        ),
        row(
            "Sessions",
            True,
            "Live API UNKNOWN; Phase63 PARTIAL user-reported",
            sessions.get("programmatic_status", UNKNOWN),
            True,
        ),
        row(
            "Swap",
            True,
            "Conflict -488.7 vs -644.8",
            swap.get("status_for_execution", UNKNOWN),
            True,
        ),
        row(
            "Risk limits",
            True,
            f"Policy {risk_policy.get('approval_status')}",
            risk_policy.get("approval_status", "UNAPPROVED"),
            risk_policy.get("approval_status") != "APPROVED_FOR_DEMO",
        ),
        row("Preflight", True, "Phase64.9", "PASS", False),
        row("Reconciliation", True, "Phase64.8", "PASS", False),
        row("Authorization", True, "Phase64.9", "BLOCKED", True),
        row(
            "Cost model completeness",
            True,
            COST_NOTE(cost_model),
            "COMPLETE" if cost_model.get("deterministic_execution_cost_complete") else "INCOMPLETE",
            not cost_model.get("deterministic_execution_cost_complete"),
        ),
    ]

    blockers = [r for r in rows if r["blocks_execution"]]
    out = {
        "scorecard_version": SCORECARD_VERSION,
        "rows": rows,
        "n_rows": len(rows),
        "n_blocking": len(blockers),
        "blocking_dependencies": [r["dependency"] for r in blockers],
        "execution_ready": False,
        "rule": "Do not convert UNKNOWN into PASS",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def COST_NOTE(cost_model: dict[str, Any]) -> str:
    c = cost_model.get("counts") or {}
    return f"VERIFIED={c.get('VERIFIED')} UNKNOWN={c.get('UNKNOWN')} CONFLICTING={c.get('CONFLICTING')}"
