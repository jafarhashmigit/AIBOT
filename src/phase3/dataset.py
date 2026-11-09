"""Load Phase 2 OOS predictions and pivot to timestamp-level decision rows."""

from __future__ import annotations

from pathlib import Path

from phase3.constants import (
    DECISION_FEATURE_ALLOWLIST,
    OOS_PATH,
    PHASE2_OOS_SHA256,
    RESEARCH_CUTOFF,
    SIDES,
    VALIDATION_END,
)
from phase3.nplib import parse_time, read_csv_dicts, sha256_file


FLOAT_COLS = (
    "p_tp_prior", "p_sl_prior", "p_time_prior",
    "p_tp_logreg", "p_sl_logreg", "p_time_logreg",
    "p_tp_rf", "p_sl_rf", "p_time_rf",
    "pred_r_const", "pred_r_ridge", "pred_r_rf",
    "actual_net_r", "actual_net_pnl",
)


def load_oos(path: Path = OOS_PATH) -> list[dict]:
    if path.resolve() != OOS_PATH.resolve():
        raise RuntimeError("Phase 3 may only read the approved Phase 2 OOS file")
    digest = sha256_file(path)
    if digest != PHASE2_OOS_SHA256:
        raise RuntimeError(f"Phase 2 OOS file hash changed: {digest} != {PHASE2_OOS_SHA256}. Stopping.")
    rows = read_csv_dicts(path)
    out = []
    for rec in rows:
        item = dict(rec)
        item["decision_time"] = parse_time(rec["decision_time"])
        item["training_period_end"] = parse_time(rec["training_period_end"])
        for col in FLOAT_COLS:
            item[col] = float(rec[col])
        if item["decision_time"].strftime("%Y-%m-%d %H:%M:%S") > VALIDATION_END:
            raise RuntimeError("OOS decision_time exceeds validation end")
        if item["decision_time"].strftime("%Y-%m-%d %H:%M:%S") > RESEARCH_CUTOFF:
            raise RuntimeError("OOS decision_time exceeds research cutoff")
        out.append(item)
    sides = {r["side"] for r in out}
    if sides != set(SIDES):
        raise RuntimeError(f"unexpected sides: {sides}")
    return out


def add_derived(row: dict) -> dict:
    row["pred_r_rf_diff"] = row["pred_r_rf_BUY"] - row["pred_r_rf_SELL"]
    row["p_tp_rf_diff"] = row["p_tp_rf_BUY"] - row["p_tp_rf_SELL"]
    row["p_tp_minus_sl_rf_BUY"] = row["p_tp_rf_BUY"] - row["p_sl_rf_BUY"]
    row["p_tp_minus_sl_rf_SELL"] = row["p_tp_rf_SELL"] - row["p_sl_rf_SELL"]
    missing = [c for c in DECISION_FEATURE_ALLOWLIST if c not in row]
    if missing:
        raise RuntimeError(f"derived frame missing allowlist columns: {missing}")
    return row


def to_wide(long_rows: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for rec in long_rows:
        key = (rec["decision_time"], rec["fold_id"])
        slot = by_key.setdefault(key, {"decision_time": rec["decision_time"], "fold_id": rec["fold_id"]})
        side = rec["side"]
        for k, v in rec.items():
            if k in ("decision_time", "fold_id", "side"):
                continue
            slot[f"{k}_{side}"] = v
    wide = []
    for key in sorted(by_key, key=lambda x: x[0]):
        row = by_key[key]
        if "pred_r_rf_BUY" not in row or "pred_r_rf_SELL" not in row:
            raise RuntimeError(f"timestamp {key} is missing a side")
        wide.append(add_derived(row))
    return wide
