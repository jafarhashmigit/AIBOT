"""Broker-independent execution evidence interface + Exness adapter (no live orders)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase61.constants import EVIDENCE_STORE, canonical_json_sha256

CATEGORIES = (
    "HISTORICAL_QUOTE_PROXY",
    "SIMULATED_PAPER",
    "EXNESS_DEMO_EXECUTION",
    "EXNESS_LIVE_EXECUTION",
)


def evidence_schema() -> dict[str, Any]:
    fields = [
        "decision_id",
        "strategy_or_policy_id",
        "instrument",
        "symbol",
        "side",
        "intended_entry_price",
        "decision_timestamp_utc",
        "quote_timestamp_utc",
        "bid_at_decision",
        "ask_at_decision",
        "intended_volume_lots",
        "simulated_submission_timestamp_utc",
        "first_executable_quote_after_decision",
        "simulated_fill_price",
        "actual_broker_order_id",
        "actual_broker_deal_id",
        "actual_broker_fill_price",
        "actual_broker_fill_timestamp_utc",
        "actual_commission",
        "exit_decision",
        "exit_fill",
        "evidence_category",
        "data_quality",
        "source_provenance",
    ]
    out = {
        "schema_version": "phase61_execution_evidence_v1",
        "required_core": [
            "decision_id",
            "side",
            "evidence_category",
            "source_provenance",
        ],
        "fields": fields,
        "categories": list(CATEGORIES),
        "category_rules": {
            "HISTORICAL_QUOTE_PROXY": "Not proof of broker fill",
            "SIMULATED_PAPER": "Internal paper path — not Exness deal",
            "EXNESS_DEMO_EXECUTION": "Requires genuine demo order/deal records",
            "EXNESS_LIVE_EXECUTION": "Requires genuine live records; live trading NOT authorized in Phase61",
        },
        "never_cross_prove": True,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


class ExecutionEvidenceCollector:
    """Append-only JSONL store; never fabricates broker IDs or fills."""

    def __init__(self, root: Path | None = None):
        self.root = root or EVIDENCE_STORE
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "records.jsonl"

    def record(self, payload: dict[str, Any]) -> dict[str, Any]:
        cat = payload.get("evidence_category")
        if cat not in CATEGORIES:
            raise ValueError(f"invalid_evidence_category:{cat}")
        # Refuse fabricating actual broker fields for proxy/paper
        if cat in ("HISTORICAL_QUOTE_PROXY", "SIMULATED_PAPER"):
            for k in (
                "actual_broker_order_id",
                "actual_broker_deal_id",
                "actual_broker_fill_price",
                "actual_broker_fill_timestamp_utc",
                "actual_commission",
            ):
                if payload.get(k) is not None:
                    raise ValueError(f"proxy_or_paper_cannot_set_{k}")
        if cat == "EXNESS_LIVE_EXECUTION":
            raise ValueError("live_execution_records_not_authorized_in_phase61")
        row = {
            **payload,
            "record_id": payload.get("record_id") or uuid.uuid4().hex,
            "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if not row.get("decision_id"):
            raise ValueError("decision_id_required")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        return row

    def all(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows


class ExnessEvidenceAdapter:
    """Exness-specific adapter — demo collection capability evaluation only."""

    def __init__(self, collector: ExecutionEvidenceCollector | None = None):
        self.collector = collector or ExecutionEvidenceCollector()

    def capability(self) -> dict[str, Any]:
        # Phase61: no live MT5; evaluate whether demo deal history integration exists
        mt5_deal_history_module = False
        # Search for existing deal-history helpers without connecting
        from phase61.constants import PROJECT_ROOT

        hits = []
        for pat in ("**/history_deals*", "**/deal_history*", "**/orders_history*"):
            hits.extend([str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.glob(pat)][:5])
        out = {
            "adapter": "ExnessEvidenceAdapter",
            "live_mt5_connection": False,
            "live_order_submission": False,
            "demo_deal_history_integration_present": mt5_deal_history_module or bool(hits),
            "integration_hits": hits,
            "can_collect_actual_demo_fills_without_live_orders": False,
            "missing_integration": [
                "No authorized Exness demo MT5 deal-history collector wired in Phase61",
                "Would require read-only history API + verified demo account login (not performed)",
            ],
            "interfaces_built": True,
            "evidence_store_path": str(self.collector.path),
            "categories_supported": list(CATEGORIES),
            "exness_live_blocked": True,
        }
        out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
        return out

    def record_simulated_paper(self, **fields: Any) -> dict[str, Any]:
        return self.collector.record({**fields, "evidence_category": "SIMULATED_PAPER"})

    def record_quote_proxy(self, **fields: Any) -> dict[str, Any]:
        return self.collector.record({**fields, "evidence_category": "HISTORICAL_QUOTE_PROXY"})
