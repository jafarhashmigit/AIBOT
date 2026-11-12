"""Existing architecture audit for Phase64.6 readiness engineering."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PERMITTED_MT5_API, PROHIBITED_MT5_API
from phase64_3.constants import APPROVED_FACTORY
from phase64_4.constants import RECIPE_ID as P644
from phase64_5.constants import RECIPE_ID as P645
from phase64_6.constants import RECIPE_ID, canonical_json_sha256


def audit_architecture() -> dict[str, Any]:
    out = {
        "recipe": RECIPE_ID,
        "traced": [
            {
                "component": "phase12.mt5_allowlist",
                "finding": "PERMITTED RO market/account APIs; order/position/history PROHIBITED",
                "phase64_6_action": "Do not modify; document matrix + future review proposal only",
            },
            {
                "component": "phase12.mt5_readonly",
                "finding": "Legacy probe still references XAUUSD symbol string historically",
                "phase64_6_action": "New adapter uses XAUUSDm; Phase12 left immutable",
            },
            {
                "component": "phase64_4.authorization_gate",
                "finding": "All gates default BLOCKED; submission_authorized always False in 64.4",
                "phase64_6_action": "Compose hardened ExecutionGate on top; do not edit 64.4",
            },
            {
                "component": "phase64_5.BrokerEvidenceJournal",
                "finding": "Append-only broker evidence + recon foundation",
                "phase64_6_action": "Keep separate from metadata adapter store",
            },
            {
                "component": APPROVED_FACTORY,
                "finding": "Sole approved paper runtime",
                "phase64_6_action": "Paper readiness ≠ broker authorization",
            },
            {
                "component": "phase57_1 durable journal",
                "finding": "WAL crash patterns for paper lifecycle",
                "phase64_6_action": "Reuse patterns conceptually for intent prep tests",
            },
        ],
        "phase64_4_recipe": P644,
        "phase64_5_recipe": P645,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "symbol_info_permitted": "symbol_info" in PERMITTED_MT5_API,
        "positions_get_prohibited": "positions_get" in PROHIBITED_MT5_API,
        "allowlist_expanded": False,
        "pass": "order_send" in PROHIBITED_MT5_API and "symbol_info" in PERMITTED_MT5_API,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
