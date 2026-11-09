# Phase 12 market data

Symbol `XAUUSD`, timeframe `M5`.

Stage A uses `SyntheticReader` only. MT5 is not imported.

Broker `copy_rates` timestamps are server wall-clock (Europe/Athens), not UTC. Conversion is IANA DST via `zoneinfo`, never a fixed offset. Unknown timezones are rejected and are never labeled UTC.

Incomplete candles are rejected. Invalid OHLC is rejected. Duplicates are rejected. Gaps are flagged, never filled.

Forward files live under `src/data/phase12/` and are not appended to historical research CSVs.
