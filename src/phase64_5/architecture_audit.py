"""Architecture audit — reuse Phase62–64.4; no duplicate lifecycle."""

from __future__ import annotations

from typing import Any

from phase12.mt5_allowlist import PROHIBITED_MT5_API
from phase63.constants import EXPORTS_DIR as P63_EXPORTS
from phase64_3.constants import APPROVED_FACTORY
from phase64_4.constants import RECIPE_ID as P644_RECIPE, SCHEMA_VERSION as P644_SCHEMA
from phase64_5.constants import RECIPE_ID, canonical_json_sha256


def audit_architecture() -> dict[str, Any]:
    out = {
        "recipe": RECIPE_ID,
        "read_only": True,
        "reuses": [
            {
                "component": "phase64_3.approved_runtime",
                "role": "Paper decision/intent authority — not modified; linkage reads intents when provided",
            },
            {
                "component": "phase64_2 HardenedIntentJournal patterns",
                "role": "Intent identity; Phase64.5 does not fork intent journal",
            },
            {
                "component": "phase57_1 WAL recovery pattern",
                "role": "Journal WAL commit pattern reused conceptually in BrokerEvidenceJournal",
            },
            {
                "component": "phase64_4 schemas linkage_chain / make_fill_id",
                "role": "Imported for verified link fill_id when execution_request_id known",
            },
            {
                "component": "phase62/63 CSV header candidates + export dir",
                "role": f"Discovery includes {P63_EXPORTS}; header maps aligned, journal is Phase64.5-owned",
            },
            {
                "component": "phase64_4 authorization_gate",
                "role": "Submission remains blocked; this phase never calls order_send",
            },
        ],
        "new_components": [
            "BrokerEvidenceJournal",
            "XLSX Trade History inspector/importer",
            "Conservative linkage + reconciliation engine",
            "Broker-evidence cost ledger",
        ],
        "duplicate_lifecycle_avoided": True,
        "stores_remain_separate": True,
        "phase64_4_schema": P644_SCHEMA,
        "phase64_4_recipe": P644_RECIPE,
        "approved_paper_factory": APPROVED_FACTORY,
        "order_send_prohibited": "order_send" in PROHIBITED_MT5_API,
        "pass": "order_send" in PROHIBITED_MT5_API and APPROVED_FACTORY.endswith("make_approved_paper_engine"),
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
