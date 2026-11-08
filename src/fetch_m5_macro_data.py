"""Download the external data for the macro-feature research (new files only).

* DXY basket: M5 bars of the six ICE US Dollar Index component pairs from the same
  MT5 server as xauusd_m5.csv (verified identical feed and clock), read-only
  history download, no trading calls.
* US Treasury yields: FRED daily constant-maturity DGS2 and DGS10, each series
  requested separately (a combined request misaligns DGS2).

Nothing after the research boundary (last validation bar + 12 bars, inside the
purge gap before the test split) is kept, so no test-period external data is
stored. The XAUUSD test CSV is never opened.
"""

import io
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
VALIDATION_PATH = DATA_DIR / "xauusd_m5_validation.csv"
DXY_BASKET_PATH = DATA_DIR / "external_dxy_basket_m5.csv"
TREASURY_PATH = DATA_DIR / "external_us_treasury_daily.csv"

MT5_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
DXY_PAIRS = ["EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDSEK", "USDCHF"]
FX_START = datetime(2026, 2, 1, tzinfo=timezone.utc)
FRED_SERIES = ["DGS2", "DGS10"]
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
FRED_START = "2025-10-01"
PURGE_BARS, BAR_MINUTES = 12, 5


def research_cutoff() -> pd.Timestamp:
    val = pd.read_csv(VALIDATION_PATH, usecols=["time"])
    return pd.to_datetime(val["time"].iloc[-1]) + pd.Timedelta(minutes=PURGE_BARS * BAR_MINUTES)


def fetch_dxy_basket(cutoff: pd.Timestamp) -> pd.DataFrame:
    import MetaTrader5 as mt5

    if not mt5.initialize(path=MT5_TERMINAL, timeout=60000):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        server = mt5.account_info().server
        # MT5 compares request times with its bar timestamps; timezone-aware UTC
        # datetimes make the request use the same clock as the stored bar times.
        end = cutoff.to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(seconds=1)
        frames = []
        for pair in DXY_PAIRS:
            if not mt5.symbol_select(pair, True):
                raise RuntimeError(f"{pair} not available on {server}")
            rates = mt5.copy_rates_range(pair, mt5.TIMEFRAME_M5, FX_START, end)
            if rates is None or len(rates) == 0:
                raise RuntimeError(f"no M5 history for {pair}: {mt5.last_error()}")
            df = pd.DataFrame(rates)[["time", "close", "tick_volume"]]
            df["time"] = pd.to_datetime(df["time"], unit="s")
            frames.append(df.rename(columns={"close": f"{pair}_close", "tick_volume": f"{pair}_tick_volume"})
                          .set_index("time"))
    finally:
        mt5.shutdown()

    basket = pd.concat(frames, axis=1, join="outer").sort_index()
    basket = basket[basket.index <= cutoff]
    assert basket.index.is_unique and basket.index.is_monotonic_increasing
    basket.insert(0, "source", f"MT5 {server} M5")
    return basket.reset_index()


def fetch_fred(cutoff: pd.Timestamp) -> pd.DataFrame:
    series = []
    for sid in FRED_SERIES:
        with urllib.request.urlopen(FRED_URL.format(sid), timeout=60) as resp:
            df = pd.read_csv(io.StringIO(resp.read().decode("utf-8")))
        df.columns = ["observation_date", sid]
        df["observation_date"] = pd.to_datetime(df["observation_date"])
        df[sid] = pd.to_numeric(df[sid], errors="coerce")
        series.append(df.set_index("observation_date"))
    out = pd.concat(series, axis=1, sort=True)
    out = out[(out.index >= FRED_START) & (out.index <= cutoff.normalize())]
    out["retrieved_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    out["source"] = "FRED " + ",".join(FRED_SERIES) + " (latest vintage)"
    return out.reset_index()


def main() -> None:
    for path in (DXY_BASKET_PATH, TREASURY_PATH):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    cutoff = research_cutoff()

    basket = fetch_dxy_basket(cutoff)
    complete = basket[[f"{p}_close" for p in DXY_PAIRS]].notna().all(axis=1)
    basket.to_csv(DXY_BASKET_PATH, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"Saved {DXY_BASKET_PATH}: {len(basket)} timestamps {basket['time'].min()} -> {basket['time'].max()}, "
          f"{int(complete.sum())} with all six pairs")

    fred = fetch_fred(cutoff)
    fred.to_csv(TREASURY_PATH, index=False, date_format="%Y-%m-%d")
    print(f"Saved {TREASURY_PATH}: {len(fred)} dates {fred['observation_date'].min().date()} -> "
          f"{fred['observation_date'].max().date()}; missing DGS2 {int(fred['DGS2'].isna().sum())}, "
          f"DGS10 {int(fred['DGS10'].isna().sum())}")
    print(f"Research cutoff: {cutoff} (no external data after it was stored)")


if __name__ == "__main__":
    main()
