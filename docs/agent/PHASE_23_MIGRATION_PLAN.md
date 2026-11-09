# Phase 23 — Cloud Migration Plan

**Recipe:** `phase23_cloud_architecture_design_v1`  
**Mode:** DESIGN ONLY  
**Status:** Ready as a plan; **execution gated** by provider qualification.

## Safety invariants (every stage)

- Champion = `NO_MODEL`
- H13_C = `EXPERIMENTAL`
- Production `final_action` = `WAIT`
- No broker connections / orders / live execution
- Frozen WF3 thresholds unchanged
- No final holdout access
- Phase 19 synthetic isolated
- AGENT_SHADOW ≠ HISTORICAL_HYPOTHETICAL
- Discord never described as validated trading signals
- Invalid/stale/missing data blocks decisions
- No duplicate decisions for duplicate candles
- Restart does not replay processed candles
- Phase 22 campaign checkpoints remain recoverable
- No paid OCI resources without explicit operator approval

## Stage overview

| Stage | Name | Exit criteria | Rollback |
|-------|------|---------------|----------|
| A | Provider qualification | Q1–Q12 pass + written parity report | Discard adapter config; keep local MT5 Phase 22 |
| B | ARM64 compatibility audit | Deps install dry-run on aarch64; MetaTrader5 excluded | Stay on Windows venv; no cloud promote |
| C | Cloud deployment preparation | OCI Always Free VM + secrets + systemd unit drafted | Destroy VM; revoke secrets; no data loss locally |
| D | Offline cloud validation | Synthetic/provider-recorded fixtures through pipeline | Wipe cloud data root; restore from backup |
| E | Bounded shadow pilot | Explicit ≤ N candles; Discord optional dry-run | Stop service; revert to Phase 22 local campaign |
| F | Extended observation | Campaign resume toward 1000 candles on cloud data root | Freeze cloud writes; continue/resume local Phase 22 if needed |

---

## Stage A — Provider qualification

**Actions (future; not Phase 23):** account only if free; fetch documented samples; measure UTC, completeness, spread, rate limits; run MT5↔provider parity on overlapping windows.

**Pass:** All Q1–Q12; parity deltas within pre-registered tolerances (to be defined in qualification harness — **not** threshold recalibration).

**Rollback:** Delete provider credentials; mark provider FAIL in assessment; continue local Phase 22.

---

## Stage B — ARM64 compatibility audit

**Actions:** On a disposable aarch64 environment (or future OCI VM), verify wheels for `numpy`, `pandas`, `scipy`, `scikit-learn`, `joblib`, `tzdata`. Confirm **MetaTrader5 is not installed**. Confirm pure-Python path: `predict_h13c_experimental` + phase18 barrier import.

**Risks:** Pinned Windows x64 wheels may lack matching aarch64 builds for exact pins; may need same-major ARM wheels after explicit approval (Phase 23 forbids installs now).

**Rollback:** Do not proceed to Stage C; keep Windows runtime.

---

## Stage C — Cloud deployment preparation

**Actions:**

1. OCI Always Free `VM.Standard.A1.Flex` 2 OCPU / 12 GB, UTC, SSH restricted.
2. Clone/copy repo **without** secrets; place `DISCORD_WEBHOOK_URL` / provider key in `/etc/aibot/secrets.env`.
3. systemd unit with `Restart=on-failure`, `WorkingDirectory`, durable data directory on block volume.
4. Firewall: egress HTTPS only; no open app ports.
5. Backup policy for data root + campaign_state.

**Rollback:** Terminate instance; rotate webhook if exposed; local Phase 22 untouched.

---

## Stage D — Offline cloud validation

**Actions:** Replay recorded completed M5/H1 fixtures through injectable `bar_source` (existing Phase 20/22 seam). Assert WAIT production, no Discord unless dry-run, no broker, campaign/idempotency, health-block on stale feed.

**Rollback:** Delete cloud `src/data/phase22` (or cloud data root); restore empty scaffold from backup.

---

## Stage E — Bounded shadow pilot

**Actions:** Explicit command equivalent to Phase 22 `--run-bounded --max-candles N` using qualified provider. Prefer Discord dry-run first; live Discord only with explicit flag.

**Rollback:** Stop systemd service; leave campaign_state; optionally copy journals back to operator PC; resume local MT5 Phase 22 from its **own** data root (do not merge casually).

---

## Stage F — Extended observation

**Actions:** Multiple explicit sessions toward 1000-candle observation target; cumulative reports comparing Phase 21 historical reachability vs forward frequencies vs outcomes — without significance/profit claims.

**Rollback:** Pause sessions; snapshot volume; if provider fails health checks, freeze decisions and alert operator.

---

## Data migration rules

| Source | Rule |
|--------|------|
| Phase 20 `src/data/phase20` | **Do not overwrite**; cloud uses separate root |
| Phase 22 `src/data/phase22` | Prefer copy-forward of campaign_state only with operator intent; never silent merge |
| Phase 19 synthetic | Never copy into cloud production journal |
| HISTORICAL_HYPOTHETICAL | Optional separate import; never into AGENT_SHADOW |

---

## Monitoring checklist

- Provider health (last successful completed bar age)
- Campaign remaining candles
- PENDING outcome backlog
- Disk usage on boot/block volume
- systemd restart count
- Discord delivery failures (no secret leakage)
- Idle-instance reclaim risk (keep process active)

---

## Explicit Phase 23 non-execution

This document is not authorization to run Stages A–F. Phase 23 produced design artifacts and offline validation only.
