"""Minimal Phase12 allowlist approval for read-only broker evidence APIs."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import (
    PERMITTED_MT5_API,
    PHASE64_8_APPROVED_READ_ONLY,
    PROHIBITED_MT5_API,
)
from phase64_8.constants import APPROVAL_VERSION, API_TIMEOUT_SEC, canonical_json_sha256


def _row(
    api: str,
    *,
    decision: str,
    read_only: bool,
    returned_fields: list[str],
    why_needed: str,
    existing_alternative: str,
    invocation_scope: str,
    retention: str,
    failure_behavior: str,
    timeout_behavior: str,
    sensitive_handling: str,
    adversarial_tests: list[str],
    rationale: str,
) -> dict[str, Any]:
    in_permitted = api in PERMITTED_MT5_API
    in_prohibited = api in PROHIBITED_MT5_API
    effective = (
        "PERMITTED"
        if in_permitted
        else ("PROHIBITED" if in_prohibited else "UNLISTED")
    )
    return {
        "api": api,
        "decision": decision,
        "strictly_read_only": read_only,
        "returned_fields": returned_fields,
        "why_aibot_needs_it": why_needed,
        "existing_api_alternative": existing_alternative,
        "permitted_invocation_scope": invocation_scope,
        "data_retention": retention,
        "failure_behavior": failure_behavior,
        "timeout_behavior": timeout_behavior,
        "sensitive_field_handling": sensitive_handling,
        "adversarial_tests": adversarial_tests,
        "rationale": rationale,
        "phase12_effective_status": effective,
        "decision_matches_allowlist": (
            (decision == "APPROVED_READ_ONLY" and in_permitted and not in_prohibited)
            or (decision == "REJECTED" and in_prohibited and not in_permitted)
            or (decision == "PROPOSAL_ONLY" and in_prohibited)
        ),
    }


def build_approval_matrix() -> dict[str, Any]:
    rows = [
        _row(
            "positions_get",
            decision="APPROVED_READ_ONLY",
            read_only=True,
            returned_fields=[
                "ticket",
                "symbol",
                "type",
                "volume",
                "price_open",
                "price_current",
                "sl",
                "tp",
                "profit",
                "swap",
                "magic",
                "comment",
                "time",
                "identifier",
            ],
            why_needed="Observe open exposure for crash/partial-fill reconciliation without mutation",
            existing_alternative="CSV Toolbox export (Phase63/64.5) — too slow for realtime recon",
            invocation_scope=(
                "phase64_8 evidence collector only; optional symbol filter; "
                "never from execution/auth modules; bounded poll interval"
            ),
            retention="Append-only BrokerEvidenceJournal; stable_key=position:{ticket}; no credentials",
            failure_behavior="None/empty → OBSERVED empty set; disconnect → fail closed collection cycle",
            timeout_behavior=f"Fail closed after {API_TIMEOUT_SEC}s; no retry storm; emit incident",
            sensitive_handling="Magic/comment retained only when non-secret; never store passwords",
            adversarial_tests=[
                "duplicate_position_response",
                "unexpected_symbol",
                "unexpected_account_server",
                "malformed_response",
                "disconnect",
            ],
            rationale="Necessary for open exposure evidence; no Close/order_send in same path",
        ),
        _row(
            "orders_get",
            decision="APPROVED_READ_ONLY",
            read_only=True,
            returned_fields=[
                "ticket",
                "symbol",
                "type",
                "volume_initial",
                "volume_current",
                "price_open",
                "sl",
                "tp",
                "state",
                "time_setup",
                "time_done",
                "magic",
                "comment",
            ],
            why_needed="Observe pending/open orders for intent↔broker order linkage",
            existing_alternative="Manual History→Orders CSV — insufficient for timeout recon",
            invocation_scope="phase64_8 collector only; filter by symbol/magic when available",
            retention="Append-only journal; stable_key=order:{ticket}",
            failure_behavior="Empty → empty open-order evidence; never fabricate orders",
            timeout_behavior=f"Fail closed after {API_TIMEOUT_SEC}s",
            sensitive_handling="Comment/magic only; no credentials",
            adversarial_tests=[
                "duplicate_order_response",
                "missing_order_for_deal",
                "malformed_response",
                "api_timeout",
            ],
            rationale="Required for order lifecycle evidence; cancellation APIs remain prohibited",
        ),
        _row(
            "history_deals_get",
            decision="APPROVED_READ_ONLY",
            read_only=True,
            returned_fields=[
                "ticket",
                "order",
                "position_id",
                "symbol",
                "type",
                "entry",
                "volume",
                "price",
                "commission",
                "swap",
                "profit",
                "fee",
                "time",
                "time_msc",
                "magic",
                "comment",
            ],
            why_needed="Native deal evidence for commission/swap/fill recon vs CSV-only path",
            existing_alternative="Phase64.5 CSV import — offline OK, not live RO collector",
            invocation_scope=(
                "phase64_8 collector; bounded lookback window; "
                "balance/credit classified separately from trade fills"
            ),
            retention="Append-only; stable_key=deal:{ticket}; never merge into paper/hist stores",
            failure_behavior="Empty range → empty history evidence; never invent deals from paper",
            timeout_behavior=f"Bounded window; fail closed on timeout; no unbounded pull",
            sensitive_handling="Sanitize login; strip secrets from comments if detected",
            adversarial_tests=[
                "duplicate_deal_response",
                "same_deal_multi_window",
                "out_of_order_deal",
                "partial_fill_sequence",
                "unknown_commission",
                "unknown_swap",
                "conflicting_price",
                "conflicting_volume",
            ],
            rationale="Highest-value RO evidence for economics; not an entire history_* family approval",
        ),
        _row(
            "history_orders_get",
            decision="APPROVED_READ_ONLY",
            read_only=True,
            returned_fields=[
                "ticket",
                "symbol",
                "type",
                "state",
                "volume_initial",
                "volume_current",
                "price_open",
                "sl",
                "tp",
                "time_setup",
                "time_done",
                "reason",
                "magic",
                "comment",
            ],
            why_needed="Link historical orders to deals for rejected/cancelled/partial paths",
            existing_alternative="CSV History→Orders — offline only",
            invocation_scope="phase64_8 collector; same bounded window as deals",
            retention="Append-only; stable_key=hist_order:{ticket}",
            failure_behavior="Empty → empty hist-order evidence",
            timeout_behavior=f"Fail closed after {API_TIMEOUT_SEC}s",
            sensitive_handling="Same as orders_get",
            adversarial_tests=[
                "missing_deal_for_order",
                "duplicate_order_response",
                "replay_complete_window",
            ],
            rationale="Complements history_deals_get; approved individually not as history_* family",
        ),
        _row(
            "positions_total",
            decision="REJECTED",
            read_only=True,
            returned_fields=["count"],
            why_needed="Not needed — positions_get returns the set",
            existing_alternative="positions_get",
            invocation_scope="N/A — remains PROHIBITED",
            retention="N/A",
            failure_behavior="N/A",
            timeout_behavior="N/A",
            sensitive_handling="N/A",
            adversarial_tests=["attempted_call_must_fail_allowlist"],
            rationale="Redundant with positions_get; avoid expanding surface",
        ),
        _row(
            "orders_total",
            decision="REJECTED",
            read_only=True,
            returned_fields=["count"],
            why_needed="Not needed — orders_get returns the set",
            existing_alternative="orders_get",
            invocation_scope="N/A — remains PROHIBITED",
            retention="N/A",
            failure_behavior="N/A",
            timeout_behavior="N/A",
            sensitive_handling="N/A",
            adversarial_tests=["attempted_call_must_fail_allowlist"],
            rationale="Redundant with orders_get",
        ),
    ]

    approved = [r for r in rows if r["decision"] == "APPROVED_READ_ONLY"]
    rejected = [r for r in rows if r["decision"] == "REJECTED"]
    proposal_only = [r for r in rows if r["decision"] == "PROPOSAL_ONLY"]

    allowlist_diff = {
        "added_to_permitted": sorted(PHASE64_8_APPROVED_READ_ONLY),
        "removed_from_prohibited": sorted(PHASE64_8_APPROVED_READ_ONLY),
        "still_prohibited_mutation": sorted(
            a for a in ("order_send", "buy", "sell", "Close", "order_check", "symbol_select") if a in PROHIBITED_MT5_API
        ),
        "still_prohibited_totals": sorted(
            a for a in ("positions_total", "orders_total") if a in PROHIBITED_MT5_API
        ),
    }

    out = {
        "approval_version": APPROVAL_VERSION,
        "phase": "64.8",
        "rows": rows,
        "summary": {
            "APPROVED_READ_ONLY": [r["api"] for r in approved],
            "REJECTED": [r["api"] for r in rejected],
            "PROPOSAL_ONLY": [r["api"] for r in proposal_only],
        },
        "allowlist_diff": allowlist_diff,
        "order_send": "PROHIBITED",
        "all_decisions_consistent": all(r["decision_matches_allowlist"] for r in rows),
        "pass": all(r["decision_matches_allowlist"] for r in rows)
        and "order_send" in PROHIBITED_MT5_API
        and PHASE64_8_APPROVED_READ_ONLY <= PERMITTED_MT5_API,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
