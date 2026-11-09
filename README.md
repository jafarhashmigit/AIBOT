# AIBOT

Research and **shadow-observation** system for XAUUSD (gold) M5 decisioning.

**Current production posture**

| Item | Status |
|------|--------|
| Champion model | `NO_MODEL` |
| H13_C candidate | `EXPERIMENTAL` (not production) |
| Production `final_action` | `WAIT` |
| Live broker orders | **Disabled** by design |

This repository is for offline research, walk-forward validation, and optional read-only MetaTrader 5 / Discord **shadow** observation. It does **not** claim a proven live trading edge and must not be treated as an automated money-making bot.

---

## Requirements

### System

| Requirement | Notes |
|-------------|--------|
| **OS** | Windows 10/11 recommended for MetaTrader 5 |
| **Python** | **3.12.x** (project pinned around 3.12.10) |
| **RAM** | 8 GB+ recommended for feature/outcome workflows |
| **Disk** | Space for approved research CSVs under `src/data/` (not in git) |
| **MetaTrader 5** | Optional; required only for live/read-only shadow phases (20/22) |
| **Discord webhook** | Optional; required only for live Discord delivery tests |

### Python packages (core)

Install from the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python tools\verify_requirements.py
```

Core pins (`requirements.txt`):

- `numpy`, `pandas`, `scikit-learn`, `scipy`, `joblib`, `tzdata`
- `MetaTrader5` (Windows; used for read-only market data probes)

Optional:

- `requirements-research.txt` — Kronos / torch research only (not needed for Phase 14–25 core flows)
- `requirements-legacy.txt` — legacy packages not used by the current pipeline

### Data (not shipped in git)

`.gitignore` excludes `src/data/`, `reports/`, and model binaries. You need the approved local research artifacts already used by this project, for example:

- `src/data/xauusd_m5_features_utc_corrected.csv`
- `src/data/m5_side_outcomes.csv`
- `src/data/phase2_oos_predictions.csv`
- `src/data/xauusd_h1_mt5.csv`

**Do not open** the final holdout file `src/data/xauusd_m5_test.csv` for research. Research cutoff is `2026-09-29 18:50:00` UTC.

### Secrets

```powershell
copy .env.example .env
```

Edit `.env`:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Never commit `.env`. Rotate the webhook if it was ever exposed.

---

## Repository layout

```text
src/phase2 … phase25/     Research phases (isolated packages)
src/phase14/              Frozen H13_C independent validation
src/phase22/              Extended forward shadow observation loop
src/phase25/              Strategy discovery vs H13_C (NO_NEW_EDGE_FOUND)
docs/agent/               Phase plans and results
reports/                  Generated JSON reports (local only; gitignored)
requirements.txt          Core runtime dependencies
```

---

## How to run

Always run from the repo root with the venv activated, and put `src` on `PYTHONPATH` (most runners already add it):

```powershell
cd C:\path\to\AIBOT
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
```

### 1) Offline unit / integrity checks (safe default)

```powershell
python -m unittest phase25.tests.test_phase25 -v
python -m unittest phase14.tests.test_phase14 -v
python -m unittest phase22.tests.test_phase22 -v
```

### 2) Phase 14 — frozen H13_C validation (offline)

Requires approved CSVs under `src/data/`.

```powershell
python -m phase14.run_phase14
```

Expected posture after a successful historical validation: H13_C remains **EXPERIMENTAL**, champion **NO_MODEL**.

### 3) Phase 25 — strategy discovery vs H13_C (offline)

```powershell
python -m phase25.run_phase25
```

Writes docs under `docs/agent/` and machine-readable reports under `reports/phase25/` (local). Latest research verdict: **`NO_NEW_EDGE_FOUND`**.

### 4) Phase 22 — forward shadow observation (MT5 read-only)

**Readiness / status only** (no MT5 session, no Discord):

```powershell
python src\phase22\run_phase22.py
python src\phase22\run_phase22.py --campaign-status
```

**Bounded shadow session** (starts a read-only MT5 connection when configured; still production `WAIT`):

```powershell
python src\phase22\run_phase22.py --run-bounded --max-candles 100
```

**Optional Discord live messages** (requires `.env` webhook; still no broker orders):

```powershell
python src\phase22\run_phase22.py --run-bounded --max-candles 100 --discord-live
```

### 5) Discord dry-run (Phase 16B)

```powershell
python src\phase16b\run_phase16b.py --dry-run
```

---

## What “running the AI bot” means here

1. **Offline research** loads approved historical features/outcomes and scores strategies (Phases 2–14, 25).
2. **Shadow observation** reads live/closed M5 bars (optional MT5), applies frozen H13_C experimental rules, then **RiskGate / ForwardGate** keep production action at **`WAIT`**.
3. Optional Discord posts are **notifications / shadow journals**, not trade execution.
4. There is **no supported path** in this repo that places MT5 buy/sell orders as a champion strategy.

If experimental BUY/SELL conditions appear in journals, they are research signals only until a future phase explicitly authorizes controlled paper/live trading (currently **not** authorized).

---

## Safety rules

- Do not open or train on the holdout test set.
- Do not install packages unless you intend to (prefer the pinned `requirements.txt`).
- Do not loosen frozen H13_C WF3 thresholds to force trades.
- Do not bypass ForwardGate / RiskGate / production `WAIT`.
- Do not commit secrets, credentials, or large market datasets.

---

## Branch

Primary working branch for this snapshot: **`dev`**.

Phase research docs: `docs/agent/PHASE_*`.
Start with `docs/agent/PHASE_25_RESULTS.md` and `docs/agent/PHASE_22_EXTENDED_FORWARD_OBSERVATION.md` for the latest operational posture.

---

## Disclaimer

Trading FX/metals involves substantial risk of loss. Past research metrics are not a guarantee of future results. Use this codebase for research and controlled observation only.
