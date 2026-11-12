"""Independent full label/outcome reconstruction (no label_m5 / backtest imports)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase32.constants import (
    BAR_MINUTES,
    EXTRA_COST_PER_SIDE,
    FEATURES_PATH,
    HOLDOUT_NAME,
    HORIZON_BARS,
    LABELED_PATH,
    LABEL_TOL_ABS,
    MIN_SPREAD_POINTS,
    OUTCOMES_PATH,
    POINT_SIZE,
    RAW_M5_PATH,
    RESEARCH_CUTOFF_UTC,
    SL_ATR_MULTIPLE,
    TP_ATR_MULTIPLE,
)
from phase32.independent_features import load_raw_independent


BUY, SELL, WAIT = 1, -1, 0


def _simulate_trade_independent(
    *,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread_usd: np.ndarray,
    time: np.ndarray,
    side: int,
    signal_pos: int,
    atr: float,
    horizon_bars: int = HORIZON_BARS,
) -> dict[str, Any]:
    entry_pos = signal_pos + 1
    last_pos = entry_pos + horizon_bars - 1
    if last_pos >= len(open_):
        raise ValueError("incomplete")
    tp_dist = TP_ATR_MULTIPLE * atr
    sl_dist = SL_ATR_MULTIPLE * atr
    if side == BUY:
        entry_fill = open_[entry_pos] + spread_usd[entry_pos] + EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill + tp_dist, entry_fill - sl_dist
    else:
        entry_fill = open_[entry_pos] - EXTRA_COST_PER_SIDE
        tp_level, sl_level = entry_fill - tp_dist, entry_fill + sl_dist

    exit_fill, reason, exit_pos = None, "TIME", last_pos
    for k in range(entry_pos, last_pos + 1):
        if side == BUY:
            open_px = open_[k] - EXTRA_COST_PER_SIDE
            low_px = low[k] - EXTRA_COST_PER_SIDE
            high_px = high[k] - EXTRA_COST_PER_SIDE
            if k > entry_pos and open_px <= sl_level:
                exit_fill, reason, exit_pos = open_px, "SL", k
            elif low_px <= sl_level:
                exit_fill, reason, exit_pos = sl_level, "SL", k
            elif high_px >= tp_level:
                exit_fill, reason, exit_pos = tp_level, "TP", k
        else:
            ask = spread_usd[k] + EXTRA_COST_PER_SIDE
            open_px = open_[k] + ask
            high_px = high[k] + ask
            low_px = low[k] + ask
            if k > entry_pos and open_px >= sl_level:
                exit_fill, reason, exit_pos = open_px, "SL", k
            elif high_px >= sl_level:
                exit_fill, reason, exit_pos = sl_level, "SL", k
            elif low_px <= tp_level:
                exit_fill, reason, exit_pos = tp_level, "TP", k
        if exit_fill is not None:
            break
    else:
        if side == BUY:
            exit_fill = close[last_pos] - EXTRA_COST_PER_SIDE
        else:
            exit_fill = close[last_pos] + spread_usd[last_pos] + EXTRA_COST_PER_SIDE
        exit_pos = last_pos

    net = exit_fill - entry_fill if side == BUY else entry_fill - exit_fill
    spread_paid = spread_usd[entry_pos] if side == BUY else spread_usd[exit_pos]
    costs = spread_paid + 2 * EXTRA_COST_PER_SIDE
    return {
        "side": "BUY" if side == BUY else "SELL",
        "entry_time": time[entry_pos],
        "exit_time": time[exit_pos],
        "entry_fill": float(entry_fill),
        "exit_fill": float(exit_fill),
        "exit_reason": reason,
        "gross_pnl": float(net + costs),
        "costs": float(costs),
        "net_pnl": float(net),
        "initial_risk": float(sl_dist),
        "net_r": float(net / sl_dist),
        "tp_level": float(tp_level),
        "sl_level": float(sl_level),
    }


def _window_flags(raw_times: pd.Series, positions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_raw = len(raw_times)
    step = pd.Timedelta(minutes=BAR_MINUTES)
    contiguous = (raw_times.diff() == step).to_numpy()
    incomplete = positions + HORIZON_BARS > n_raw - 1
    crosses = np.zeros(len(positions), dtype=bool)
    for offset in range(1, HORIZON_BARS + 1):
        k = np.minimum(positions + offset, n_raw - 1)
        crosses |= ~contiguous[k]
    crosses &= ~incomplete
    return incomplete, crosses


def reconstruct_all_labels() -> dict[str, Any]:
    if HOLDOUT_NAME in str(LABELED_PATH):
        raise RuntimeError("HARD FAILURE: holdout path referenced")
    raw = load_raw_independent()
    # Use stored atr_14 from features file as decision-time ATR (same as original label path).
    feats = pd.read_csv(FEATURES_PATH)
    feats["time"] = pd.to_datetime(feats["time"])
    raw_pos = pd.Series(np.arange(len(raw)), index=raw["time"])
    positions = raw_pos.reindex(feats["time"]).to_numpy(dtype=np.int64)
    if np.isnan(positions).any():
        raise RuntimeError("feature times not in raw")
    positions = positions.astype(np.int64)

    incomplete, crosses = _window_flags(raw["time"], positions)
    excluded = incomplete | crosses

    open_ = raw["open"].to_numpy(dtype=float)
    high = raw["high"].to_numpy(dtype=float)
    low = raw["low"].to_numpy(dtype=float)
    close = raw["close"].to_numpy(dtype=float)
    spread = np.maximum(raw["spread"].to_numpy(dtype=float), MIN_SPREAD_POINTS) * POINT_SIZE
    times = raw["time"].to_numpy()
    atr = feats["atr_14"].to_numpy(dtype=float)

    # Vectorized first-touch for target labels (mirrors label_m5 logic)
    entry = np.minimum(positions + 1, len(raw) - 1)
    long_entry = open_[entry] + spread[entry] + EXTRA_COST_PER_SIDE
    short_entry = open_[entry] - EXTRA_COST_PER_SIDE
    tp = TP_ATR_MULTIPLE * atr
    sl = SL_ATR_MULTIPLE * atr

    def first_touch(flags: list[np.ndarray]) -> np.ndarray:
        hits = np.column_stack(flags)
        return np.where(hits.any(axis=1), hits.argmax(axis=1) + 1, HORIZON_BARS + 1)

    long_tp, long_sl, short_tp, short_sl = [], [], [], []
    for offset in range(1, HORIZON_BARS + 1):
        k = np.minimum(positions + offset, len(raw) - 1)
        long_tp.append((high[k] - EXTRA_COST_PER_SIDE) >= (long_entry + tp))
        long_sl.append((low[k] - EXTRA_COST_PER_SIDE) <= (long_entry - sl))
        short_tp.append((low[k] + spread[k] + EXTRA_COST_PER_SIDE) <= (short_entry - tp))
        short_sl.append((high[k] + spread[k] + EXTRA_COST_PER_SIDE) >= (short_entry + sl))

    ltp, lsl = first_touch(long_tp), first_touch(long_sl)
    stp, ssl = first_touch(short_tp), first_touch(short_sl)
    long_win = (ltp < lsl) & ~excluded
    short_win = (stp < ssl) & ~excluded
    target = np.full(len(positions), WAIT, dtype=np.int64)
    target[long_win] = BUY
    target[short_win] = SELL

    labeled = pd.read_csv(LABELED_PATH)
    labeled["time"] = pd.to_datetime(labeled["time"])
    recon = pd.DataFrame({"time": feats["time"], "target_ind": target, "excluded": excluded})
    joined = labeled.merge(recon, on="time", how="inner")
    # Original labeled excludes incomplete/gap rows entirely
    # Compare only rows present in labeled file
    match = (joined["target"].to_numpy(dtype=np.int64) == joined["target_ind"].to_numpy(dtype=np.int64)).sum()
    mism = int(len(joined) - match)

    # Full side-outcome reconciliation on eligible rows (not excluded)
    outcomes = pd.read_csv(OUTCOMES_PATH)
    outcomes["decision_time"] = pd.to_datetime(outcomes["decision_time"])
    elig = outcomes[outcomes["eligible"] == True].copy()  # noqa: E712

    # Compare only decision times present in the stored outcomes ledger
    # (outcomes cover the research build window; features.csv extends past cutoff).
    feat_times = feats["time"].to_numpy()
    time_to_i = {pd.Timestamp(t): i for i, t in enumerate(feat_times)}
    side_match = 0
    side_mis = 0
    examples = []
    skipped_excluded_in_recon = 0
    for r in elig.itertuples(index=False):
        dt = pd.Timestamp(r.decision_time)
        i = time_to_i.get(dt)
        if i is None:
            side_mis += 1
            if len(examples) < 10:
                examples.append({"time": str(dt), "side": r.side, "issue": "missing_in_features"})
            continue
        if excluded[i]:
            skipped_excluded_in_recon += 1
            side_mis += 1
            if len(examples) < 10:
                examples.append({"time": str(dt), "side": r.side, "issue": "recon_marks_excluded"})
            continue
        side = BUY if r.side == "BUY" else SELL
        tr = _simulate_trade_independent(
            open_=open_,
            high=high,
            low=low,
            close=close,
            spread_usd=spread,
            time=times,
            side=side,
            signal_pos=int(positions[i]),
            atr=float(atr[i]),
        )
        good = (
            str(r.exit_reason) == tr["exit_reason"]
            and abs(float(r.net_r) - tr["net_r"]) <= LABEL_TOL_ABS
            and abs(float(r.entry_fill) - tr["entry_fill"]) <= LABEL_TOL_ABS
        )
        if good:
            side_match += 1
        else:
            side_mis += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "time": str(dt),
                        "side": r.side,
                        "stored_exit": r.exit_reason,
                        "recon_exit": tr["exit_reason"],
                        "stored_net_r": float(r.net_r),
                        "recon_net_r": tr["net_r"],
                    }
                )

    gaps_full = int((raw["time"].diff() > pd.Timedelta(minutes=BAR_MINUTES)).sum())
    cutoff = pd.Timestamp(RESEARCH_CUTOFF_UTC)
    gaps_cut = int((raw.loc[raw["time"] <= cutoff, "time"].diff() > pd.Timedelta(minutes=BAR_MINUTES)).sum())

    return {
        "holdout_opened": False,
        "n_feature_rows": int(len(feats)),
        "n_labeled_stored": int(len(labeled)),
        "n_labeled_compared": int(len(joined)),
        "target_exact_matches": int(match),
        "target_mismatches": mism,
        "target_mismatch_pct": mism / len(joined) if len(joined) else None,
        "eligible_side_outcome_matches": int(side_match),
        "eligible_side_outcome_mismatches": int(side_mis),
        "side_mismatch_pct": side_mis / (side_match + side_mis) if (side_match + side_mis) else None,
        "n_stored_eligible_compared": int(len(elig)),
        "skipped_excluded_disagreement": int(skipped_excluded_in_recon),
        "comparison_scope": "stored_eligible_outcomes_only",
        "representative_mismatches": examples,
        "gaps_gt_5min_full_raw": gaps_full,
        "gaps_gt_5min_le_cutoff": gaps_cut,
        "expected_labeled_rows": 47683,
        "row_count_note": (
            "Labeled file excludes incomplete/gap windows; feature file includes them until labeling drops. "
            f"Stored labeled={len(labeled)}; compared intersection={len(joined)}."
        ),
        "all_targets_match": mism == 0,
        "all_side_outcomes_match": side_mis == 0,
        "reconstruction_agrees": mism == 0 and side_mis == 0,
    }
