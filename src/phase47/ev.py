"""Expected-value arithmetic — shared contract for primary and independent paths."""

from __future__ import annotations


def expected_net_r(p_positive: float, e_pos: float, e_neg: float) -> float:
    """EV = P(pos)*E[R|pos] + P(neg)*E[R|neg]."""
    p = float(p_positive)
    return p * float(e_pos) + (1.0 - p) * float(e_neg)


def assert_ev_identity(p: float, e_pos: float, e_neg: float, ev: float, tol: float = 1e-9) -> bool:
    return abs(expected_net_r(p, e_pos, e_neg) - float(ev)) <= tol
