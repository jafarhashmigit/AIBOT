"""Decision-time expected-value engine. Class-conditional R from inner data only."""

from __future__ import annotations

import numpy as np

from phase3.constants import OUTCOME_CLASSES, SIDES
from phase3.nplib import col


def class_conditional_mean_r(inner: list[dict]) -> dict:
    mapping: dict[str, dict[str, float]] = {}
    for side in SIDES:
        mapping[side] = {}
        r = col(inner, f"actual_net_r_{side}")
        reason = col(inner, f"actual_exit_reason_{side}", dtype=object)
        for cls in OUTCOME_CLASSES:
            part = r[reason == cls]
            mapping[side][cls] = float(part.mean()) if len(part) else float("nan")
    return mapping


def ev_side(rows: list[dict], mapping: dict, side: str) -> np.ndarray:
    m = mapping[side]
    return (
        col(rows, f"p_tp_rf_{side}") * m["TP"]
        + col(rows, f"p_sl_rf_{side}") * m["SL"]
        + col(rows, f"p_time_rf_{side}") * m["TIME"]
    )


def attach_conservative(rows: list[dict], mapping: dict, mae: dict, k: float) -> list[dict]:
    evs = {side: ev_side(rows, mapping, side) for side in SIDES}
    out = []
    for i, row in enumerate(rows):
        item = dict(row)
        for side in SIDES:
            item[f"ev_{side}"] = float(evs[side][i])
            item[f"ev_mae_{side}"] = float(mae[side])
            item[f"cons_ev_{side}"] = float(evs[side][i] - k * mae[side])
        item["uncertainty_k"] = k
        out.append(item)
    return out


def inner_mae(inner: list[dict], mapping: dict) -> dict[str, float]:
    out = {}
    for side in SIDES:
        pred = ev_side(inner, mapping, side)
        actual = col(inner, f"actual_net_r_{side}")
        out[side] = float(np.mean(np.abs(pred - actual)))
    return out
