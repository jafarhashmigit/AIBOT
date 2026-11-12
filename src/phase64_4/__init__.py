"""Phase 64.4 — Broker demo execution safety design & authorization gate (DESIGN-ONLY)."""

from phase64_4.authorization_gate import evaluate_authorization, attempt_unauthorized_submit
from phase64_4.constants import RECIPE_ID

__all__ = ["RECIPE_ID", "evaluate_authorization", "attempt_unauthorized_submit"]
