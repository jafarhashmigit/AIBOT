"""Phase 26 runner — orthogonal features & richer outcomes (offline)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phase26.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_STATUS,
    HORIZONS,
    ORTHOGONAL_CANDIDATES,
    PHASE25_VERDICT,
    PREDICT_TARGETS,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REDUNDANCY_CORR_MAX,
    RESEARCH_CUTOFF_UTC,
    SKIPPED_FAMILIES,
)
from phase26.data import load_decision_times, load_h1_bars, load_m5_bars
from phase26.evaluate import decide_verdict, outcome_quality_summary, write_reports
from phase26.features import FEATURE_FORMULAS, compute_orthogonal_features
from phase26.integrity import safety_audit
from phase26.outcomes import build_rich_outcomes
from phase26.predict import walk_forward_predict
from phase26.redundancy import analyze_redundancy


def write_docs(
    *,
    preflight: dict,
    redundancy: dict,
    outcome_quality: dict,
    walk_forward: dict,
    safety: dict,
    verdict: dict,
) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    plan = DOCS_DIR / "PHASE_26_RESEARCH_PLAN.md"
    results = DOCS_DIR / "PHASE_26_RESULTS.md"

    plan_txt = f"""# PHASE 26 — Research Plan (predeclared)

Recipe: `{RECIPE_ID}`

## Objective

Investigate whether orthogonal features and richer outcome labels add incremental *predictive* information beyond the existing approved feature store and net-R labels — without repeating Phase 25 strategies.

Protected posture must remain: champion `{CHAMPION_STATUS}`, H13_C `{H13C_STATUS}`, production `{PRODUCTION_FINAL_ACTION}`, Phase 25 `{PHASE25_VERDICT}`.

## Preflight summary

```json
{json.dumps(preflight, indent=2)}
```

## Existing information already represented

- Trend / EMA geometry: `ema_*`, `close_to_ema_*`, spreads
- Volatility: `atr_14`, `atr_14_pct`, `volatility_12/48`, `volatility_ratio_12_48`, `bb_width`
- Candle anatomy: body/wicks/range ratios
- Short returns/momentum/ROC
- Sessions / clock features
- Outcomes: triple-barrier `net_r` / costs in `m5_side_outcomes.csv` (not MFE/MAE)

## Predeclared orthogonal candidates

| Feature | Formula |
|---------|---------|
""" + "\n".join(f"| `{k}` | {FEATURE_FORMULAS[k]} |" for k in ORTHOGONAL_CANDIDATES) + f"""

Skipped families: `{json.dumps(SKIPPED_FAMILIES)}`

Redundancy gate (predeclared): reject if max |corr| vs baseline ≥ **{REDUNDANCY_CORR_MAX}** on WF1 train cutoff sample.

## Richer outcomes (research labels)

- Entry: next bar **open** after decision close `t`
- Horizons: {list(HORIZONS)} M5 bars
- MFE/MAE in ATR units of decision bar (separate from net R)
- Forward return, forward vol, time-to-fav/adv, fav-before-adv, neither
- Gap/incomplete windows excluded

## Predictive configs (predeclared)

```json
{json.dumps(PREDICT_TARGETS, indent=2)}
```

Models: Ridge (regression), LogisticRegression (classification). Chronological WF1–WF3 with purge={60} minutes. No iterative retuning.

## Experience sources

