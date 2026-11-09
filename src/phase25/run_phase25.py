"""Phase 25 runner — isolated strategy discovery vs frozen H13_C."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from phase25.audit.offline_audit import build_offline_audit
from phase25.constants import (
    CHAMPION_STATUS,
    DOCS_DIR,
    H13C_STATUS,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    STRATEGY_PARAMS,
)
from phase25.data import fold_counts, load_research_bundle
from phase25.evaluate import evaluate_all, write_reports
from phase25.integrity import verify_safety


def _fmt(x) -> str:
    if x is None:
        return "nan"
    try:
        if x != x:
            return "nan"
        return f"{float(x):.6f}"
    except Exception:
        return str(x)


def write_docs(result: dict, audit: dict, safety: dict, preflight: dict) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    research = DOCS_DIR / "PHASE_25_STRATEGY_RESEARCH.md"
    results = DOCS_DIR / "PHASE_25_RESULTS.md"

    lines = [
        "# PHASE 25 — Strategy Research Plan & Repository Audit",
        "",
        f"Recipe: `{RECIPE_ID}`",
        "",
        "## Scope & Safety",
        "",
        "- Isolated under `src/phase25/`.",
        "- H13_C remains frozen EXPERIMENTAL benchmark.",
        "- Champion remains `NO_MODEL`; production `final_action=WAIT`.",
        "- No holdout access, MT5, Discord, Telegram, OCI, package installs, or git push.",
        "- No autonomous retraining / RL.",
        "",
        "## Predeclared parameters",
        "",
        "```json",
        json.dumps(STRATEGY_PARAMS, indent=2),
        "```",
        "",
        "## Repository audits (source-inspected)",
        "",
    ]
    for repo in audit["repositories"]:
        s = repo["strategy"]
        lines.extend(
            [
                f"### {repo['repo']}",
                "",
                f"- License: **{repo['license']}**",
                f"- Code copied into AIBOT: **{repo['code_copied']}**",
                f"- Strategy: {s['summary']}",
                f"- Entry/exit: {s['entry_exit']}",
                f"- Indicators/TF: {s['indicators_tf']}",
                f"- Regime: {s['regime']}",
                f"- SL/TP/sizing: {s['sl_tp_sizing']}",
                f"- Costs: {s['costs']}",
                f"- Data/deps: {s['data_deps']}",
                f"- Reusable math: {s['reusable_math']}",
                f"- Look-ahead / repaint risks: {s['look_ahead_risks']}",
                f"- Implementation policy: {s['implementation_policy']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Independent hypotheses implemented",
            "",
            "1. `mean_reversion` — Z-score + RSI + ATR/vol filters",
            "2. `breakout_retest` — Donchian break + retest + false-break filter",
            "3. `smc_liquidity` — liquidity sweep + BOS/CHoCH + FVG (closed-bar)",
            "4. `regime_router` — past-only trending/ranging/high-vol routing",
            "5. `mtf_h1_m5` — H1 bias + M5 RSI/EMA confirmation (not H13_C cuts)",
            "",
            "## Evaluation contract",
            "",
            "- Same approved features/outcomes/H1 as Phase 14.",
            "- Same WF1–WF3 windows, purge/embargo, day-cluster bootstrap.",
            "- Identical outcome costs (spread/commission/slippage embedded in `m5_side_outcomes`).",
            "- Single confirmatory pass; no iterative retuning on validation.",
            "",
            "## Preflight",
            "",
            "```json",
            json.dumps(preflight, indent=2, default=str),
            "```",
            "",
        ]
    )
    research.write_text("\n".join(lines) + "\n", encoding="utf-8")

    h = result["h13c_benchmark"]["score"]["pooled"]
    rlines = [
        "# PHASE 25 — Results",
        "",
        f"Created: `{result['created_at_utc']}`",
        f"Phase verdict: **{result['phase_verdict']}**",
        f"Champion: `{result['champion_status']}` | H13_C: `{result['h13c_status']}` | Production: `{result['production_final_action']}`",
        "",
        "## Comparative table (pooled, after costs)",
        "",
        "| Strategy | Status | N | Mean R | Net R | PF | Win% | Max DD$ | CI low | CI high |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| H13_C (benchmark) | EXPERIMENTAL | {h['n']} | {_fmt(h['mean_r'])} | {_fmt(h['net_r'])} | "
            f"{_fmt(h['profit_factor'])} | {_fmt(h['win_rate'])} | {_fmt(h['max_drawdown_usd'])} | "
            f"{_fmt(h['bootstrap']['ci_low'])} | {_fmt(h['bootstrap']['ci_high'])} |"
        ),
    ]
    for sid, block in result["strategies"].items():
        p = block["score"]["pooled"]
        st = block["decision"]["status"]
        rlines.append(
            f"| {sid} | {st} | {p['n']} | {_fmt(p['mean_r'])} | {_fmt(p['net_r'])} | "
            f"{_fmt(p['profit_factor'])} | {_fmt(p['win_rate'])} | {_fmt(p['max_drawdown_usd'])} | "
            f"{_fmt(p['bootstrap']['ci_low'])} | {_fmt(p['bootstrap']['ci_high'])} |"
        )

    rlines.extend(["", "## Per-strategy decisions", ""])
    for sid, block in result["strategies"].items():
        d = block["decision"]
        vs = block["vs_h13c"]
        folds = block["score"]["folds"]
        rlines.extend(
            [
                f"### {sid}",
                "",
                f"- Status: **{d['status']}**",
                f"- Rationale: {d['rationale']}",
                f"- Signals/trades: {block['n_signals']}/{block['n_trades']} (BUY {block['n_buy']} / SELL {block['n_sell']})",
                f"- Δ mean R vs H13_C: {_fmt(vs['delta_mean_r'])}",
                f"- WF1 mean R (n={folds['WF1']['n']}): {_fmt(folds['WF1']['mean_r'])}",
                f"- WF2 mean R (n={folds['WF2']['n']}): {_fmt(folds['WF2']['mean_r'])}",
                f"- WF3 mean R (n={folds['WF3']['n']}): {_fmt(folds['WF3']['mean_r'])}",
                f"- Cost 1.5x mean R: {_fmt(block['cost_robustness'].get('1.5x', {}).get('mean_r'))}",
                f"- Gates: `{json.dumps(d['gates'])}`",
                "",
            ]
        )

    rlines.extend(
        [
            "## Rejected / inconclusive hypotheses",
            "",
        ]
    )
    for sid, block in result["strategies"].items():
        if block["decision"]["status"] in {"REJECTED", "INCONCLUSIVE", "PROMISING_BUT_UNCONFIRMED"}:
            rlines.append(
                f"- `{sid}` → {block['decision']['status']}: {block['decision']['rationale']}"
            )

    rlines.extend(
        [
            "",
            "## Data integrity & safety",
            "",
            "```json",
            json.dumps(safety, indent=2),
            "```",
            "",
            "## Multiple-testing note",
            "",
            result["multiple_testing_note"],
            "",
            "## Recommended next research step",
            "",
        ]
    )
    if result["phase_verdict"] == "NO_NEW_EDGE_FOUND":
        rlines.append(
            "Preserve champion `NO_MODEL`, H13_C `EXPERIMENTAL`, production `WAIT`. "
            "Next research should explore orthogonal features/labels or longer out-of-sample observation — "
            "not promote any Phase 25 strategy to production."
        )
    else:
        rlines.append(
            "Any `CANDIDATE_FOR_FUTURE_SHADOW_TEST` may enter a future gated shadow observation only; "
            "still not production-ready and must not bypass ForwardGate/RiskGate/WAIT controls."
        )

    rlines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- `{REPORTS_DIR / 'phase25_summary.json'}`",
            f"- `{REPORTS_DIR / 'comparative_results.json'}`",
            f"- `{REPORTS_DIR / 'strategy_decisions.json'}`",
            f"- `{REPORTS_DIR / 'repo_audit.json'}`",
            "",
        ]
    )
    results.write_text("\n".join(rlines) + "\n", encoding="utf-8")


def main() -> int:
    print("PHASE25 preflight…")
    assert CHAMPION_STATUS == "NO_MODEL"
    assert H13C_STATUS == "EXPERIMENTAL"
    assert PRODUCTION_FINAL_ACTION == "WAIT"

    print("Building offline repository audit…")
    audit = build_offline_audit()

    print("Loading approved research bundle…")
    bundle = load_research_bundle()
    safety = verify_safety(bundle, PROJECT_ROOT)
    preflight = {
        "n_timestamps": len(bundle["timestamps"]),
        "n_features": len(bundle["feature_times"]),
        "n_outcomes": len(bundle["outcomes"]),
        "bounds": bundle["bounds"],
        "fold_timestamp_counts": fold_counts(bundle["timestamps"]),
        "safety_all_pass": safety["all_pass"],
        "audit_mode": "offline_compiled_from_inspected_public_sources",
        "repos_audited": len(audit["repositories"]),
    }
    print(json.dumps(preflight, indent=2, default=str))
    if not safety["all_pass"]:
        print("SAFETY CHECK FAILED", safety)
        return 2

    print("Evaluating strategies vs frozen H13_C…")
    result = evaluate_all(bundle)
    result["preflight"] = preflight
    result["safety"] = safety
    paths = write_reports(result)
    write_docs(result, audit, safety, preflight)

    print("phase_verdict", result["phase_verdict"])
    for sid, block in result["strategies"].items():
        p = block["score"]["pooled"]
        print(
            f"  {sid}: {block['decision']['status']} n={p['n']} mean_r={_fmt(p['mean_r'])}"
        )
    print("reports", paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
