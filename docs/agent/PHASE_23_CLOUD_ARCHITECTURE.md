# Phase 23 — Fully Cloud AIBOT Architecture Design

**Recipe:** `phase23_cloud_architecture_design_v1`  
**Branch:** `cursor/phase23-cloud-architecture`  
**Mode:** DESIGN ONLY — no cloud deployment, no provider accounts, no MT5, no Discord sends  
**Final status:** `CLOUD_ARCHITECTURE_READY_WITH_PROVIDER_BLOCKER`

No trading-edge or profitability claims.

## 1. Verified repository baseline (code audit)

Audit inspected actual modules under `src/phase16a`–`src/phase22` (not docs alone).

| Component | Verified coupling | Cloud implication |
|-----------|-------------------|-------------------|
| `phase16a/mt5_reader.py` | `MetaTrader5` + Windows `terminal64.exe` | **Must be replaced** by `MarketDataProvider` |
| `phase16a/predictor.py` | Pure inputs (`m5_closes`, `h1_rows`) → `decide_h13c` + `ForwardGateAdapter` | **Reusable as-is** |
| `phase16a/constants.py` | Frozen WF3 `FROZEN_CUTS` | **Immutable** in cloud |
| `phase16b/secrets.py` | `DISCORD_WEBHOOK_URL` from env / `.env` | Cloud: env/secret file only; never Git |
| `phase18/store.py` + `experience.py` | CSV/JSONL under store root; AGENT_SHADOW vs HISTORICAL_HYPOTHETICAL | Persist on block volume |
| `phase19` | `PHASE19_SYNTHETIC_TEST` namespace isolation | Keep offline-only / separate path |
| `phase20/candles.py` | Complete-bar guard (`as_of > close`) | Reuse for provider bars |
| `phase20/loop.py` / `phase22/loop.py` | Already accept injectable `bar_source` | Primary migration seam |
| `phase22/campaign.py` | `campaign_state.json` resume; never resets | Mount durable volume |

**Hard MT5 call sites (must not run in cloud):**  
`phase16a/mt5_reader.py`, `phase16a/session.py`, `phase17/loop.py`, `phase18/loop.py`, `phase20/loop.py` (when `bar_source is None`), `phase22/loop.py` (same).

**Already cloud-friendly:** `predict_h13c_experimental`, phase16b Discord HTTP client, phase18 outcomes/experience, phase20 candle validators, phase22 campaign store.

### Frozen WF3 cuts (unchanged)

| Key | Value |
|-----|-------|
| `q_low` / `q_high` | 25 / 75 |
| `close_ema_low` | `-0.0010069324198160867` |
| `close_ema_high` | `0.0009989244530461683` |
| Source | Phase 14 WF3 train (`phase14_replication.json:cuts_independent.WF3`) |

### Safety gates already in code

- Champion `NO_MODEL` → production `final_action=WAIT` (`ForwardGateAdapter` + loop hard fails)
- No broker order APIs; MT5 allowlist; `BROKER_ORDERS=0`
- Session lock; incomplete/duplicate candle rejection
- Discord dedupe ledger; journal-before-send; secret redaction
- Experience source separation; Phase 19 synthetic isolation
- Phase 22 protected SHA256 hashes over Phase 16A–21 artifacts

---

## 2. Target architecture (independent components)

```text
                    ┌─────────────────────────────────────────┐
                    │  systemd (aibot-shadow.service)         │
                    │  healthcheck + auto-restart             │
                    └──────────────────┬──────────────────────┘
                                       │
┌──────────────────────┐   ┌───────────▼────────────┐   ┌─────────────────────┐
│ MarketDataProvider   │──▶│ CandleBuilder/Validator│──▶│ Observation Pipeline│
│ (HTTP/WS adapter)    │   │ UTC normalize, M5 OHLC │   │ predict_h13c_*      │
│ health monitor       │   │ dup/gap detection      │   │ RiskGate → WAIT     │
└──────────────────────┘   └────────────────────────┘   └──────────┬──────────┘
                                                                   │
                     ┌─────────────────────────────────────────────┼──────────┐
                     ▼                                             ▼          ▼
            Persistent journal                          Experience stores   Discord
            (obs/dec/outcomes)                          AGENT_SHADOW /      adapter
            Phase22 campaign_state                      HISTORICAL_*        (opt-in)
```

### Component contracts (design)

