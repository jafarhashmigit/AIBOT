"""Commission evidence investigation — refuse invented schedules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from phase60.constants import PROJECT_ROOT, SRC_DIR, canonical_json_sha256

SEARCH_ROOTS = [
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "configs",
    PROJECT_ROOT / "reports" / "phase46",
    PROJECT_ROOT / "reports" / "phase54",
    PROJECT_ROOT / "reports" / "phase59",
]

# Patterns that look like fee schedules — we only record hits for human audit; never invent
_FEE_HINT = re.compile(
    r"commission\s*[:=]\s*\$?\d|per[\s_-]?lot|round[\s_-]?turn|usd\s*/\s*lot|commission_usd",
    re.I,
)


class CommissionModel:
    """Explicit units; refuses adjusted performance without verified schedule."""

    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        self.status = evidence.get("commission_status", "UNKNOWN")

    def calculate_commission_usd(
        self,
        *,
        lots: float | None = None,
        sides: int | None = None,
        notional_usd: float | None = None,
    ) -> float | None:
        if self.status != "VERIFIED":
            return None
        sched = self.evidence.get("schedule") or {}
        method = sched.get("calculation_method")
        if method == "per_lot_per_side":
            if lots is None or sides is None:
                return None
            return float(sched["usd_per_lot_per_side"]) * float(lots) * int(sides)
        if method == "per_lot_round_turn":
            if lots is None:
                return None
            return float(sched["usd_per_lot_round_turn"]) * float(lots)
        if method == "percent_notional":
            if notional_usd is None:
                return None
            return float(sched["percent"]) / 100.0 * float(notional_usd)
        return None

    def commission_adjusted_net_r(self, *, gross_r: float, risk_amount: float, **kwargs: Any) -> float | None:
        if self.status != "VERIFIED":
            return None
        if risk_amount is None or float(risk_amount) == 0:
            return None
        c = self.calculate_commission_usd(**kwargs)
        if c is None:
            return None
        return float(gross_r) - (float(c) / float(risk_amount))


def investigate_commission() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    # Known project documentation statements (read-only)
    known_docs = [
        PROJECT_ROOT / "docs" / "agent" / "PHASE_38_DATA_ARCHITECTURE.md",
        PROJECT_ROOT / "docs" / "agent" / "PHASE_46_COSTED_EV_FOUNDATION.md",
        PROJECT_ROOT / "docs" / "agent" / "PHASE_59_EXECUTION_ECONOMICS.md",
    ]
    for p in known_docs:
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            hits.append(
                {
                    "path": str(p),
                    "kind": "project_doc",
                    "mentions_demo_not_live": "MetaQuotes-Demo" in text or "demo" in text.lower(),
                    "contains_numeric_fee_schedule": bool(_FEE_HINT.search(text)),
                    "excerpt_note": "Demo/source caveats; not a verified live broker commission schedule",
                }
            )

    # Scan limited config files for explicit schedules
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".md", ".json", ".yml", ".yaml", ".toml", ".ini", ".txt", ".env.example"}:
                continue
            if p.stat().st_size > 2_000_000:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if _FEE_HINT.search(text):
                # Skip phase59 costs that explicitly set UNKNOWN
                hits.append(
                    {
                        "path": str(p.relative_to(PROJECT_ROOT) if p.is_relative_to(PROJECT_ROOT) else p),
                        "kind": "fee_hint_match",
                        "contains_numeric_fee_schedule": True,
                    }
                )
                if len(hits) > 40:
                    break
        if len(hits) > 40:
            break

    verified_schedule = None  # none found applicable to target venue
    status = "UNKNOWN"
    out = {
        "commission_status": status,
        "target_venue_established": False,
        "target_account_established": False,
        "instrument": "XAUUSD",
        "schedule": verified_schedule,
        "evidence_hits": hits[:40],
        "accepted_evidence": [],
        "rejected_transfers": [
            "Do not transfer another broker's fee schedule to MetaQuotes-Demo or unknown live account",
            "Do not assume zero commission when schedule missing",
        ],
        "model_behavior": {
            "refuses_adjusted_performance_when_unknown": True,
            "units_when_verified": ["usd_per_lot_per_side", "usd_per_lot_round_turn", "percent_notional"],
        },
        "provenance_note": "Server historically labeled MetaQuotes-Demo in Phase38 docs — not live broker execution truth",
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out
