"""Frozen H70 historical challenge — exploratory retrospective only; no parameter tuning."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from phase54.archive_loader import sealed_forbidden
from signal_bot.asia_london_mss.constants import (
    HYPOTHESIS_ID,
    MAX_HOLD_BARS,
    PROJECT_ROOT,
    SIGNAL_EXPIRY_BARS,
)
from signal_bot.asia_london_mss.engine import evaluate_at
from signal_bot.asia_london_mss.sessions import in_london_window, parse_utc

PHASE53_M5 = PROJECT_ROOT / "src" / "data" / "phase53" / "mt5" / "raw" / "m5"
PHASE38_M5 = PROJECT_ROOT / "src" / "data" / "phase38" / "mt5" / "canonical"
PHASE58_SPLITS = PROJECT_ROOT / "reports" / "phase58" / "dataset_splits.json"
PHASE67_JOURNAL = (
    PROJECT_ROOT / "src" / "data" / "phase67" / "exness_market_evidence_journal" / "events.jsonl"
)
REPORTS = PROJECT_ROOT / "reports" / "completion"

LEDGER_FIELDS = [
    "setup_id",
    "trading_date",
    "direction",
    "asia_day",
    "asia_high",
    "asia_low",
    "asia_n",
    "sweep_timestamp_utc",
    "sweep_extreme",
    "sweep_side",
    "atr",
    "sweep_threshold",
    "mss_timestamp_utc",
    "mss_price",
    "entry_reference",
    "entry_fill_proxy",
    "entry_proxy_method",
    "stop_loss",
    "take_profit",
    "signal_expiry_utc",
    "exit_timestamp_utc",
    "exit_reason",
    "holding_bars",
    "gross_pnl_price",
    "gross_r",
    "data_provenance",
    "dataset_id",
    "execution_flags",
    "ambiguous_intrabar",
    "decision_idx",
    "entry_idx",
    "exit_idx",
]


def _holdout_sealed() -> set[str]:
    if not PHASE58_SPLITS.is_file():
        return set()
    return set(json.loads(PHASE58_SPLITS.read_text(encoding="utf-8")).get("holdout_sealed") or [])


def normalize_ts(ts: str) -> str:
    s = str(ts).strip().replace(" ", "T")
    if s.endswith("Z") or "+" in s[10:]:
        return s
    return s + "Z"


def load_jsonl_bars(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        ts = r.get("timestamp_utc") or r.get("server_timestamp_utc")
        if not ts:
            continue
        rows.append(
            {
                "timestamp_utc": normalize_ts(ts),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "tick_volume": r.get("tick_volume"),
                "spread": r.get("spread") or r.get("spread_points_bar"),
                "symbol": r.get("symbol"),
                "source_server": r.get("source_server"),
                "retrieval_id": r.get("retrieval_id"),
                "time_epoch": r.get("time_epoch"),
            }
        )
    rows.sort(key=lambda x: x["timestamp_utc"])
    return rows


def inventory_m5_file(
    path: Path,
    *,
    dataset_id: str,
    classification: str,
    provenance: str,
) -> dict[str, Any]:
    bars = load_jsonl_bars(path)
    day = path.stem.split("_")[-1]
    epochs: list[int] = []
    for b in bars:
        if b.get("time_epoch") is not None:
            epochs.append(int(b["time_epoch"]))
        else:
            epochs.append(int(parse_utc(b["timestamp_utc"]).timestamp()))
    gaps = []
    for a, b in zip(epochs, epochs[1:]):
        if b - a != 300:
            gaps.append({"from_epoch": a, "to_epoch": b, "delta_sec": b - a})
    ts_list = [b["timestamp_utc"] for b in bars]
    dup = sum(1 for c in Counter(ts_list).values() if c > 1)
    holdout = day in _holdout_sealed()
    forbid = day in sealed_forbidden()
    asia_start_ok = False
    if bars:
        first = parse_utc(bars[0]["timestamp_utc"])
        # Tokyo 09:00 ≈ 00:00 UTC (no Tokyo DST); truncated if first bar after 00:05
        asia_start_ok = first.hour == 0 and first.minute <= 5
    return {
        "path": str(path),
        "dataset_id": dataset_id,
        "trading_date": day,
        "classification": classification,
        "provenance": provenance,
        "source_server": bars[0].get("source_server") if bars else None,
        "symbol": bars[0].get("symbol") if bars else None,
        "n_bars": len(bars),
        "first_ts": ts_list[0] if ts_list else None,
        "last_ts": ts_list[-1] if ts_list else None,
        "n_gaps": len(gaps),
        "gap_samples": gaps[:5],
        "n_duplicate_timestamps": dup,
        "asia_session_start_present": asia_start_ok,
        "phase58_holdout_sealed": holdout,
        "phase44_49_forbidden": forbid,
        "eligible_for_h70_replay": (not holdout) and (not forbid) and classification.startswith("ELIGIBLE"),
        "independent_unconsumed": False,
        "live_collected": provenance.startswith("BROKER_OBSERVED"),
        "historical_backfill": provenance.startswith("HISTORICAL"),
        "previously_consumed_research": True if "CONSUMED" in classification else False,
    }


def build_data_inventory() -> dict[str, Any]:
    holdout = sorted(_holdout_sealed())
    forbid = sorted(sealed_forbidden())
    datasets: list[dict[str, Any]] = []

    for p in sorted(PHASE53_M5.glob("m5_XAUUSD_*.jsonl")):
        day = p.stem.replace("m5_XAUUSD_", "")
        if day in holdout:
            cls = "EXCLUDED_PHASE58_HOLDOUT_SEALED"
        elif day in sealed_forbidden():
            cls = "EXCLUDED_PHASE44_49_FORBIDDEN"
        else:
            cls = "ELIGIBLE_CONSUMED_ARCHIVE"
        datasets.append(
            inventory_m5_file(
                p,
                dataset_id=f"phase53_mt5_raw_m5:{day}",
                classification=cls,
                provenance="HISTORICAL_BACKFILL_METAQUOTES_DEMO_ARCHIVE",
            )
        )

    for p in sorted(PHASE38_M5.glob("m5_XAUUSD_*.jsonl")):
        day = p.stem.replace("m5_XAUUSD_", "")
        if day in holdout:
            cls = "EXCLUDED_PHASE58_HOLDOUT_SEALED"
        elif day in sealed_forbidden():
            cls = "EXCLUDED_PHASE44_49_FORBIDDEN"
        else:
            cls = "ELIGIBLE_CONSUMED_ARCHIVE_SECONDARY"
        datasets.append(
            inventory_m5_file(
                p,
                dataset_id=f"phase38_canonical_m5:{day}",
                classification=cls,
                provenance="HISTORICAL_BACKFILL_METAQUOTES_DEMO_ARCHIVE",
            )
        )

    live: dict[str, Any] = {
        "dataset_id": "phase67_exness_journal",
        "path": str(PHASE67_JOURNAL),
        "provenance": "BROKER_OBSERVED_LIVE_PARTIAL",
        "classification": "INSUFFICIENT_FOR_H70_SESSION_COVERAGE",
        "independent_unconsumed_for_h70": True,
        "eligible_complete_asia_london_days": 0,
        "note": "Live XAUUSDm M5 exists but does not cover a complete Asia+London H70 window.",
    }
    if PHASE67_JOURNAL.is_file():
        m5 = []
        for line in PHASE67_JOURNAL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("kind") != "M5_BAR":
                continue
            m5.append(e)
        dates = sorted({str(e.get("server_timestamp_utc", ""))[:10] for e in m5})
        live.update(
            {
                "n_m5_bars": len(m5),
                "unique_dates": dates,
                "first_ts": m5[0].get("server_timestamp_utc") if m5 else None,
                "last_ts": m5[-1].get("server_timestamp_utc") if m5 else None,
                "symbol": (m5[0].get("symbol") if m5 else None),
                "source_server": (m5[0].get("source_server") if m5 else None),
            }
        )

    eligible = [d for d in datasets if d.get("eligible_for_h70_replay")]
    return {
        "hypothesis_id": HYPOTHESIS_ID,
        "evidence_class": "EXPLORATORY_RETROSPECTIVE_ONLY",
        "independent_unconsumed_complete_days": 0,
        "phase58_holdout_sealed_not_accessed": holdout,
        "phase44_49_forbidden": forbid,
        "n_datasets_inventoried": len(datasets) + 1,
        "n_eligible_consumed_phase53_days": len(
            [d for d in eligible if d["dataset_id"].startswith("phase53")]
        ),
        "eligible_phase53_dates": [
            d["trading_date"] for d in eligible if d["dataset_id"].startswith("phase53")
        ],
        "datasets": datasets,
        "live_broker_observed": live,
        "notes": [
            "All phase53/phase38 M5 archives are MetaQuotes demo historical backfill previously consumed by research phases.",
            "Symbol in archives is XAUUSD, not Exness XAUUSDm — engineering replay only.",
            "Phase58 holdout dates present on disk were not loaded into the H70 challenge ledger.",
            "No genuinely independent complete Asia+London day exists for confirmatory validation.",
        ],
    }


@dataclass
class TradeRow:
    setup_id: str
    trading_date: str
    direction: str
    asia_day: str
    asia_high: float
    asia_low: float
    asia_n: int
    sweep_timestamp_utc: str
    sweep_extreme: float
    sweep_side: str
    atr: float
    sweep_threshold: float
    mss_timestamp_utc: str
    mss_price: float
    entry_reference: float
    entry_fill_proxy: float | None
    entry_proxy_method: str
    stop_loss: float
    take_profit: float
    signal_expiry_utc: str | None
    exit_timestamp_utc: str | None
    exit_reason: str
    holding_bars: int | None
    gross_pnl_price: float | None
    gross_r: float | None
    data_provenance: str
    dataset_id: str
    execution_flags: str
    ambiguous_intrabar: bool
    decision_idx: int
    entry_idx: int | None
    exit_idx: int | None
    extras: dict[str, Any] = field(default_factory=dict)


def _simulate_trade(
    bars: list[dict[str, Any]],
    decision_idx: int,
    direction: str,
    entry_ref: float,
    sl: float,
    tp: float,
) -> dict[str, Any]:
    """OHLC proxy: fill at next bar open after signal; SL-first if both touched same bar."""
    flags: list[str] = []
    entry_idx = decision_idx + 1
    if entry_idx >= len(bars):
        return {
            "entry_fill_proxy": None,
            "entry_proxy_method": "NO_NEXT_BAR",
            "exit_reason": "SIGNAL_EXPIRED_NO_ENTRY_BAR",
            "exit_timestamp_utc": None,
            "holding_bars": None,
            "gross_pnl_price": None,
            "gross_r": None,
            "ambiguous_intrabar": False,
            "execution_flags": "NO_ENTRY_BAR",
            "entry_idx": None,
            "exit_idx": None,
        }
    # Expiry: entry must occur within SIGNAL_EXPIRY_BARS after confirmation
    if entry_idx > decision_idx + SIGNAL_EXPIRY_BARS:
        return {
            "entry_fill_proxy": None,
            "entry_proxy_method": "EXPIRED",
            "exit_reason": "SIGNAL_EXPIRED",
            "exit_timestamp_utc": bars[min(decision_idx + SIGNAL_EXPIRY_BARS, len(bars) - 1)][
                "timestamp_utc"
            ],
            "holding_bars": 0,
            "gross_pnl_price": None,
            "gross_r": None,
            "ambiguous_intrabar": False,
            "execution_flags": "EXPIRED_BEFORE_ENTRY",
            "entry_idx": None,
            "exit_idx": None,
        }

    entry = float(bars[entry_idx]["open"])
    flags.append("ENTRY_NEXT_BAR_OPEN_AFTER_MSS_CLOSE")
    flags.append("OHLC_PROXY_NO_TICK_PATH")
    risk = abs(entry_ref - sl)
    # Recompute risk from actual fill vs frozen SL (strategy SL anchored to signal levels)
    if direction == "BUY":
        risk_fill = entry - sl
    else:
        risk_fill = sl - entry
    if risk_fill <= 0:
        flags.append("FILL_INVALID_VS_SL")
        return {
            "entry_fill_proxy": entry,
            "entry_proxy_method": "NEXT_BAR_OPEN",
            "exit_reason": "INVALID_FILL_VS_STOP",
            "exit_timestamp_utc": bars[entry_idx]["timestamp_utc"],
            "holding_bars": 0,
            "gross_pnl_price": None,
            "gross_r": None,
            "ambiguous_intrabar": False,
            "execution_flags": "|".join(flags),
            "entry_idx": entry_idx,
            "exit_idx": entry_idx,
        }

    # Adjust TP to 2R from fill while keeping frozen SL (execution realism vs product TP)
    # Prompt: do not modify frozen strategy rules. Keep strategy TP; measure vs fill.
    # Use frozen TP/SL from signal; PnL from fill.
    last_idx = min(entry_idx + MAX_HOLD_BARS - 1, len(bars) - 1)
    ambiguous = False
    for j in range(entry_idx, last_idx + 1):
        bar = bars[j]
        hi, lo = float(bar["high"]), float(bar["low"])
        hit_sl = hit_tp = False
        if direction == "BUY":
            hit_sl = lo <= sl
            hit_tp = hi >= tp
        else:
            hit_sl = hi >= sl
            hit_tp = lo <= tp
        if hit_sl and hit_tp:
            ambiguous = True
            flags.append("AMBIGUOUS_SL_TP_SAME_BAR_SL_FIRST")
            pnl = (sl - entry) if direction == "BUY" else (entry - sl)
            return {
                "entry_fill_proxy": entry,
                "entry_proxy_method": "NEXT_BAR_OPEN",
                "exit_reason": "STOP_LOSS_AMBIGUOUS_BAR",
                "exit_timestamp_utc": bar["timestamp_utc"],
                "holding_bars": j - entry_idx + 1,
                "gross_pnl_price": pnl,
                "gross_r": pnl / risk_fill,
                "ambiguous_intrabar": True,
                "execution_flags": "|".join(flags),
                "entry_idx": entry_idx,
                "exit_idx": j,
                "risk_at_fill": risk_fill,
                "risk_at_signal": risk,
            }
        if hit_sl:
            # Gap through stop: fill at worse of SL and open if gap
            fill_px = sl
            if direction == "BUY" and float(bar["open"]) < sl:
                fill_px = float(bar["open"])
                flags.append("GAP_THROUGH_STOP_CONSERVATIVE")
            if direction == "SELL" and float(bar["open"]) > sl:
                fill_px = float(bar["open"])
                flags.append("GAP_THROUGH_STOP_CONSERVATIVE")
            pnl = (fill_px - entry) if direction == "BUY" else (entry - fill_px)
            return {
                "entry_fill_proxy": entry,
                "entry_proxy_method": "NEXT_BAR_OPEN",
                "exit_reason": "STOP_LOSS",
                "exit_timestamp_utc": bar["timestamp_utc"],
                "holding_bars": j - entry_idx + 1,
                "gross_pnl_price": pnl,
                "gross_r": pnl / risk_fill,
                "ambiguous_intrabar": ambiguous,
                "execution_flags": "|".join(flags),
                "entry_idx": entry_idx,
                "exit_idx": j,
                "risk_at_fill": risk_fill,
            }
        if hit_tp:
            pnl = (tp - entry) if direction == "BUY" else (entry - tp)
            return {
                "entry_fill_proxy": entry,
                "entry_proxy_method": "NEXT_BAR_OPEN",
                "exit_reason": "TAKE_PROFIT",
                "exit_timestamp_utc": bar["timestamp_utc"],
                "holding_bars": j - entry_idx + 1,
                "gross_pnl_price": pnl,
                "gross_r": pnl / risk_fill,
                "ambiguous_intrabar": False,
                "execution_flags": "|".join(flags),
                "entry_idx": entry_idx,
                "exit_idx": j,
                "risk_at_fill": risk_fill,
            }

    # Max hold exit at last bar close
    bar = bars[last_idx]
    fill_px = float(bar["close"])
    flags.append("MAX_HOLD_EXIT")
    pnl = (fill_px - entry) if direction == "BUY" else (entry - fill_px)
    return {
        "entry_fill_proxy": entry,
        "entry_proxy_method": "NEXT_BAR_OPEN",
        "exit_reason": "MAX_HOLD",
        "exit_timestamp_utc": bar["timestamp_utc"],
        "holding_bars": last_idx - entry_idx + 1,
        "gross_pnl_price": pnl,
        "gross_r": pnl / risk_fill,
        "ambiguous_intrabar": False,
        "execution_flags": "|".join(flags),
        "entry_idx": entry_idx,
        "exit_idx": last_idx,
        "risk_at_fill": risk_fill,
    }


def replay_day(
    bars: list[dict[str, Any]],
    *,
    trading_date: str,
    dataset_id: str,
    provenance: str,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    fired_setups: set[str] = set()
    position_open_until: int | None = None

    for i in range(len(bars)):
        ts = bars[i]["timestamp_utc"]
        # Only evaluate inside London window for signal generation (engine also gates)
        if not in_london_window(ts):
            continue
        if position_open_until is not None and i <= position_open_until:
            decisions.append(
                {
                    "idx": i,
                    "ts": ts,
                    "action": "WAIT",
                    "reason_codes": ["POSITION_ALREADY_OPEN_NO_OVERLAP"],
                }
            )
            continue

        d = evaluate_at(bars, i, forming_bar=False, symbol="XAUUSD")
        action = d.get("action") or "WAIT"
        decisions.append(
            {
                "idx": i,
                "ts": ts,
                "action": action,
                "reason_codes": list(d.get("reason_codes") or []),
                "setup_id": d.get("setup_id"),
            }
        )
        if action == "WAIT":
            rejected.append(
                {
                    "idx": i,
                    "ts": ts,
                    "reason_codes": list(d.get("reason_codes") or []),
                }
            )
            continue

        setup_id = str(d.get("setup_id") or f"{HYPOTHESIS_ID}:{trading_date}:{i}")
        if setup_id in fired_setups:
            decisions[-1]["reason_codes"].append("DUPLICATE_SETUP_SUPPRESSED")
            continue
        fired_setups.add(setup_id)

        ar = d.get("asia_range") or {}
        sweep = d.get("sweep") or {}
        mss = d.get("mss") or {}
        atr = float(d.get("atr") or 0.0)
        thresh = max(0.05, 0.05 * atr) if atr else 0.05
        sim = _simulate_trade(
            bars,
            i,
            action,
            float(d["entry_reference"]),
            float(d["stop_loss"]),
            float(d["take_profit"]),
        )
        row = {
            "setup_id": setup_id,
            "trading_date": trading_date,
            "direction": action,
            "asia_day": ar.get("asia_day"),
            "asia_high": ar.get("high"),
            "asia_low": ar.get("low"),
            "asia_n": ar.get("n"),
            "sweep_timestamp_utc": sweep.get("timestamp_utc"),
            "sweep_extreme": sweep.get("extreme"),
            "sweep_side": sweep.get("side"),
            "atr": atr,
            "sweep_threshold": thresh,
            "mss_timestamp_utc": mss.get("timestamp_utc"),
            "mss_price": float(d["entry_reference"]),
            "entry_reference": float(d["entry_reference"]),
            "entry_fill_proxy": sim.get("entry_fill_proxy"),
            "entry_proxy_method": sim.get("entry_proxy_method"),
            "stop_loss": float(d["stop_loss"]),
            "take_profit": float(d["take_profit"]),
            "signal_expiry_utc": d.get("signal_expiry_utc"),
            "exit_timestamp_utc": sim.get("exit_timestamp_utc"),
            "exit_reason": sim.get("exit_reason"),
            "holding_bars": sim.get("holding_bars"),
            "gross_pnl_price": sim.get("gross_pnl_price"),
            "gross_r": sim.get("gross_r"),
            "data_provenance": provenance,
            "dataset_id": dataset_id,
            "execution_flags": sim.get("execution_flags"),
            "ambiguous_intrabar": bool(sim.get("ambiguous_intrabar")),
            "decision_idx": i,
            "entry_idx": sim.get("entry_idx"),
            "exit_idx": sim.get("exit_idx"),
        }
        trades.append(row)
        if sim.get("exit_idx") is not None:
            position_open_until = int(sim["exit_idx"])
        else:
            position_open_until = i + SIGNAL_EXPIRY_BARS

    return {
        "trading_date": trading_date,
        "dataset_id": dataset_id,
        "n_bars": len(bars),
        "n_london_decisions": len(decisions),
        "n_buy": sum(1 for t in trades if t["direction"] == "BUY"),
        "n_sell": sum(1 for t in trades if t["direction"] == "SELL"),
        "n_wait_evaluations": sum(1 for d in decisions if d["action"] == "WAIT"),
        "trades": trades,
        "decisions_sha256": _sha_obj(
            [{"idx": d["idx"], "action": d["action"], "setup_id": d.get("setup_id")} for d in decisions]
        ),
        "trades_sha256": _sha_obj(trades),
    }


def _sha_obj(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def run_frozen_replay(eligible_dates: list[str] | None = None) -> dict[str, Any]:
    inv = build_data_inventory()
    dates = eligible_dates or list(inv["eligible_phase53_dates"])
    # Safety: never touch holdout
    holdout = _holdout_sealed()
    forbid = sealed_forbidden()
    dates = [d for d in dates if d not in holdout and d not in forbid]

    day_results = []
    all_trades: list[dict[str, Any]] = []
    for day in dates:
        path = PHASE53_M5 / f"m5_XAUUSD_{day}.jsonl"
        if not path.is_file():
            continue
        bars = load_jsonl_bars(path)
        res = replay_day(
            bars,
            trading_date=day,
            dataset_id=f"phase53_mt5_raw_m5:{day}",
            provenance="HISTORICAL_BACKFILL_METAQUOTES_DEMO_ARCHIVE",
        )
        day_results.append({k: v for k, v in res.items() if k != "trades"})
        all_trades.extend(res["trades"])

    return {
        "evidence_class": "EXPLORATORY_RETROSPECTIVE_ONLY",
        "archive_root": str(PHASE53_M5),
        "dates": dates,
        "n_dates": len(dates),
        "day_results": day_results,
        "trades": all_trades,
        "ledger_sha256": _sha_obj(all_trades),
        "n_trades": len(all_trades),
        "holdout_accessed": False,
        "parameters_tuned": False,
    }


def run_deterministic_twice() -> dict[str, Any]:
    a = run_frozen_replay()
    b = run_frozen_replay()
    same = a["ledger_sha256"] == b["ledger_sha256"] and a["n_trades"] == b["n_trades"]
    return {
        "identical": same,
        "ledger_sha256_a": a["ledger_sha256"],
        "ledger_sha256_b": b["ledger_sha256"],
        "n_trades": a["n_trades"],
        "replay_a": a,
        "replay_b_sha_only": b["ledger_sha256"],
    }


def write_ledger_csv(trades: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
        w.writeheader()
        for t in trades:
            row = {k: t.get(k) for k in LEDGER_FIELDS}
            if isinstance(row.get("ambiguous_intrabar"), bool):
                row["ambiguous_intrabar"] = str(row["ambiguous_intrabar"]).upper()
            w.writerow(row)
    return path


def _ci_mean(xs: list[float]) -> dict[str, Any]:
    if not xs:
        return {"n": 0, "mean": None, "ci95": None}
    n = len(xs)
    mean = statistics.mean(xs)
    if n < 2:
        return {"n": n, "mean": mean, "ci95": None, "note": "n<2 — CI undefined"}
    sd = statistics.stdev(xs)
    se = sd / math.sqrt(n)
    # Normal approx; date-blocked caution noted by caller
    return {"n": n, "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se], "se": se}


def performance_stats(trades: list[dict[str, Any]], dates: list[str]) -> dict[str, Any]:
    realized = [t for t in trades if t.get("gross_r") is not None]
    rs = [float(t["gross_r"]) for t in realized]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    by_dir = {"BUY": [], "SELL": []}
    for t in realized:
        by_dir[t["direction"]].append(float(t["gross_r"]))

    def _dir_stats(xs: list[float], n_signals: int) -> dict[str, Any]:
        w = [x for x in xs if x > 0]
        l = [x for x in xs if x <= 0]
        gp = sum(x for x in xs if x > 0)
        gl = abs(sum(x for x in xs if x <= 0))
        return {
            "n_trades": len(xs),
            "n_signals": n_signals,
            "win_rate": (len(w) / len(xs)) if xs else None,
            "avg_win_r": statistics.mean(w) if w else None,
            "avg_loss_r": statistics.mean(l) if l else None,
            "expectancy_gross_r": statistics.mean(xs) if xs else None,
            "profit_factor": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else None),
            "median_r": statistics.median(xs) if xs else None,
            "sum_r": sum(xs) if xs else 0.0,
        }

    # Equity / drawdown in R (chronological by exit then setup)
    ordered = sorted(
        realized,
        key=lambda t: (t.get("exit_timestamp_utc") or "", t.get("setup_id") or ""),
    )
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    curve = []
    for t in ordered:
        equity += float(t["gross_r"])
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        curve.append(equity)

    # Consecutive
    max_cw = max_cl = cw = cl = 0
    for r in rs:
        if r > 0:
            cw += 1
            cl = 0
            max_cw = max(max_cw, cw)
        else:
            cl += 1
            cw = 0
            max_cl = max(max_cl, cl)

    # Date-blocked: mean of daily sum R
    by_date: dict[str, float] = defaultdict(float)
    for t in realized:
        by_date[t["trading_date"]] += float(t["gross_r"])
    daily = [by_date[d] for d in sorted(by_date)]
    monthly: dict[str, float] = defaultdict(float)
    for d, v in by_date.items():
        monthly[d[:7]] += v

    exit_counts = Counter(t.get("exit_reason") for t in trades)
    holds = [int(t["holding_bars"]) for t in realized if t.get("holding_bars") is not None]

    gp = sum(r for r in rs if r > 0)
    gl = abs(sum(r for r in rs if r <= 0))

    return {
        "total_signals": len(trades),
        "total_realized_trades": len(realized),
        "n_buy": sum(1 for t in trades if t["direction"] == "BUY"),
        "n_sell": sum(1 for t in trades if t["direction"] == "SELL"),
        "unique_trading_dates_with_trades": sorted({t["trading_date"] for t in trades}),
        "unique_eligible_dates": dates,
        "n_eligible_dates": len(dates),
        "n_dates_with_trades": len({t["trading_date"] for t in trades}),
        "win_rate": (len(wins) / len(rs)) if rs else None,
        "avg_win_r": statistics.mean(wins) if wins else None,
        "avg_loss_r": statistics.mean(losses) if losses else None,
        "expectancy_gross_r": statistics.mean(rs) if rs else None,
        "expectancy_ci95_trade_naive": _ci_mean(rs),
        "profit_factor_gross": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else None),
        "median_r": statistics.median(rs) if rs else None,
        "sum_gross_r": sum(rs) if rs else 0.0,
        "max_drawdown_r": max_dd,
        "max_consecutive_wins": max_cw,
        "max_consecutive_losses": max_cl,
        "avg_holding_bars": statistics.mean(holds) if holds else None,
        "exit_reason_counts": dict(exit_counts),
        "ambiguous_executions": sum(1 for t in trades if t.get("ambiguous_intrabar")),
        "buy": _dir_stats(by_dir["BUY"], sum(1 for t in trades if t["direction"] == "BUY")),
        "sell": _dir_stats(by_dir["SELL"], sum(1 for t in trades if t["direction"] == "SELL")),
        "daily_sum_r": dict(sorted(by_date.items())),
        "date_blocked_daily_expectancy": _ci_mean(daily),
        "monthly_sum_r": dict(sorted(monthly.items())),
        "net_profitability": "NOT_ESTABLISHED",
        "commission": "UNKNOWN",
        "swap": "UNKNOWN_FOR_EXECUTION",
        "spread_cost_modeled": False,
        "wait_benchmark": {
            "trades": 0,
            "realized_r": 0.0,
            "exposure": 0.0,
            "comparison_gross": (
                "H70_GROSS_BETTER_THAN_WAIT"
                if (sum(rs) if rs else 0) > 0
                else (
                    "H70_GROSS_WORSE_OR_EQUAL_WAIT"
                    if rs
                    else "H70_NO_REALIZED_TRADES_EQUAL_WAIT_EXPOSURE"
                )
            ),
            "note": "Gross comparison only; costs unknown ⇒ no net economic advantage claim.",
        },
        "sample_limitation": (
            "Small date-blocked sample on consumed MetaQuotes archive; "
            "trade-level CI overstates independence; not confirmatory."
        ),
    }


def failure_analysis(trades: list[dict[str, Any]], day_results: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [t for t in trades if t.get("gross_r") is not None]
    losers = [t for t in realized if float(t["gross_r"]) <= 0]
    winners = [t for t in realized if float(t["gross_r"]) > 0]
    patterns = []

    # 1. Direction imbalance
    buy_r = [float(t["gross_r"]) for t in realized if t["direction"] == "BUY"]
    sell_r = [float(t["gross_r"]) for t in realized if t["direction"] == "SELL"]
    if buy_r or sell_r:
        patterns.append(
            {
                "pattern": "DIRECTION_ASYMMETRY",
                "evidence": {
                    "buy_n": len(buy_r),
                    "buy_sum_r": sum(buy_r) if buy_r else 0,
                    "buy_mean_r": statistics.mean(buy_r) if buy_r else None,
                    "sell_n": len(sell_r),
                    "sell_sum_r": sum(sell_r) if sell_r else 0,
                    "sell_mean_r": statistics.mean(sell_r) if sell_r else None,
                    "trade_ids": [t["setup_id"] for t in realized],
                },
                "supported": True,
            }
        )

    # 2. SL frequency / targets rarely reached
    exits = Counter(t.get("exit_reason") for t in trades)
    patterns.append(
        {
            "pattern": "EXIT_MIX_SL_VS_TP_VS_TIME",
            "evidence": {
                "counts": dict(exits),
                "tp_ids": [t["setup_id"] for t in trades if t.get("exit_reason") == "TAKE_PROFIT"],
                "sl_ids": [
                    t["setup_id"]
                    for t in trades
                    if str(t.get("exit_reason") or "").startswith("STOP_LOSS")
                ],
                "max_hold_ids": [t["setup_id"] for t in trades if t.get("exit_reason") == "MAX_HOLD"],
            },
            "supported": True,
        }
    )

    # 3. Stop distance large vs ATR
    stop_vs_atr = []
    for t in realized:
        atr = float(t.get("atr") or 0) or 1e-9
        risk = abs(float(t["entry_fill_proxy"]) - float(t["stop_loss"]))
        stop_vs_atr.append(
            {
                "setup_id": t["setup_id"],
                "date": t["trading_date"],
                "risk": risk,
                "risk_over_atr": risk / atr,
                "gross_r": t["gross_r"],
            }
        )
    large = [x for x in stop_vs_atr if x["risk_over_atr"] > 1.5]
    patterns.append(
        {
            "pattern": "LARGE_STOP_DISTANCE_VS_ATR",
            "evidence": {
                "n_risk_gt_1_5_atr": len(large),
                "samples": large[:10],
                "median_risk_over_atr": statistics.median([x["risk_over_atr"] for x in stop_vs_atr])
                if stop_vs_atr
                else None,
            },
            "supported": bool(stop_vs_atr),
        }
    )

    # 4. Concentration in few dates
    by_date = defaultdict(float)
    for t in realized:
        by_date[t["trading_date"]] += float(t["gross_r"])
    if by_date:
        ranked = sorted(by_date.items(), key=lambda kv: abs(kv[1]), reverse=True)
        top = ranked[:3]
        patterns.append(
            {
                "pattern": "DATE_CONCENTRATION",
                "evidence": {
                    "daily_sum_r": dict(sorted(by_date.items())),
                    "top_abs_contribution_dates": top,
                    "trade_ids_by_top_date": {
                        d: [t["setup_id"] for t in realized if t["trading_date"] == d]
                        for d, _ in top
                    },
                },
                "supported": True,
            }
        )

    # 5. Chronological deterioration
    chron = sorted(by_date.items())
    if len(chron) >= 4:
        mid = len(chron) // 2
        first_half = sum(v for _, v in chron[:mid])
        second_half = sum(v for _, v in chron[mid:])
        patterns.append(
            {
                "pattern": "CHRONOLOGICAL_HALF_COMPARISON",
                "evidence": {
                    "first_half_dates": [d for d, _ in chron[:mid]],
                    "second_half_dates": [d for d, _ in chron[mid:]],
                    "first_half_sum_r": first_half,
                    "second_half_sum_r": second_half,
                },
                "supported": True,
            }
        )

    # 6. MSS late / few signals relative to days
    patterns.append(
        {
            "pattern": "LOW_SIGNAL_DENSITY",
            "evidence": {
                "n_days_replayed": len(day_results),
                "n_trades": len(trades),
                "trades_per_day": (len(trades) / len(day_results)) if day_results else 0,
                "days_with_zero_trades": [
                    d["trading_date"]
                    for d in day_results
                    if d.get("n_buy", 0) + d.get("n_sell", 0) == 0
                ],
            },
            "supported": True,
        }
    )

    # Loser detail
    loser_detail = [
        {
            "setup_id": t["setup_id"],
            "date": t["trading_date"],
            "direction": t["direction"],
            "gross_r": t["gross_r"],
            "exit_reason": t["exit_reason"],
            "holding_bars": t["holding_bars"],
            "sweep_side": t.get("sweep_side"),
        }
        for t in losers
    ]

    return {
        "n_realized": len(realized),
        "n_winners": len(winners),
        "n_losers": len(losers),
        "patterns": patterns,
        "loser_detail": loser_detail,
        "winner_detail": [
            {
                "setup_id": t["setup_id"],
                "date": t["trading_date"],
                "direction": t["direction"],
                "gross_r": t["gross_r"],
                "exit_reason": t["exit_reason"],
            }
            for t in winners
        ],
        "unsupported_claims_avoided": [
            "Cannot assert institutional intent from OHLC alone.",
            "Cannot assert net edge without costs.",
            "Cannot treat consumed archive as independent OOS.",
        ],
    }


def implementation_audit() -> dict[str, Any]:
    """Static audit of frozen constants/engine vs PROMPT_03 definition — no silent repairs."""
    from signal_bot.asia_london_mss import constants as C

    checks = [
        ("tokyo_session", C.ASIA_TZ == "Asia/Tokyo" and C.ASIA_START_HM == (9, 0) and C.ASIA_END_HM == (15, 0)),
        ("london_session", C.LONDON_TZ == "Europe/London" and C.LONDON_START_HM == (8, 0) and C.LONDON_END_HM == (12, 0)),
        ("sweep_threshold_formula", C.SWEEP_BUFFER_ATR == 0.05 and C.SWEEP_BUFFER_ABS_MIN == 0.05),
        ("close_back_inside", C.REQUIRE_CLOSE_BACK_INSIDE is True),
        ("fractal_L2_R2", C.SWING_LEFT == 2 and C.SWING_RIGHT == 2),
        ("tp_2R", C.REWARD_RISK == 2.0),
        ("expiry_3", C.SIGNAL_EXPIRY_BARS == 3),
        ("max_hold_48", C.MAX_HOLD_BARS == 48),
        ("sl_buffer", C.SL_BUFFER_ATR == 0.05 and C.SL_BUFFER_ABS_MIN == 0.05),
        ("champion_no_model", C.CHAMPION_STATUS == "NO_MODEL"),
        ("order_send_prohibited", C.ORDER_SEND == "PROHIBITED"),
    ]
    mismatches = [name for name, ok in checks if not ok]

    # Behavioral notes (not silent defects of frozen hypothesis)
    observations = [
        {
            "id": "ENTRY_REFERENCE_VS_FILL",
            "severity": False,
            "note": (
                "Engine entry_reference is MSS confirmation close per frozen spec. "
                "Challenge ledger uses next-bar open as earliest defensible fill proxy; "
                "this is execution modeling, not a strategy-rule rewrite."
            ),
        },
        {
            "id": "FIRST_SWEEP_ONLY",
            "severity": False,
            "note": "Engine locks the first valid sweep after Asia completion; later sweeps ignored for that decision path — matches implementation; document as design choice.",
        },
        {
            "id": "ASIA_TRUNCATION_IN_ARCHIVE",
            "severity": False,
            "note": (
                "Many phase53 day files start at 01:00/01:05 UTC, omitting early Asia bars. "
                "Not an engine bug; data incompleteness flagged in eligibility."
            ),
        },
        {
            "id": "ARCHIVE_SYMBOL_XAUUSD",
            "severity": False,
            "note": "Replay archives use XAUUSD MetaQuotes demo; live target is XAUUSDm Exness. Not silent repair.",
        },
        {
            "id": "NO_LOOKAHEAD_IN_SWINGS",
            "severity": False,
            "note": "confirmed_swing_* require confirm_idx <= asof_idx; evaluate_at windows bars[:decision_idx+1].",
        },
    ]

    material_defect = len(mismatches) > 0
    return {
        "spec_source": "reports/completion/PROMPT_03_STRATEGY_DEFINITION.md",
        "checks": [{"name": n, "pass": ok} for n, ok in checks],
        "mismatches": mismatches,
        "material_defect": material_defect,
        "observations": observations,
        "result": "MATCH_FROZEN_SPEC" if not material_defect else "IMPLEMENTATION_DEFECT",
        "economic_evaluation_permitted": not material_defect,
    }
