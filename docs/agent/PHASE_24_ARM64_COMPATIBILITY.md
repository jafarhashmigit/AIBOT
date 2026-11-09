# Phase 24 — ARM64 / Linux aarch64 Compatibility

**Recipe:** `phase24_provider_arm64_qualification_v1`  
**Overall status:** **`COMPATIBLE_IF_MT5_EXCLUDED`** (metadata evidence; **no packages installed**)

## Scope

Inspect pinned `requirements.txt` runtime dependencies for **Linux aarch64 / cp312** wheel availability via **PyPI JSON metadata**.  
Do **not** install or upgrade anything. Do **not** modify the existing Windows venv.

## Python target

| Item | Guidance |
|------|----------|
| Cloud target | CPython **3.12.x** on Linux aarch64 (matches available `cp312` manylinux wheels) |
| Audit host | May be Windows x64 — host ≠ target |

## Pinned runtime results (PyPI metadata)

| Package | Pin | Linux aarch64 (cp312 manylinux) | Notes |
|---------|-----|----------------------------------|-------|
| numpy | 2.5.4 | **Available** | e.g. `manylinux_2_27_aarch64.manylinux_2_28_aarch64` |
| pandas | 3.1.1 | **Available** | manylinux aarch64 wheel present |
| scipy | 1.18.1 | **Available** | manylinux aarch64 wheel present |
| scikit-learn | 1.9.1 | **Available** | manylinux aarch64 wheel present |
| joblib | 1.6.0 | **Pure / any** | `py3-none-any` class wheels |
| tzdata | 2026.6 | **Pure / any** | data package |
| **MetaTrader5** | 5.0.6231 | **Not available** | **win_amd64 wheels only**; platform Windows |

## Windows-only dependency

**`MetaTrader5`** must be omitted from any cloud image.

Cloud runtime must:

1. Never `import MetaTrader5`  
2. Never call `phase16a.mt5_reader.open_readonly`  
3. Supply market data via `MarketDataProvider` / Phase 20–22 `bar_source` injection  

Existing decision code (`predict_h13c_experimental`, journals, Discord client) does not require MT5 when bars are injected.

## Residual risks

- Metadata ≠ runtime smoke test on real Ampere A1 hardware (deferred; no OCI this phase).  
- Exact manylinux glibc version on Oracle Linux must still be checked at first bootstrap.  
- `requirements.txt` still lists MetaTrader5 — cloud install manifests must use an MT5-free subset (future phase; not edited here).

## Safety

- Packages installed this phase: **none**  
- Environment modified: **no**  
- Champion / H13_C / WAIT / holdout / Discord / MT5 connection: unchanged invariants
