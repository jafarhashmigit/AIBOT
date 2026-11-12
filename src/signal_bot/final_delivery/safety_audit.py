"""Repository safety audit — detect bypasses; invariants must hold."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from signal_bot.final_delivery.constants import (
    AUTOMATED_ORDERS,
    BROKER_COLLECTION,
    CHAMPION_STATUS,
    COMMISSION,
    DISCORD_ACTIONABLE,
    EXECUTION_AUTHORIZATION,
    HARD_BLOCK_ACTIONABLE_DISCORD,
    HARD_BLOCK_ORDER_SEND,
    LIVE_TRADING,
    NET_PROFITABILITY,
    ORDER_SEND,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    PROMPT09_VERDICT,
    RISK_POLICY,
    STRATEGY_APPROVAL,
    SWAP,
)
from signal_bot.orchestrator.constants import HARD_BLOCK_ACTIONABLE_DISCORD as ORCH_HARD
from signal_bot.orchestrator.constants import ORDER_SEND as ORCH_ORDER
from signal_bot.orchestrator.delivery import deliver_signal
from signal_bot.orchestrator.gate import effective_operating_mode, evaluate_publication_gate


FORBIDDEN_CALL_PATTERNS = (
    r"\border_send\s*\(",
    r"\bOrderSend\s*\(",
    r"\bmt5\.order_send\b",
)


def _scan_src_for_order_send() -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    src = PROJECT_ROOT / "src"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            # Allow string mentions / constants / comments about prohibition
            if "PROHIBITED" in line or "order_send:" in line or "no order_send" in line.lower():
                continue
            if "\"order_send\"" in line or "'order_send'" in line:
                # API name lists ok
                if "PROHIBITED" in text[max(0, text.find(line) - 200) : text.find(line) + 200]:
                    continue
            for pat in FORBIDDEN_CALL_PATTERNS:
                if re.search(pat, line) and "PROHIBITED" not in line:
                    # Skip tests, scanners, integrity denylist string tables, fakes
                    if "tests" in path.parts or "fake_broker" in path.name:
                        continue
                    if path.name in {"safety_audit.py", "integrity.py", "security.py"}:
                        continue
                    if "prohibited" in line.lower() or "must_not" in line.lower():
                        continue
                    if "needles" in line or "denylist" in line.lower():
                        continue
                    hits.append({"path": str(path.relative_to(PROJECT_ROOT)), "line": str(i), "text": line.strip()[:120]})
    return hits


def run_safety_audit() -> dict[str, Any]:
    invariants = {
        "champion": CHAMPION_STATUS == "NO_MODEL",
        "production_wait": PRODUCTION_FINAL_ACTION == "WAIT",
        "strategy_approval": STRATEGY_APPROVAL == "NOT_APPROVED",
        "live_trading": LIVE_TRADING == "NOT_AUTHORIZED",
        "broker_collection": BROKER_COLLECTION == "READ_ONLY",
        "automated_orders": AUTOMATED_ORDERS == "DISABLED",
        "order_send": ORDER_SEND == "PROHIBITED" and ORCH_ORDER == "PROHIBITED",
        "execution_auth": EXECUTION_AUTHORIZATION == "BLOCKED",
        "risk_policy": RISK_POLICY == "UNAPPROVED",
        "commission": COMMISSION == "UNKNOWN",
        "swap": "CONFLICTED" in SWAP or "UNKNOWN" in SWAP,
        "net_profitability": NET_PROFITABILITY == "NOT_ESTABLISHED",
        "discord_actionable": DISCORD_ACTIONABLE == "DISABLED",
        "prompt09": PROMPT09_VERDICT == "NO_QUALIFIED_STRATEGY",
        "hard_block_actionable": HARD_BLOCK_ACTIONABLE_DISCORD and ORCH_HARD,
        "hard_block_order_send": HARD_BLOCK_ORDER_SEND,
    }

    # Env cannot unlock AUTHORIZED operating mode
    mode_clamp = effective_operating_mode("AUTHORIZED") == "SHADOW"

    # Gate blocks BUY even if caller passes publication_authorization_enabled=True
    fake_buy = {
        "schema_version": "aibot_signal_event_v1",
        "signal_id": "test-buy",
        "decision_id": "d1",
        "strategy_id": "FAKE",
        "strategy_version": "v0",
        "symbol": "XAUUSDm",
        "timeframe": "M5",
        "direction": "BUY",
        "entry_reference": 1.0,
        "entry_type": "MARKET",
        "stop_loss": 0.9,
        "take_profit": 1.2,
        "reward_risk": 2.0,
        "created_utc": "2026-11-12T09:00:00Z",
        "bar_close_utc": "2026-11-12T09:00:00Z",
        "validation_status": "INDEPENDENTLY_VALIDATED",
        "risk_check_status": "APPROVED",
        "data_quality_status": "OK",
        "market_data_provenance": "BROKER_OBSERVED_LIVE_BAR",
        "stale": False,
        "forming_bar": False,
        "authorizes_execution": False,
    }
    # Minimal event — gate may schema-fail; either way must not allow
    g = evaluate_publication_gate(
        fake_buy,
        mode="AUTHORIZED",
        publication_authorization_enabled=True,
    )
    gate_blocks_buy = not g.get("allowed")

    # Delivery hard block even if forced AUTHORIZED + gate_allowed
    d = deliver_signal(
        {**fake_buy, "direction": "BUY", "publication_status": "ALLOWED", "actionable_discord": True},
        mode="AUTHORIZED",
        gate_allowed=True,
        transport=lambda *a, **k: (200, "ok"),
    )
    delivery_hard_blocks = d.get("network_called") is False and d.get("status") in {
        "HARD_BLOCKED_ACTIONABLE",
        "BLOCKED_RECORDED",
        "SHADOW_RECORDED",
    }

    order_hits = _scan_src_for_order_send()

    all_ok = (
        all(invariants.values())
        and mode_clamp
        and gate_blocks_buy
        and delivery_hard_blocks
        and len(order_hits) == 0
    )

    return {
        "invariants": invariants,
        "all_invariants_hold": all(invariants.values()),
        "authorized_mode_clamped_to_shadow": mode_clamp,
        "gate_blocks_buy_despite_flags": gate_blocks_buy,
        "gate_block_reasons_sample": g.get("block_reasons"),
        "delivery_hard_blocks_actionable_network": delivery_hard_blocks,
        "delivery_status": d.get("status"),
        "order_send_call_hits": order_hits[:20],
        "n_order_send_call_hits": len(order_hits),
        "config_flag_bypass_possible": False if (mode_clamp and gate_blocks_buy and delivery_hard_blocks) else True,
        "audit_pass": all_ok,
    }
