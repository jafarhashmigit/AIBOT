"""Download XAUUSD H1 history for the EMA-pullback research (new file only).

Read-only MT5 history request (copy_rates_range) from the same terminal as xauusd_m5.csv;
no trading calls. The request ends before the research cutoff (last M5 validation bar + 12
bars, inside the purge gap before the M5 test split): the last H1 bar kept is the one whose
whole hour ends at or before the cutoff, so no bar containing test-period prices is ever
retrieved or stored. The XAUUSD M5 test CSV is never opened.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
VALIDATION_PATH = DATA_DIR / "xauusd_m5_validation.csv"
H1_PATH = DATA_DIR / "xauusd_h1_mt5.csv"

MT5_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
SYMBOL = "XAUUSD"
START = datetime(2018, 1, 1, tzinfo=timezone.utc)
PURGE_BARS, BAR_MINUTES = 12, 5
H1 = pd.Timedelta(hours=1)
M5 = pd.Timedelta(minutes=BAR_MINUTES)


def research_cutoff() -> pd.Timestamp:
    val = pd.read_csv(VALIDATION_PATH, usecols=["time"])
    return pd.to_datetime(val["time"].iloc[-1]) + PURGE_BARS * M5


def main() -> None:
    import MetaTrader5 as mt5

    if H1_PATH.exists():
        raise SystemExit(f"Refusing to overwrite existing file {H1_PATH}")
    cutoff = research_cutoff()
    # Last H1 bar whose final M5 sub-bar is <= cutoff opens at last_open.
    last_open = (cutoff + M5 - H1).floor("h")
    if not mt5.initialize(path=MT5_TERMINAL, timeout=60000):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        server = mt5.account_info().server
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"{SYMBOL} not available on {server}")
        # Timezone-aware UTC datetimes make MT5 compare against its stored bar times unchanged.
        end = last_open.to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(minutes=55)
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_H1, START, end)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"no H1 history: {mt5.last_error()}")
    finally:
        mt5.shutdown()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df[df["time"] <= last_open].reset_index(drop=True)
    assert df["time"].is_unique and df["time"].is_monotonic_increasing
    assert df["time"].max() + H1 <= cutoff + M5, "an H1 bar extends past the research cutoff"
    df = df[["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]
    df.to_csv(H1_PATH, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"Saved {H1_PATH}: {len(df)} H1 bars {df['time'].min()} -> {df['time'].max()} from MT5 {server}")
    print(f"Research cutoff {cutoff}; last H1 bar ends {df['time'].max() + H1} (no later data requested or stored)")


if __name__ == "__main__":
    main()