- `HISTORICAL_HYPOTHETICAL` and `AGENT_SHADOW` remain separate; Phase 26 does not merge them or change production policy.
"""
    plan.write_text(plan_txt + "\n", encoding="utf-8")

    # Results
    lines = [
        "# PHASE 26 — Results",
        "",
        f"Verdict: **{verdict['verdict']}**",
        f"Rationale: {verdict['rationale']}",
        "",
        f"Champion: `{verdict['champion_status']}` | H13_C: `{verdict['h13c_status']}` | Production: `{verdict['production_final_action']}` | Phase25: `{verdict['phase25_verdict_preserved']}`",
        "",
        "## Accepted / rejected features",
        "",
        f"- Accepted ({len(redundancy.get('accepted') or [])}): `{redundancy.get('accepted')}`",
        f"- Rejected ({len(redundancy.get('rejected') or [])}): `{redundancy.get('rejected')}`",
        "",
        "## Outcome quality (decision-time OOS indices)",
        "",
        "```json",
        json.dumps(outcome_quality, indent=2),
        "```",
        "",
        "## Walk-forward predictive results",
        "",
    ]
    for tid, block in walk_forward.items():
        lines.append(f"### `{tid}` ({block['kind']})")
        lines.append(f"- Folds improved: {block['n_folds_improved']} / 3; all folds: {block['all_folds_improved']}")
        for fid, fb in block["folds"].items():
            b = fb.get("baseline", {})
            o = fb.get("baseline_plus_orthogonal", {})
            lines.append(
                f"- {fid}: n_test_base={b.get('n')} baseline={ {k:b.get(k) for k in ('mae','r2','log_loss','accuracy','brier') if k in b} } "
                f"| ortho={ {k:o.get(k) for k in ('mae','r2','log_loss','accuracy','brier') if k in o} } "
                f"| improved={fb.get('improved')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Safety verification",
            "",
            "```json",
            json.dumps(safety.get("checks"), indent=2),
            "```",
            "",
            "## Limitations",
            "",
            "- Predictive improvement ≠ trading edge; no strategy promotion from this phase.",
            "- MFE/MAE are not net R after costs.",
            "- VWAP family skipped due to volume validity.",
            "- Single predeclared pass; multiple-testing risk remains for future exploration.",
            "- Incomplete H1 candles never used; H1 features require completed hour.",
            "",
            "## Commands",
            "",
            "```powershell",
            "cd <repo>",
            ".\\.venv\\Scripts\\Activate.ps1",
            "$env:PYTHONPATH='src'",
            "python -m unittest phase26.tests.test_phase26 -v",
            "python -m phase26.run_phase26",
            "```",
            "",
        ]
    )
    results.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    print("PHASE26 preflight…")
    assert PRODUCTION_FINAL_ACTION == "WAIT"
    assert CHAMPION_STATUS == "NO_MODEL"
    assert PHASE25_VERDICT == "NO_NEW_EDGE_FOUND"

    m5 = load_m5_bars()
    h1 = load_h1_bars()
    decision_times = load_decision_times()
    safety = safety_audit(m5, PROJECT_ROOT)
    preflight = {
        "research_cutoff_utc": RESEARCH_CUTOFF_UTC,
        "n_m5_bars": len(m5["times"]),
        "n_h1_bars": len(h1),
        "n_decision_times_in_wf": len(decision_times),
        "first_m5": m5["times"][0] if m5["times"] else None,
        "last_m5": m5["times"][-1] if m5["times"] else None,
        "holdout_opened": m5["holdout_opened"],
        "safety_all_pass": safety["checks"]["all_pass"],
        "orthogonal_candidates": list(ORTHOGONAL_CANDIDATES),
    }
    print(json.dumps(preflight, indent=2))
    if not safety["checks"]["all_pass"]:
        print("SAFETY FAIL", json.dumps(safety["checks"], indent=2))
        return 2

    print("Computing orthogonal features…")
    feats = compute_orthogonal_features(m5, h1)
    print("Building richer outcomes…")
    outcomes = build_rich_outcomes(feats, len(m5["times"]))
    print("Redundancy analysis…")
    redundancy = analyze_redundancy(m5, feats)
    print("accepted", redundancy["accepted"])
    print("rejected", redundancy["rejected"])

    # map decision times -> indices
    decision_indices = []
    missing = 0
    for t in decision_times:
        i = m5["index"].get(t)
        if i is None:
            missing += 1
            continue
        decision_indices.append(i)
    preflight["decision_index_missing"] = missing

    outcome_quality = outcome_quality_summary(outcomes, decision_indices)
    print("Walk-forward prediction…")
    wf = walk_forward_predict(
        m5, feats, outcomes, redundancy["accepted"], decision_indices
    )
    verdict = decide_verdict(redundancy, wf)
    paths = write_reports(
        redundancy=redundancy,
        outcome_quality=outcome_quality,
        walk_forward=wf,
        safety=safety,
        verdict=verdict,
        preflight=preflight,
    )
    write_docs(
        preflight=preflight,
        redundancy=redundancy,
        outcome_quality=outcome_quality,
        walk_forward=wf,
        safety=safety,
        verdict=verdict,
    )
    print("VERDICT", verdict["verdict"])
    print("reports", paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
