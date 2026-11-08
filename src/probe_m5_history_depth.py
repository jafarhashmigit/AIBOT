"""Read-only probe of XAUUSD M5 history strictly BEFORE 2026-02-16.

No bars are requested at or after 2026-02-16 08:50 (the first bar of the
existing raw file). No bars at or after the research cutoff are requested.
Nothing is written under src/data/. No orders are sent.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from evaluation.constants import DEFAULT_SEED
from evaluation.integrity import reports_dir
from evaluation.report import save, wrap

MT5_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
# Exclusive end: last timestamp we will *request* is strictly before the existing file start.
EXISTING_M5_START = datetime(2026, 2, 16, 8, 50, tzinfo=timezone.utc)
PROBE_END = datetime(2026, 2, 16, 8, 45, tzinfo=timezone.utc)
START_YEARS = (2018, 2020, 2022, 2023, 2024, 2025, 2026)


def _month_window(year: int, month: int) -> tuple[datetime, datetime] | None:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(minutes=5)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(minutes=5)
    if start >= PROBE_END:
        return None
    if end >= EXISTING_M5_START:
        end = PROBE_END
    if start > end:
        return None
    return start, end


def _summarize(rates, err) -> dict:
    n = 0 if rates is None else len(rates)
    first = last = None
    if n:
        first = pd.to_datetime(rates[0]["time"], unit="s")
        last = pd.to_datetime(rates[-1]["time"], unit="s")
        if last.to_pydatetime().replace(tzinfo=timezone.utc) >= EXISTING_M5_START:
            raise RuntimeError(f"probe returned a bar at/after existing start: {last}")
    return {"n": n, "first": str(first), "last": str(last), "mt5_error": err}


def run() -> dict:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        payload = {"status": "blocked", "error": f"MetaTrader5 import failed: {exc}"}
        save(reports_dir() / "m5_history_depth_probe.json",
             wrap("m5_history_depth_probe", "exploratory", {"end": str(PROBE_END)}, payload, DEFAULT_SEED))
        print(payload)
        return payload

    if not mt5.initialize(path=MT5_TERMINAL, timeout=60000):
        payload = {"status": "blocked", "error": f"MT5 initialize failed: {mt5.last_error()}"}
        save(reports_dir() / "m5_history_depth_probe.json",
             wrap("m5_history_depth_probe", "exploratory", {"end": str(PROBE_END)}, payload, DEFAULT_SEED))
        print(payload)
        return payload

    try:
        info = mt5.terminal_info()
        account = mt5.account_info()
        maxbars = getattr(info, "maxbars", None)
        server = getattr(account, "server", None) if account else None
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"{SYMBOL} not available: {mt5.last_error()}")

        by_year = []
        for year in START_YEARS:
            start = datetime(year, 1, 1, tzinfo=timezone.utc)
            if start >= PROBE_END:
                continue
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, start, PROBE_END)
            by_year.append({"start_year": year, **_summarize(rates, mt5.last_error())})

        # Batching: two adjacent windows that together should cover 2025-01-01 .. probe_end.
        mid = datetime(2025, 8, 1, tzinfo=timezone.utc)
        a = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, datetime(2025, 1, 1, tzinfo=timezone.utc), mid)
        b = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, mid, PROBE_END)
        batch = {
            "window_a": 0 if a is None else len(a),
            "window_b": 0 if b is None else len(b),
            "sum": (0 if a is None else len(a)) + (0 if b is None else len(b)),
        }

        # Longest successful range among the year probes.
        ok = [row for row in by_year if row["n"]]
        earliest = min(row["first"] for row in ok) if ok else None
        latest = max(row["last"] for row in ok) if ok else None
        deepest = max(ok, key=lambda r: r["n"]) if ok else None

        monthly = []
        year, month = 2026, 2
        empty_run = 0
        while (year, month) >= (2018, 1) and empty_run < 12:
            window = _month_window(year, month)
            if window is None:
                month -= 1
                if month == 0:
                    year, month = year - 1, 12
                continue
            start, end = window
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, start, end)
            row = {"year": year, "month": month, **_summarize(rates, mt5.last_error())}
            monthly.append(row)
            empty_run = empty_run + 1 if row["n"] == 0 else 0
            month -= 1
            if month == 0:
                year, month = year - 1, 12

        monthly_ok = [row for row in monthly if row["n"]]
        if monthly_ok:
            earliest = min(row["first"] for row in monthly_ok)
            latest = max(row["last"] for row in monthly_ok)

        n_gaps = None
        weekendish = None
        if deepest and deepest["n"]:
            start = datetime(deepest["start_year"], 1, 1, tzinfo=timezone.utc)
            rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, start, PROBE_END)
            if rates is not None and len(rates):
                times = pd.to_datetime(pd.Series(rates["time"]), unit="s")
                delta = times.diff()
                n_gaps = int((delta > pd.Timedelta(minutes=5)).sum())
                weekendish = int((delta > pd.Timedelta(hours=12)).sum())

        payload = {
            "status": "ok" if (ok or monthly_ok) else "no_bars",
            "server": server,
            "maxbars": maxbars,
            "probe_end_exclusive_of_existing_start": str(PROBE_END),
            "existing_m5_start": str(EXISTING_M5_START),
            "by_year": by_year,
            "monthly_batches": monthly,
            "n_monthly_windows_with_bars": len(monthly_ok),
            "earliest_available": earliest,
            "latest_in_probe": latest,
            "deepest_request": deepest,
            "gaps_gt_5min_in_2026_year_request": n_gaps,
            "gaps_gt_12h_in_2026_year_request": weekendish,
            "large_range_batching": batch,
            "copy_rates_range_appears_capped_at_50k": batch["sum"] == 50000,
            "history_limit_hit": bool(maxbars and deepest and deepest["n"] >= maxbars),
            "older_history_retrievable_in_batches": bool(monthly_ok) and (
                any(r["year"] < 2026 for r in monthly_ok) or any(r["n"] == 0 for r in by_year)
            ),
            "orders_sent": 0,
        }
    finally:
        mt5.shutdown()

    save(reports_dir() / "m5_history_depth_probe.json",
         wrap("m5_history_depth_probe", "exploratory",
              {"end": str(PROBE_END), "no_src_data_written": True}, payload, DEFAULT_SEED))
    print(payload["status"], "earliest", payload.get("earliest_available"),
          "latest", payload.get("latest_in_probe"), "maxbars", payload.get("maxbars"))
    if payload.get("deepest_request"):
        print("deepest n", payload["deepest_request"]["n"], "from", payload["deepest_request"]["start_year"])
    return payload


def main() -> None:
    run()


if __name__ == "__main__":
    main()
