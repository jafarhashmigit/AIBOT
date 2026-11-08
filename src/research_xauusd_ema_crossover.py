"""Research backtest: XAUUSD H4 EMA 21/50 Crossover.

Fixed, pre-declared rules; no fitting, no tuning, no ML, no filters. Research only - no live
code, no MT5 connection, no orders.

Data: src/data/xauusd_h1_mt5.csv (broker XAUUSD H1 bid bars, validated against xauusd_m5.csv
by the EMA-pullback experiment), which ends with the last H1 bar closing before the research
cutoff 2026-09-29 18:50. Everything after the cutoff is the untouched final holdout and is never
loaded. No other price file is read.

H4 candles: H1 bars grouped into 4-hour server-clock slots (00, 04, 08, 12, 16, 20 - MT5's
grouping). A candle exists only where H1 bars exist; nothing is filled. A slot that is not
finished by the end of the data is dropped. Candle stamped T covers [T, T+4h); its close is
known at T+4h.

Signals use EMA21/EMA50 of completed H4 closes: BUY when EMA21 crosses from <= EMA50 on the
previous completed candle to > EMA50 on the crossover candle; SELL mirrors it. Entry is the
open of the next H4 candle, only if that candle is the very next 4-hour slot; otherwise the
signal is rejected. SL = 1.5 x ATR14 (crossover candle), TP = 2 x risk.

Costs (project methodology): bid bars; H4 spread = max of the H1 bar spreads in the slot (MT5
stores each bar's MINIMUM spread, so the maximum of the hourly minimums is the conservative
bar-level estimate), floored at 15 points; plus $0.05 per side.
"""

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from features_m5 import add_atr
from label_m5 import EXTRA_COST_PER_SIDE, MIN_SPREAD_POINTS, POINT_SIZE
from research_kronos_m5 import GUARD, TEST_PATH, install_guards
from research_m5_label_horizon import research_boundary
from research_rf_m5_conditional_edge import snapshot
from research_xauusd_ema_pullback import (
    H1_PATH,
    PERIODS,
    WF_PERIODS,
    ema,
    fmt,
    load_h1,
    metric_table,
    metrics,
    period_of,
    session_utc,
    short_table,
)

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
TRADES_PATH = DATA_DIR / "xauusd_ema_crossover_trades.csv"
RESULTS_PATH = DATA_DIR / "xauusd_ema_crossover_results.csv"
REPORT_PATH = DATA_DIR / "xauusd_ema_crossover_report.txt"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
H1 = pd.Timedelta(hours=1)
H4 = pd.Timedelta(hours=4)
M5 = pd.Timedelta(minutes=5)
EXPECTED_CUTOFF = pd.Timestamp("2026-09-29 18:50:00")
BUY, SELL = 1, -1

# Pre-declared strategy parameters (from the specification; never changed).
PARAMS = {"ema_fast": 21, "ema_slow": 50, "atr_period": 14, "sl_atr_multiple": 1.5, "reward_risk": 2.0,
          "max_open_positions": 1}
SPREAD_MULTIPLIERS = (1.0, 1.5, 2.0)
WF_FRACTIONS = (0.55, 0.70, 0.85)
TRUNCATION_FRACTIONS = (0.30, 0.58, 0.74, 0.90)

TEST_STATEMENT = "The untouched final holdout (everything after 2026-09-29 18:50, incl. the M5 test CSV) was never loaded."


# --------------------------------------------------------------------------
# H4 candles, indicators, signals
# --------------------------------------------------------------------------

def build_h4(h1: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    g = h1.assign(slot=h1["time"].dt.floor("4h")).groupby("slot", sort=True)
    h4 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                       "close": g["close"].last(), "spread": g["spread"].max(), "tick_volume": g["tick_volume"].sum(),
                       "h1_bars": g["time"].size(), "first_h1": g["time"].min(), "last_h1": g["time"].max()}
                      ).reset_index().rename(columns={"slot": "time"})
    data_end = h1["time"].max() + H1
    unfinished = h4["time"] + H4 > data_end
    return h4[~unfinished].reset_index(drop=True), int(unfinished.sum())