1. **`MarketDataProvider`** — `fetch_completed_m5(count|since)`, `fetch_completed_h1(...)`, `health()`, `server_time_utc()`. No MT5 types.
2. **Independent XAUUSD adapter** — one concrete provider behind the interface (selected only after qualification).
3. **UTC timestamp normalization** — convert provider stamps → `YYYY-MM-DD HH:MM:SS` UTC; reject ambiguous TZ.
4. **M5 candle builder/validator** — reuse `phase20.candles.is_complete_m5_bar` semantics; 5-minute boundaries on UTC.
5. **Duplicate / missing detection** — observation ID idempotency (existing store) + gap flag via `phase12.bar_validator.gap_status`.
6. **Market-data health monitor** — stale feed, auth failure, rate-limit, clock skew → **block decisions**.
7. **Observation / prediction pipeline** — existing `predict_h13c_experimental` unchanged.
8. **RiskGate / WAIT-only** — existing `ForwardGateAdapter`; production remains WAIT.
9. **Persistent journals** — `Phase18Store` layout under `src/data/phase22` (or cloud data root).
10. **Experience stores** — separate JSONL files; never mix with Phase 19 synthetic.
11. **Discord adapter** — existing phase16b/20 message builders; disclaimer required; BUY/SELL only.
12. **Supervisor** — systemd unit, restart on failure, lock file, campaign resume.

**MT5 must not be required at runtime** on the cloud VM.

---

## 3. Recommended Oracle Cloud Always Free VM

Verified against Oracle Always Free docs (as of late 2026): Ampere A1 total **2 OCPU + 12 GB RAM**; **200 GB** block storage family; home-region only.

| Setting | Recommendation |
|---------|----------------|
| Shape | `VM.Standard.A1.Flex` |
| OCPUs | **2** (single VM; avoid idle dual-VM reclamation complexity) |
| Memory | **12 GB** |
| Boot volume | **50–100 GB** (counts against 200 GB Always Free) |
| OS | Oracle Linux 8/9 **aarch64** or Ubuntu 22.04/24.04 **arm64** |
| Clock | NTP/`chronyd` → **UTC** |
| Process | `systemd` user/system unit `aibot-shadow.service` (`Restart=on-failure`) |
| Network | Egress HTTPS only to provider + Discord; no inbound app ports required |
| Firewall | Deny all inbound except SSH from operator IP (or OCI Bastion) |
| Billing | Stay on Always Free limits; do **not** enable paid shapes/egress overage without review |
| Idle risk | Always Free idle reclaim (CPU/net/mem <20% over 7 days) — keep lightweight poll loop alive |

Resource fit: forward path is light (pure-Python features + occasional numpy barrier). 2 OCPU / 12 GB is ample if MetaTrader5 is **not** installed.

---

## 4. Persistence and restart recovery

| Artifact | Path (logical) | Recovery role |
|----------|----------------|---------------|
| Campaign | `campaign_state.json` | Target progress, last bar, counters |
| Observations / decisions / outcomes | Phase18 CSV set | Idempotent append; duplicate candle skip |
| Bar cache | `bar_cache.jsonl` | Pending outcome resolution |
| Discord ledger | `discord_delivery_ledger.jsonl` | Dedupe SENT |
| Experience | `agent_shadow_*.jsonl`, `historical_*.jsonl` | Source separation |
| Session lock | `session.lock` | Prevent concurrent writers |
| Diagnostics | `observation_diagnostics.*` | Phase 22 journal |

**Restart rules:** resume from `max(store.last_open_utc, campaign.last_bar_open_utc)`; never replay processed opens; resolve PENDING outcomes before new decisions; refuse start if lock held.

**Backup:** OCI block-volume backup (Always Free allows limited backups) + periodic `tar` of data root to Object Storage (Always Free tier) with retention policy.

---

## 5. Security and secret management

| Secret | Storage | Runtime |
|--------|---------|---------|
| `DISCORD_WEBHOOK_URL` | OCI Vault **or** `/etc/aibot/secrets.env` mode `0600`, outside Git | systemd `EnvironmentFile=` |
| Provider API key (if any) | Same secret file / Vault | Env only |
| SSH keys | Operator workstation | No password SSH |

Never commit `.env`. Reuse `phase16b.secrets.redact_secrets` on all reports/logs. Discord messages must retain: **AIBOT SHADOW — NOT A REAL TRADING SIGNAL**.

---

## 6. Data compatibility warning (critical)

Existing H13_C frozen thresholds were fit on **this project's MT5 XAUUSD** history (point size `0.01`, spread floor assumptions, Europe/Athens→UTC normalization historically).

A new provider:

- Does **not** inherit MT5 threshold validity
- Requires separate **parity / distribution** validation (prices, spreads, M5 boundaries, ATR, feature quantiles)
- Must **not** trigger recalibration of H13_C in this phase

Invalid, stale, or missing data **blocks** decisions (no fabricated candles, no daily substitute, no silent stale prices).

---

## 7. Explicit non-goals (this phase)

- No Oracle tenancy creation or connection
- No provider account signup or live API calls from this phase
- No cloud code implementation / deployment
- No Phase 16A–22 source or report mutation
- No threshold / model / holdout changes
- No package installs
- No commits or pushes

---

## 8. Status

Architecture for a MT5-free cloud shadow observer is **designed and validated offline**.

**Provider selection is BLOCKED** pending free-tier qualification + MT5 parity (see `PHASE_23_PROVIDER_ASSESSMENT.md`).

**Final status:** `CLOUD_ARCHITECTURE_READY_WITH_PROVIDER_BLOCKER`