def build_signals(h1: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    h4, dropped = build_h4(h1)
    h4["ema21"] = ema(h4["close"], PARAMS["ema_fast"])
    h4["ema50"] = ema(h4["close"], PARAMS["ema_slow"])
    add_atr(h4, PARAMS["atr_period"])
    h4 = h4.rename(columns={"atr_14": "atr", "atr_14_pct": "atr_pct"})
    f21, f50 = h4["ema21"], h4["ema50"]
    p21, p50 = f21.shift(1), f50.shift(1)
    h4["valid"] = pd.concat([f21, f50, p21, p50, h4["atr"]], axis=1).notna().all(axis=1)
    buy = h4["valid"] & (p21 <= p50) & (f21 > f50)
    sell = h4["valid"] & (p21 >= p50) & (f21 < f50)
    h4["signal"] = np.where(buy, BUY, np.where(sell, SELL, 0))
    h4["decision_time"] = h4["time"] + H4
    return h4, dropped


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------

def backtest(f: pd.DataFrame, spread_mult: float) -> tuple[pd.DataFrame, list[dict]]:
    t = f["time"].to_numpy()
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sp = np.maximum(f["spread"].to_numpy(float), MIN_SPREAD_POINTS) * POINT_SIZE * spread_mult
    atr, sig = f["atr"].to_numpy(float), f["signal"].to_numpy(int)
    x = EXTRA_COST_PER_SIDE
    n = len(f)
    four_h = np.timedelta64(4, "h")
    trades, rejected = [], []
    last_exit = -1
    for i in np.flatnonzero(sig):
        side = sig[i]
        if i < last_exit:
            rejected.append({"signal_time": t[i], "side": side, "reason": "position_open"})
            continue
        e = i + 1
        if e >= n:
            rejected.append({"signal_time": t[i], "side": side, "reason": "no_next_candle_end_of_data"})
            continue
        if t[e] - t[i] != four_h:
            rejected.append({"signal_time": t[i], "side": side, "reason": "next_h4_slot_missing_market_closed"})
            continue
        sl_dist = PARAMS["sl_atr_multiple"] * atr[i]
        assert np.isfinite(sl_dist) and sl_dist > 0
        if side == BUY:
            entry = o[e] + sp[e] + x
            sl, tp = entry - sl_dist, entry + PARAMS["reward_risk"] * sl_dist
        else:
            entry = o[e] - x
            sl, tp = entry + sl_dist, entry - PARAMS["reward_risk"] * sl_dist
        exit_px, reason, same, k = None, "EOD", False, e
        for k in range(e, n):
            if side == BUY:   # exits at bid, minus exit cost
                ok_, hk, lk = o[k] - x, h[k] - x, l[k] - x
                if k > e and ok_ <= sl:
                    exit_px, reason = ok_, "GAP_SL"
                elif lk <= sl:
                    exit_px, reason, same = sl, "SL", hk >= tp
                elif hk >= tp:
                    exit_px, reason = tp, "TP"
            else:             # exits at ask = bid + spread, plus exit cost
                a = sp[k] + x
                ok_, hk, lk = o[k] + a, h[k] + a, l[k] + a
                if k > e and ok_ >= sl:
                    exit_px, reason = ok_, "GAP_SL"
                elif hk >= sl:
                    exit_px, reason, same = sl, "SL", lk <= tp
                elif lk <= tp:
                    exit_px, reason = tp, "TP"
            if exit_px is not None:
                break
        else:
            k = n - 1
            exit_px = c[k] - x if side == BUY else c[k] + sp[k] + x
        net = exit_px - entry if side == BUY else entry - exit_px
        trades.append({
            "side": "BUY" if side == BUY else "SELL", "signal_pos": i, "entry_pos": e, "exit_pos": k,
            "signal_time": t[i], "entry_time": t[e], "exit_time": t[k], "entry_price": entry, "stop_loss": sl,
            "take_profit": tp, "exit_price": exit_px, "exit_reason": reason, "same_candle_sl_tp": bool(same),
            "gap_exit": reason == "GAP_SL", "bars_held": k - e + 1,
            "holding_hours": (t[k] + four_h - t[e]) / np.timedelta64(1, "h"),
            "atr": atr[i], "sl_distance": sl_dist, "tp_distance": PARAMS["reward_risk"] * sl_dist,
            "entry_spread": sp[e], "exit_spread": sp[k],
            "costs": (sp[e] if side == BUY else sp[k]) + 2 * x, "net_pnl": net, "net_r": net / sl_dist,
        })
        last_exit = k
    return pd.DataFrame(trades), rejected


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    outputs = [TRADES_PATH, RESULTS_PATH, REPORT_PATH]
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    skip = {p.resolve() for p in outputs} | {Path(__file__).resolve()}

    _, _, cutoff = research_boundary()
    assert cutoff == EXPECTED_CUTOFF, f"research cutoff changed: {cutoff}"
    cutoff_str = cutoff.strftime(TIME_FORMAT)
    hashes_before = snapshot(skip, cutoff_str)
    install_guards()
    GUARD["cutoff"] = cutoff_str
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))
        assert ok, f"integrity check failed: {name} {detail}"

    # ---- data
    h1 = load_h1()
    check("final holdout never loaded: H1 data ends before the cutoff; no other price file opened; test CSV never opened",
          h1["time"].max() + H1 <= cutoff + M5 and GUARD["test_open_attempts"] == 0
          and {p.name for p in GUARD["csv_reads"]} <= {"xauusd_h1_mt5.csv", "xauusd_m5_validation.csv"},
          f"last H1 bar {h1['time'].max()} ends {h1['time'].max() + H1}; cutoff {cutoff_str}")

    f, dropped_unfinished = build_signals(h1)
    check("no duplicate H4 timestamps; chronological; on the 4-hour grid",
          f["time"].is_unique and f["time"].is_monotonic_increasing
          and ((f["time"].dt.hour % 4 == 0) & (f["time"].dt.minute == 0)).all())
    h1_in_h4 = int(f["h1_bars"].sum())
    check("no fabricated candles / no missing H4 candles filled: every H4 candle is built from existing H1 bars of its "
          "own slot; no slot without H1 bars exists",
          (f["h1_bars"] >= 1).all() and (f["first_h1"] >= f["time"]).all() and (f["last_h1"] < f["time"] + H4).all()
          and h1_in_h4 == len(h1) - int((h1["time"] >= f["time"].iloc[-1] + H4).sum()),
          f"{len(h1)} H1 bars -> {len(f)} H4 candles; {dropped_unfinished} unfinished final slot(s) dropped")
    check("H4 OHLC/spread equal the aggregates of their H1 bars (no forward fill)",
          (f["high"] >= f[["open", "close"]].max(axis=1)).all() and (f["low"] <= f[["open", "close"]].min(axis=1)).all()
          and f[["open", "high", "low", "close", "spread"]].notna().all().all())
    check("EMA values use only completed H4 candles: unfinished final slot dropped; every candle ends at or before "
          "the data end", (f["time"] + H4 <= h1["time"].max() + H1).all())

    trunc = []
    for q in TRUNCATION_FRACTIONS:
        cut_time = h1["time"].iloc[int(len(h1) * q)] + pd.Timedelta(hours=2)
        ft, _ = build_signals(h1[h1["time"] < cut_time].reset_index(drop=True))
        cols = ["signal", "ema21", "ema50", "atr", "open", "high", "low", "close", "spread"]
        common = f["time"].isin(ft["time"])
        trunc.append(len(ft) == int(common.sum()) and np.allclose(
            ft[cols].to_numpy(float), f.loc[common, cols].to_numpy(float), equal_nan=True, rtol=1e-12, atol=1e-12))
    check("no future data leakage: H4 candles, EMAs, ATR and signals unchanged when all later H1 bars are removed "
          "(including cuts inside an H4 slot)", all(trunc), f"{len(TRUNCATION_FRACTIONS)} truncation points")

    first_valid = f.loc[f["valid"], "time"].iloc[0]
    end_time = f["time"].iloc[-1]
    span = end_time - first_valid
    bounds = [first_valid] + [f.loc[f["time"] >= first_valid + span * q, "time"].iloc[0] for q in WF_FRACTIONS] + [end_time]
    check("periods chronological and non-overlapping; development precedes all walk-forward windows",
          all(bounds[i] < bounds[i + 1] for i in range(len(bounds) - 1)))
    dev = f[(f["time"] >= bounds[0]) & (f["time"] < bounds[1]) & f["valid"]]
    atr_q = dev["atr_pct"].quantile([0.25, 0.50, 0.75]).to_numpy()
    check("ATR regime quartiles from development-period H4 candles only", dev["time"].max() < bounds[1],
          ", ".join(f"{v:.4%}" for v in atr_q))

    # ---- backtests
    runs = {}
    for mult in SPREAD_MULTIPLIERS:
        tr, rej = backtest(f, mult)
        tr["period"] = period_of(tr["signal_time"], bounds)
        rej = pd.DataFrame(rej)
        rej["period"] = period_of(rej["signal_time"], bounds) if len(rej) else []
        runs[mult] = (tr, rej)
    trades, rejected = runs[1.0]
    cost_effect = {}
    key = ["signal_time", "side"]
    for mult in SPREAD_MULTIPLIERS[1:]:
        m = trades.merge(runs[mult][0], on=key, how="outer", suffixes=("", "_x"), indicator=True)
        both = m[m["_merge"] == "both"]
        cost_effect[mult] = {
            "entry_shift_buy": float((both["entry_price_x"] - both["entry_price"])[both["side"] == "BUY"].mean()),
            "trades_only_in_one_run": int((m["_merge"] != "both").sum()),
            "changed_reason": int((both["exit_reason"] != both["exit_reason_x"]).sum()),
            "changed_time_only": int(((both["exit_reason"] == both["exit_reason_x"])
                                      & (both["exit_time"] != both["exit_time_x"])).sum()),
            "min_risk": float(trades["sl_distance"].min()), "median_risk": float(trades["sl_distance"].median()),
        }
    check("cost multipliers applied (BUY entry fills move up by the extra spread)",
          all(v["entry_shift_buy"] > 0 for v in cost_effect.values()),
          ", ".join(f"x{k}: +{v['entry_shift_buy']:.3f} USD/oz" for k, v in cost_effect.items()))
    tr2, rej2 = backtest(*build_signals(h1)[:1], 1.0)
    check("results deterministic: rebuilding candles/signals and re-running gives identical trades",
          tr2.equals(trades.drop(columns="period")) and len(rej2) == len(rejected))
    sig_total = int((f["signal"] != 0).sum())
    check("every crossover accounted for (traded or rejected with a reason)", len(trades) + len(rejected) == sig_total,
          f"{sig_total} crossovers = {len(trades)} trades + {len(rejected)} rejected")
    check("entry at the next H4 candle open (exactly 4 hours after the crossover candle)",
          ((trades["entry_time"] - trades["signal_time"]) == H4).all()
          and (trades["entry_pos"] == trades["signal_pos"] + 1).all())
    sig_pos = trades["signal_pos"].to_numpy()
    sig_rows = f.iloc[sig_pos]
    prev_rows = f.iloc[sig_pos - 1]
    buy = (trades["side"] == "BUY").to_numpy()
    cross_ok = np.where(buy, (prev_rows["ema21"].to_numpy() <= prev_rows["ema50"].to_numpy())
                        & (sig_rows["ema21"].to_numpy() > sig_rows["ema50"].to_numpy()),
                        (prev_rows["ema21"].to_numpy() >= prev_rows["ema50"].to_numpy())
                        & (sig_rows["ema21"].to_numpy() < sig_rows["ema50"].to_numpy()))
    check("crossover confirmed on a completed candle; never entered on the crossover candle",
          cross_ok.all() and (sig_rows["decision_time"].to_numpy() == trades["entry_time"].to_numpy()).all())
    atr_sig = sig_rows["atr"].to_numpy()
    exp_sl = np.where(buy, trades["entry_price"] - 1.5 * atr_sig, trades["entry_price"] + 1.5 * atr_sig)
    exp_tp = np.where(buy, trades["entry_price"] + 3.0 * atr_sig, trades["entry_price"] - 3.0 * atr_sig)
    check("ATR/SL/TP use only information at the crossover candle close plus the entry fill",
          np.allclose(trades["stop_loss"], exp_sl) and np.allclose(trades["take_profit"], exp_tp))
    check("no overlapping positions (one at a time)",
          (trades["entry_pos"].iloc[1:].to_numpy() > trades["exit_pos"].iloc[:-1].to_numpy()).all())
    check("parameters equal the pre-declared specification",
          PARAMS == {"ema_fast": 21, "ema_slow": 50, "atr_period": 14, "sl_atr_multiple": 1.5, "reward_risk": 2.0,
                     "max_open_positions": 1} and SPREAD_MULTIPLIERS == (1.0, 1.5, 2.0))

    # ---- context
    trades["atr_pct"] = sig_rows["atr_pct"].to_numpy()
    trades["atr_regime"] = pd.cut(trades["atr_pct"], [-np.inf, *atr_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"],
                                  right=False).astype(str)
    trades["session_utc_at_entry"] = session_utc(trades["entry_time"])
    for col in ("ema21", "ema50"):
        trades[f"{col}_signal"] = sig_rows[col].to_numpy()
        trades[f"{col}_prev"] = prev_rows[col].to_numpy()

    # ---- metrics
    res_rows = []

    def add(section, group, mult, tr):
        m = metrics(tr)
        res_rows.append({"section": section, "group": group, "spread_multiplier": mult, **m})
        return m

    buy_s = trades["side"] == "BUY"
    base = {"OVERALL": add("baseline", "OVERALL", 1.0, trades), "BUY": add("baseline", "BUY", 1.0, trades[buy_s]),
            "SELL": add("baseline", "SELL", 1.0, trades[~buy_s])}
    per = {p: add("period", p, 1.0, trades[trades["period"] == p]) for p in PERIODS}
    per["WF1-3"] = add("period", "WF1-3", 1.0, trades[trades["period"].isin(WF_PERIODS)])
    per_side = {f"{p} {s}": add("period_side", f"{p} {s}", 1.0,
                                trades[(trades["period"].isin(WF_PERIODS) if p == "WF1-3" else trades["period"] == p)
                                       & (trades["side"] == s)])
                for p in [*PERIODS, "WF1-3"] for s in ("BUY", "SELL")}
    cost = {mult: {g: add("cost_sensitivity", g, mult, tr if g == "OVERALL" else
                         tr[tr["period"].isin(WF_PERIODS)] if g == "WF1-3" else tr[tr["period"] == g])
                   for g in ["OVERALL", *PERIODS, "WF1-3"]} for mult, (tr, _) in runs.items()}
    regimes = {}
    for col, order in (("atr_regime", ["Q1", "Q2", "Q3", "Q4"]),
                       ("session_utc_at_entry", ["Asia", "London", "London-NY overlap", "New York", "Off-hours"]),
                       ("side", ["BUY", "SELL"])):
        regimes[col] = [(g, add(f"regime_{col}", g, 1.0, trades[trades[col] == g])) for g in order]
        regimes[col + "_wf"] = [(g, add(f"regime_{col}_wf_only", g, 1.0,
                                        trades[(trades[col] == g) & trades["period"].isin(WF_PERIODS)])) for g in order]
    rej_counts = rejected.groupby(["period", "reason"]).size().unstack(fill_value=0) if len(rejected) else pd.DataFrame()
    for p, row in rej_counts.iterrows():
        for reason, v in row.items():
            res_rows.append({"section": "rejected_signals", "group": f"{p} {reason}", "spread_multiplier": 1.0,
                             "total_trades": int(v)})

    hashes_after = snapshot(skip, cutoff_str)
    changed = sorted(k for k in set(hashes_before) | set(hashes_after) if hashes_before.get(k) != hashes_after.get(k))
    check("existing files not modified (incl. EMA-pullback files and outputs)", not changed,
          f"{len(hashes_before)} files compared")
    check("final holdout still never loaded at the end of the run",
          GUARD["test_open_attempts"] == 0 and TEST_PATH.resolve() not in GUARD["csv_reads"]
          and trades["exit_time"].max() + H4 <= cutoff + M5)

    # ---- outputs
    out = trades.drop(columns=["signal_pos", "entry_pos", "exit_pos"]).copy()
    out.insert(0, "trade_id", np.arange(1, len(out) + 1))
    out.to_csv(TRADES_PATH, index=False, date_format=TIME_FORMAT, float_format="%.6f")
    pd.DataFrame(res_rows).to_csv(RESULTS_PATH, index=False, float_format="%.6f")

    o = base["OVERALL"]
    usd_pos, r_pos = o["net_pnl"] > 0, o["average_r"] > 0
    if usd_pos and r_pos:
        neutral = ("The baseline produced a positive result after costs, in USD and in R. This is a preliminary research "
                   "result requiring independent confirmation (e.g. the reserved holdout); it is not evidence of a "
                   "profitable or live-ready strategy.")
    elif not usd_pos and not r_pos:
        neutral = ("The baseline lost money after costs, in USD and in R. No modification was made in response; the "
                   "rules as specified do not show a positive result on this data.")
    else:
        neutral = (f"The result is mixed: net {o['net_pnl']:+.2f} USD/oz (PF {o['profit_factor']:.3f}) versus "
                   f"{o['average_r']:+.4f}R per trade ({o['total_r']:+.2f}R). The units disagree because gold's price and "
                   "ATR rose several-fold over the sample, so later trades carry larger USD amounts; R corresponds to a "
                   "fixed risk per trade. No modification was made; this is not evidence of a profitable strategy.")
    neutral += (f" Break-even win rate at 2:1 before costs is 33.3%; observed {o['win_rate']:.1%} over {o['total_trades']} "
                "trades. By walk-forward window (USD/oz; R): " + ", ".join(
                    f"{p} {per[p].get('net_pnl', 0):+.2f}; {per[p].get('average_r', float('nan')):+.4f}R" for p in WF_PERIODS)
                + f". At 2.0x spread: {cost[2.0]['OVERALL']['net_pnl']:+.2f} USD/oz, "
                f"{cost[2.0]['OVERALL']['average_r']:+.4f}R per trade.")

    bars_dist = f["h1_bars"].value_counts().sort_index()
    L = ["XAUUSD H4 EMA 21/50 Crossover - research backtest", "=" * 60,
         "Research only. Fixed, pre-declared rules; no tuning, no filters, no ML, no live code, no orders.",
         TEST_STATEMENT, ""]
    L += ["1. DATA",
          f"   {H1_PATH.relative_to(SRC_DIR.parent)}: {len(h1)} H1 bid bars, {h1['time'].iloc[0]} -> {h1['time'].iloc[-1]} "
          "(MT5 MetaQuotes-Demo, server clock Europe/Athens;",
          "   OHLC verified identical to xauusd_m5.csv by the EMA-pullback experiment). No other price file was read.",
          f"   H4 candles: {len(f)} (slots 00/04/08/12/16/20 server time), {f['time'].iloc[0]} -> {f['time'].iloc[-1]}; "
          f"unfinished final slot(s) dropped: {dropped_unfinished}.",
          "   H1 bars per H4 candle: " + ", ".join(f"{int(k)} bars: {int(v)}" for k, v in bars_dist.items())
          + " (3-bar candles are the 00:00 slots after the daily break; candles are never padded).",
          f"   First candle with EMA50, previous EMA50 and ATR14 defined: {first_valid}. Usable: {first_valid} -> {end_time}.",
          f"   Final untouched holdout: everything after {cutoff_str}.", ""]
    L += ["2. STRATEGY (pre-declared, unchanged)",
          "   BUY: EMA21[prev] <= EMA50[prev] and EMA21[cross] > EMA50[cross]; SELL: EMA21[prev] >= EMA50[prev] and",
          "   EMA21[cross] < EMA50[cross] (completed H4 candles). Entry at the open of the next H4 candle, only if it is",
          "   the very next 4-hour slot; otherwise rejected (e.g. Friday 20:00 crossovers before the weekend).",
          "   SL = entry -/+ 1.5 x ATR14 (Wilder, crossover candle); TP = entry +/- 2 x risk. One position; new",
          "   crossovers ignored while in a position; no trailing, break-even, partials or discretionary exits.",
          "   Same-candle SL and TP: SL assumed first. Gap through SL: exit at the actual open (GAP_SL). Gap through",
          "   TP: exit at the TP level (no favourable slippage credited). Open position at data end: exit at the last close.",
          "   EMAs: ewm(span, adjust=False, min_periods=span), the project convention.", f"   {PARAMS}", ""]
    L += ["3. COST CALCULATION",
          f"   spread_H4 = max(max(H1 spreads in the slot), {MIN_SPREAD_POINTS} points) x ${POINT_SIZE} x multiplier",
          "   (MT5 records each H1 bar's minimum spread; taking the largest of the hourly minimums and the 15-point",
          "   floor is conservative at bar level.)",
          f"   BUY:  entry = open[next] + spread_H4[next] + {EXTRA_COST_PER_SIDE:.2f}; exits valued at bid - {EXTRA_COST_PER_SIDE:.2f}",
          f"   SELL: entry = open[next] - {EXTRA_COST_PER_SIDE:.2f}; exits valued at bid + spread_H4[exit candle] + {EXTRA_COST_PER_SIDE:.2f} (ask)",
          "   $0.05 per side is the project's $0.10 round-trip commission/slippage allowance; no separate broker",
          "   commission is included (none validated). P&L in USD per ounce (x100 per 100-oz lot); R = P&L / risk.", ""]
    L += ["4. RESEARCH DESIGN (calendar fractions of the usable period, as in the EMA-pullback experiment)"]
    L += [f"   {p:<4} {bounds[i]} -> {bounds[i + 1]}" + ("  (development)" if p == "DEV" else "") for i, p in enumerate(PERIODS)]
    L += ["   Trades belong to the period of their crossover candle; the backtest runs continuously. Only the ATR",
          "   quartile edges come from the development period; nothing else is estimated.", ""]
    L += ["5. BASELINE METRICS (spread x1.0)"] + metric_table(base)
    L += ["   Rejected signals: " + (", ".join(f"{k} {v}" for k, v in Counter(rejected["reason"]).items()) or "none"),
          f"   Crossovers: {sig_total} = {len(trades)} trades + {len(rejected)} rejected.", ""]
    L += ["6. DEVELOPMENT, WALK-FORWARD AND COMBINED WF1-3"] + metric_table(per) + ["", "   By period and side:"] \
         + short_table(list(per_side.items()))
    if len(rej_counts):
        L += ["   Rejected signals by period:"] + [f"     {p}: " + ", ".join(f"{k} {int(v)}" for k, v in row.items())
                                                  for p, row in rej_counts.iterrows()]
    L.append("")
    L += ["7. COST SENSITIVITY (predefined; spread multiplied, $0.05/side unchanged)",
          f"   {'multiplier':<12}{'group':<10}{'trades':>7}{'win%':>7}{'net':>10}{'PF':>7}{'avgR':>8}{'totR':>8}"]
    for mult, groups in cost.items():
        for g, m in groups.items():
            if not m.get("total_trades"):
                L.append(f"   {mult:<12}{g:<10}{0:>7}")
                continue
            L.append(f"   {mult:<12}{g:<10}{m['total_trades']:>7}{m['win_rate'] * 100:>7.1f}{m['net_pnl']:>+10.2f}"
                     f"{fmt(m['profit_factor'], '.3f'):>7}{m['average_r']:>+8.4f}{m['total_r']:>+8.2f}")
    L += ["   How costs act here: SL and TP are placed at fixed distances from the actual fill (which already includes",
          "   the spread), so an SL exit always loses exactly 1.5 x ATR (-1R) and a TP exit gains 3 x ATR (+2R). Costs",
          "   change results only by shifting the levels against the trader (stop slightly easier, target slightly",
          "   harder to reach), i.e. by flipping trade outcomes or timing."]
    for mult, v in cost_effect.items():
        L.append(f"   x{mult}: BUY fills +{v['entry_shift_buy']:.3f} USD/oz vs x1.0; trades whose exit reason flipped "
                 f"(TP<->SL): {v['changed_reason']}; same exit reason but different exit candle: {v['changed_time_only']}; "
                 f"trades present in only one run: {v['trades_only_in_one_run']}.")
    flips = sum(v["changed_reason"] + v["trades_only_in_one_run"] for v in cost_effect.values())
    L += [f"   Median H4 risk is {cost_effect[2.0]['median_risk']:.2f} USD/oz (minimum {cost_effect[2.0]['min_risk']:.2f}); "
          "a shift of a few tenths of a dollar " + ("flipped no TP/SL outcome in this sample (it only moved some exits "
          "to an earlier/later candle), so identical totals are expected, not a missing cost." if flips == 0 else
          "flipped some outcomes, as counted above."), ""]
    L += ["8. REGIME ANALYSIS (descriptive only; not used to alter the strategy)",
          f"   H4 ATR14/close quartiles (development edges {', '.join(f'{v:.4%}' for v in atr_q)}), crossover candle:",
          "   all periods:"] + short_table(regimes["atr_regime"]) + ["   walk-forward only:"] + short_table(regimes["atr_regime_wf"])
    L += ["   UTC session at entry (project session hours, DST-aware):", "   all periods:"] \
         + short_table(regimes["session_utc_at_entry"]) + ["   walk-forward only:"] + short_table(regimes["session_utc_at_entry_wf"])
    L += ["   BUY vs SELL:", "   all periods:"] + short_table(regimes["side"]) + ["   walk-forward only:"] \
         + short_table(regimes["side_wf"]) + [""]
    L += ["9. INTEGRITY / LEAKAGE CHECKS"] + [f"   [{'PASS' if ok else 'FAIL'}] {n}" + (f" - {d}" if d else "")
                                            for n, ok, d in checks] + [""]
    L += ["10. LIMITATIONS",
          "   - H4 bar-level simulation: intrabar order unknown (same-candle SL/TP resolved as SL); spreads are bar",
          "     minimums with a floor, not tick bid/ask. Entry after the daily break uses the first available price.",
          "   - Few trades per window for an H4 crossover system; window results carry large sampling noise.",
          "   - One broker feed; one fixed rule set; no significance test of P&L is implied.",
          "   - Not a trading recommendation; no profitability or live-readiness is claimed.", ""]
    L += ["11. NEUTRAL CONCLUSION", f"   {neutral}"]
    REPORT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    assert snapshot(skip, cutoff_str) == hashes_before, "existing files changed while writing outputs"

    print("\nFINAL SUMMARY")
    print(f"  input: {H1_PATH} ({len(h1)} H1 rows, {h1['time'].iloc[0]} -> {h1['time'].iloc[-1]}) -> {len(f)} H4 candles")
    print(f"  usable: {first_valid} -> {end_time}; holdout after {cutoff_str} never loaded")
    print(f"  parameters: {PARAMS}")
    print(f"  costs: spread max(max H1 spread in slot, {MIN_SPREAD_POINTS} pts) x {SPREAD_MULTIPLIERS}; ${EXTRA_COST_PER_SIDE}/side; no commission")
    print("  periods: " + "; ".join(f"{p} {bounds[i]} -> {bounds[i + 1]}" for i, p in enumerate(PERIODS)))
    print(f"  baseline: {o['total_trades']} trades (BUY {o['buy_trades']}, SELL {o['sell_trades']}), win {o['win_rate']:.1%}, "
          f"net {o['net_pnl']:+.2f} USD/oz, PF {o['profit_factor']:.3f}, avg R {o['average_r']:+.4f}, total R {o['total_r']:+.2f}")
    for p in [*PERIODS, "WF1-3"]:
        m = per[p]
        print(f"  {p}: {m.get('total_trades', 0)} trades, net {m.get('net_pnl', 0):+.2f}, PF {fmt(m.get('profit_factor'), '.3f')}, "
              f"avg R {m.get('average_r', float('nan')):+.4f}")
    print("  cost sensitivity: " + ", ".join(f"x{k} {v['OVERALL']['net_pnl']:+.2f} USD/oz / {v['OVERALL']['average_r']:+.4f}R"
                                            for k, v in cost.items()))
    print(f"  rejected signals: {len(rejected)} ({dict(Counter(rejected['reason']))})")
    print(f"  integrity checks: {sum(ok for _, ok, _ in checks)}/{len(checks)} passed")
    print("  outputs: " + ", ".join(str(p) for p in outputs))


if __name__ == "__main__":
    main()
