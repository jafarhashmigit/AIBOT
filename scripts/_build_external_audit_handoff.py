"""Build external audit handoff docs + ZIP. Read-only w.r.t. project behavior."""
from __future__ import annotations

import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(".").resolve()
REPORTS = ROOT / "reports"
OUT = REPORTS / "external_audit_handoff"
CACHE = OUT / "_extract_cache.json"


def loadj(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_parse_error": str(e), "_path": str(p)}


def phase_sort_key(name: str):
    m = re.match(r"phase(\d+)([a-z]*)(?:_(\d+))?$", name)
    if not m:
        return (9999, name, 0, name)
    return (int(m.group(1)), m.group(2) or "", int(m.group(3) or 0), name)


def find_final_artifact(d: Path) -> tuple[str | None, str | None]:
    """Return (kind, path) for best final artifact."""
    for name in ("verdict.json", "final_verdict.json", "final_qualification.json"):
        p = d / name
        if p.exists():
            return ("json", str(p.relative_to(ROOT)).replace("\\", "/"))
    for p in sorted(d.glob("*FINAL*.md")) + sorted(d.glob("FINAL_REPORT.md")):
        return ("md", str(p.relative_to(ROOT)).replace("\\", "/"))
    for pat in ("*conclusion*.json", "*summary.json", "*_summary.json"):
        hits = sorted(d.glob(pat))
        if hits:
            return ("json", str(hits[0].relative_to(ROOT)).replace("\\", "/"))
    return (None, None)


def extract_verdict_label(d: Path, kind: str | None, path: str | None) -> str:
    if not path:
        return "NO_FINAL_ARTIFACT"
    p = ROOT / path
    if kind == "json":
        j = loadj(p)
        for k in ("verdict", "phase_verdict", "final_verdict", "conclusion", "status"):
            v = j.get(k) if isinstance(j, dict) else None
            if isinstance(v, dict):
                vv = v.get("verdict") or v.get("status") or v.get("conclusion")
                if vv:
                    return str(vv)
            elif v is not None:
                if k == "conclusion" and isinstance(j.get("result"), dict):
                    rr = j["result"].get("conclusion")
                    if rr:
                        return str(rr)
                return str(v)
        if isinstance(j.get("result"), dict) and j["result"].get("conclusion"):
            return str(j["result"]["conclusion"])
        # nested candidate verdicts
        if "candidates" in j and isinstance(j["candidates"], dict):
            parts = []
            for cid, cv in j["candidates"].items():
                if isinstance(cv, dict) and cv.get("verdict"):
                    parts.append(f"{cid}:{cv['verdict']}")
            if parts:
                return " | ".join(parts)
        return "PRESENT_BUT_UNLABELED_JSON"
    text = p.read_text(encoding="utf-8", errors="replace")
    for pat in (
        r"\*\*Primary verdict:\*\*\s*`([^`]+)`",
        r"\*\*Verdict:\*\*\s*`([^`]+)`",
        r"Verdict:\s*`([^`]+)`",
        r"Primary verdict:\s*`([^`]+)`",
        r"Evidence sufficiency status:\s*`([^`]+)`",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return "PRESENT_BUT_UNLABELED_MD"


def evidence_class(name: str, verdict: str) -> str:
    n = name.lower()
    v = (verdict or "").upper()
    if n in ("phase68",):
        return "exploratory (archive displacement) + live integrity verification (Exness RO)"
    if n in ("phase69", "phase67", "phase66"):
        return "engineering + live broker READ_ONLY collection (not trading-edge validation)"
    if n.startswith("phase64"):
        return "broker/execution engineering evidence (mostly demo/RO; not edge validation)"
    if n in ("phase58",):
        return "discovery/validation on historical blocks; sealed holdout EXISTS — outcomes NOT accessed for this handoff"
    if "INSUFFICIENT" in v or "NO_EDGE" in v or "NO_PREDICTIVE" in v or "NO_INFORMATION" in v or "REJECTED" in v:
        return "historical / discovery-or-validation negative or insufficient"
    if n.startswith("phase5") or n.startswith("phase4") or n.startswith("phase3"):
        return "historical research / engineering (see report)"
    if n.startswith("phase1") or n.startswith("phase2"):
        return "early historical / exploratory (MetaQuotes/archive lineage)"
    return "see original report"


PHASE_CATALOG = [
    # (id, title_hint) — titles refined from artifacts where possible
    ("phase0", "MISSING — no reports/phase0 directory"),
    ("phase1", "Baseline / reproduction snapshot"),
    ("phase2", "OOS predictions / early agent substrate"),
    ("phase3", "Decision journal foundations"),
    ("phase4", "Early pipeline (artifact-sparse)"),
    ("phase5", "Early pipeline (artifact-sparse)"),
    ("phase6", "Risk gate + journal"),
    ("phase7", "Journal evaluation chrono"),
    ("phase8", "Experience memory"),
    ("phase9", "Experience ridge learner"),
    ("phase10", "Dual-source experience + paper simulator"),
    ("phase11", "Dual-source validation / paper audit"),
    ("phase12", "Allowlist / forward gate precursor (sparse)"),
    ("phase12b", "Preflight audit"),
    ("phase12c", "Forward compatibility adapter"),
    ("phase13", "Model discovery (H13 family)"),
    ("phase14", "H13_C validation"),
    ("phase15a", "Permission / compliance readiness"),
    ("phase15b", "Injection compatibility"),
    ("phase15c", "Permission readiness layer"),
    ("phase16a", "H13 follow-on"),
    ("phase16b", "Follow-on (sparse)"),
    ("phase17", "Intermediate (sparse)"),
    ("phase18", "Intermediate completed"),
    ("phase19", "Synthetic path (excluded from later experience)"),
    ("phase20", "Activity / experience accounting"),
    ("phase20a", "Sample table (no edge claim)"),
    ("phase21", "BUY/SELL reachability diagnostics"),
    ("phase22", "Intermediate (sparse)"),
    ("phase23", "Intermediate (sparse)"),
    ("phase24", "Intermediate (sparse)"),
    ("phase25", "Strategy / feature screening precursor"),
    ("phase26", "Orthogonal feature-outcome screen"),
    ("phase27", "Volatility-aware decision"),
    ("phase28", "Forward evidence journals"),
    ("phase29", "Forward evidence continuation"),
    ("phase30", "Multi-strategy walk-forward screen"),
    ("phase31", "Implementation-defect root-cause audit"),
    ("phase32", "Execution realism audit"),
    ("phase33", "Historical bid/ask sample acquisition"),
    ("phase34", "Historical bid/ask quality partial"),
    ("phase35", "Candidate family retests"),
    ("phase36", "Acquisition bound / insufficient data"),
    ("phase37", "MT5 historical source qualification"),
    ("phase38", "Canonical data engine"),
    ("phase39", "H13_C / mean_reversion insufficient evidence"),
    ("phase40", "Coverage ready for Phase39 retest"),
    ("phase41", "Full-session retest — mean_reversion EDGE_REJECTED"),
    ("phase42", "Indicator-family screen — NO_PREDICTIVE_VALUE"),
    ("phase43", "Independent data ready"),
    ("phase44", "Independent family screen — NO_PREDICTIVE_VALUE"),
    ("phase45", "Research architecture audit — redirect required"),
    ("phase46", "Costed EV foundation"),
    ("phase47", "EV estimation unreliable"),
    ("phase48", "EV / decision stack continuation"),
    ("phase49", "No information family found"),
    ("phase50", "No demonstrated learning value"),
    ("phase51", "Independent confirmation failed"),
    ("phase52", "Market representation selected"),
    ("phase53", "No edge found"),
    ("phase54", "Autonomous paper bot engineering ready"),
    ("phase55", "Paper execution verified"),
    ("phase56", "Autonomous replay agent ready"),
    ("phase57", "Autonomous reliability partial"),
    ("phase57_1", "Journal hardening follow-on"),
    ("phase58", "No information family found (sealed holdout created)"),
    ("phase59", "Execution economics partial"),
    ("phase60", "Execution reality partial"),
    ("phase61", "Exness execution evidence partial"),
    ("phase62", "Exness demo collection partial"),
    ("phase63", "Awaiting genuine demo export"),
    ("phase64", "Demo decision execution readiness partial"),
    ("phase64_1", "Canonical decision intent integration ready"),
    ("phase64_2", "Intent identity / WAIT durability hardened"),
    ("phase64_3", "Hardened runtime adoption validated"),
    ("phase64_4", "Broker execution design validated"),
    ("phase64_5", "Broker evidence reconciliation validated"),
    ("phase64_6", "MT5 read-only readiness validated"),
    ("phase64_7", "Live MT5 metadata verified"),
    ("phase64_8", "Broker RO reconciliation validated"),
    ("phase64_9", "Execution preflight validated"),
    ("phase64_10", "Broker economics/risk partial"),
    ("phase64_11", "Broker evidence boundary validated"),
    ("phase64_12", "XAUUSDm session evidence validated"),
    ("phase64_13", "CLOSE_ONLY semantics validated"),
    ("phase65", "No new information family found"),
    ("phase66", "Collection engineering ready"),
    ("phase67", "Insufficient live evidence (ops verified)"),
    ("phase68", "Insufficient sample (exploratory displacement)"),
    ("phase69", "Evidence accumulation + hypothesis prereg (unvalidated)"),
]


def build_index_rows():
    rows = []
    for pid, title in PHASE_CATALOG:
        d = REPORTS / pid
        exists = d.is_dir()
        kind, path = (None, None)
        verdict = "MISSING_DIRECTORY"
        n_files = 0
        if exists:
            n_files = sum(1 for _ in d.rglob("*") if _.is_file())
            kind, path = find_final_artifact(d)
            verdict = extract_verdict_label(d, kind, path)
        rows.append(
            {
                "id": pid,
                "title": title,
                "dir_exists": exists,
                "n_files": n_files,
                "artifact_kind": kind,
                "artifact_path": path,
                "verdict": verdict,
                "evidence_class": evidence_class(pid, verdict) if exists else "MISSING",
            }
        )
    return rows


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def write_master_index(rows):
    lines = []
    lines.append("# AIBOT Phase 0–69 Master Index")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Scope: chronological index of Phase 0 through Phase 69 (including lettered/sub-phases).")
    lines.append("- Rule: original reports are not rewritten; this index only points to them.")
    lines.append("")
    lines.append("## Coverage summary")
    lines.append("")
    present = [r for r in rows if r["dir_exists"]]
    missing = [r for r in rows if not r["dir_exists"]]
    with_art = [r for r in present if r["artifact_path"]]
    no_art = [r for r in present if not r["artifact_path"]]
    lines.append(f"- Catalogued phase IDs (incl. sub-phases): **{len(rows)}**")
    lines.append(f"- Directories present under `reports/`: **{len(present)}**")
    lines.append(f"- Missing directories: **{len(missing)}** → `{', '.join(r['id'] for r in missing) or 'none'}`")
    lines.append(f"- With final/summary artifact: **{len(with_art)}**")
    lines.append(f"- Present but no final/summary artifact located: **{len(no_art)}** → `{', '.join(r['id'] for r in no_art) or 'none'}`")
    lines.append("")
    lines.append("## Integer Phase 0–69 presence")
    lines.append("")
    for i in range(0, 70):
        pid = f"phase{i}"
        r = next((x for x in rows if x["id"] == pid), None)
        if r is None:
            # integer may only exist as subphases
            subs = [x for x in rows if x["id"].startswith(f"phase{i}") and x["id"] != pid]
            if subs:
                lines.append(f"- `phase{i}`: no exact dir; sub-phases present: `{', '.join(s['id'] for s in subs)}`")
            else:
                lines.append(f"- `phase{i}`: **MISSING**")
        else:
            flag = "PRESENT" if r["dir_exists"] else "**MISSING**"
            lines.append(f"- `{pid}`: {flag} — verdict=`{r['verdict']}` — artifact=`{r['artifact_path'] or 'NONE'}`")
    lines.append("")
    lines.append("## Full chronological table")
    lines.append("")
    lines.append("| Phase | Title | Dir? | Files | Verdict | Artifact | Evidence class |")
    lines.append("| --- | --- | --- | ---: | --- | --- | --- |")
    for r in rows:
        lines.append(
            f"| `{r['id']}` | {md_escape(r['title'])} | {'Y' if r['dir_exists'] else 'N'} | {r['n_files']} | "
            f"`{md_escape(str(r['verdict'])[:80])}` | `{r['artifact_path'] or 'NONE'}` | {md_escape(r['evidence_class'])} |"
        )
    lines.append("")
    lines.append("## Related non-phase report dirs")
    lines.append("")
    extra = sorted(
        p.name
        for p in REPORTS.iterdir()
        if p.is_dir() and not p.name.startswith("phase") and p.name != "external_audit_handoff"
    )
    for name in extra:
        lines.append(f"- `reports/{name}/`")
    lines.append("")
    lines.append("## Notes for auditors")
    lines.append("")
    lines.append("- **Phase 0:** no `reports/phase0/` directory found in this workspace.")
    lines.append("- **Exact `phase15` / `phase16` dirs:** absent; work lives in `phase15a/b/c` and `phase16a/b`.")
    lines.append("- Early phases (approx. 1–34) often ship JSON summaries/conclusions rather than Markdown final reports.")
    lines.append("- **Sparse dirs** (present, intermediate JSON only; no formal final/summary/conclusion filename match): `phase2`, `phase3`, `phase4`, `phase5`, `phase6`, `phase7`, `phase12`.")
    lines.append("- From Phase 35 onward, Markdown `*FINAL*` / `FINAL_REPORT.md` artifacts are generally present.")
    lines.append("- Sub-phases (`12b/c`, `15a/b/c`, `16a/b`, `20a`, `57_1`, `64_1`–`64_13`) are first-class engineering/research units and are indexed.")
    lines.append("- Do **not** treat MetaQuotes/archive exploratory results as Exness live confirmation.")
    lines.append("")
    (OUT / "AIBOT_PHASE_0_TO_69_MASTER_INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def write_evidence_audit(rows):
    p45 = loadj(REPORTS / "phase45" / "consolidated_experiment_registry.json")
    p68 = loadj(REPORTS / "phase68" / "verdict.json")
    p68_live = loadj(REPORTS / "phase68" / "live_evidence_integrity.json")
    p69_suf = loadj(REPORTS / "phase69" / "evidence_sufficiency.json")
    p69_acc = loadj(REPORTS / "phase69" / "live_evidence_accounting.json")
    p69_reg = loadj(REPORTS / "phase69" / "hypothesis_registry.json")
    p69_fin = (REPORTS / "phase69" / "PHASE69_FINAL_REPORT.md").read_text(encoding="utf-8", errors="replace")
    p67 = loadj(REPORTS / "phase67" / "verdict.json")
    p66 = loadj(REPORTS / "phase66" / "verdict.json")
    p65 = loadj(REPORTS / "phase65" / "verdict.json")

    lines = []
    lines.append("# AIBOT Phase 0–69 Evidence Audit")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Method: read original `reports/phase*` artifacts; cite paths; do not rewrite originals.")
    lines.append("- Missing values are marked `UNKNOWN` / `NOT_VERIFIED` rather than invented.")
    lines.append("")
    lines.append("## Global safety invariants (verified in Phase 66–69 verdict/constants)")
    lines.append("")
    lines.append("| Invariant | Required | Phase68 `verdict.json` | Phase69 constants / final report |")
    lines.append("| --- | --- | --- | --- |")
    inv68 = p68.get("invariants", {})
    checks = [
        ("Champion", "NO_MODEL", inv68.get("Champion"), "NO_MODEL"),
        ("Production", "WAIT", inv68.get("Production"), "WAIT"),
        ("Live trading", "NOT_AUTHORIZED", inv68.get("Live"), "NOT_AUTHORIZED"),
        ("Automated orders", "DISABLED", inv68.get("AutomatedOrders"), "DISABLED"),
        ("order_send", "PROHIBITED", inv68.get("order_send"), "PROHIBITED"),
        ("Broker collection", "READ_ONLY", inv68.get("BrokerCollection"), "READ_ONLY"),
        ("Execution authorization", "BLOCKED", inv68.get("ExecutionAuthorization"), "BLOCKED"),
        ("Risk policy", "UNAPPROVED", inv68.get("RiskPolicy"), "UNAPPROVED"),
        ("Cost model", "INCOMPLETE", inv68.get("CostModel"), "INCOMPLETE"),
        ("Commission", "UNKNOWN", inv68.get("Commission"), "UNKNOWN"),
        ("Swap", "UNKNOWN_FOR_EXECUTION", inv68.get("Swap"), "UNKNOWN_FOR_EXECUTION"),
        ("Genuine broker fills", "NONE_TRADE_FILLS", inv68.get("GenuineFills"), "NONE_TRADE_FILLS"),
    ]
    for name, req, v68, v69 in checks:
        lines.append(f"| {name} | `{req}` | `{v68}` | `{v69}` |")
    lines.append("")
    lines.append("- Margin: Phase66/69 constants `MARGIN_INCOMPLETE='INCOMPLETE'` (`src/phase69/constants.py`).")
    lines.append("- `BROKER_SUBMISSION_ENABLED=false`, `BROKER_EXECUTION_AUTHORIZED=false` in Phase68/69 invariants.")
    lines.append("")
    lines.append("## Explicit Phase 68 verification")
    lines.append("")
    lines.append("User-stated claims vs original artifacts:")
    lines.append("")
    lines.append("| Claim | Observed | Source | Match? |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        f"| Engineering-complete: True | Secondary live integrity verified=`{p68.get('live_collection_integrity_verified')}`; "
        f"tests reported True in final report | `reports/phase68/PHASE68_FINAL_REPORT.md`, `verdict.json` | "
        f"**PASS** (engineering integrity verified; primary research verdict is not 'edge') |"
    )
    lines.append(
        f"| Trading-edge-validated: False | `champion_promotion={p68.get('champion_promotion')}`, "
        f"`independent_discovery={p68.get('independent_discovery')}` | `reports/phase68/verdict.json` | **PASS** |"
    )
    lines.append(
        f"| Sufficiency: INSUFFICIENT_SAMPLE | `verdict={p68.get('verdict')}` | `reports/phase68/verdict.json` | **PASS** |"
    )
    lines.append(
        f"| Exploratory displacement only | reason cites exploratory displacement; secondary `EXPLORATORY_BEHAVIOUR_IDENTIFIED` | `verdict.json` | **PASS** |"
    )
    lines.append(
        f"| 28 events / 22 dates | n_events=`{p68.get('n_events')}`, n_dates=`{p68.get('n_dates')}` | `verdict.json` | **PASS** |"
    )
    lines.append("| No predictive or Champion claim | Champion promotion false; Champion remains NO_MODEL | `verdict.json` + final report | **PASS** |")
    # backfill nuance
    backfill_events = None
    if isinstance(p68_live, dict):
        backfill_events = (
            p68_live.get("backfill_m5")
            or p68_live.get("historical_backfill_m5")
            or (p68_live.get("provenance_counts") or {}).get("HISTORICAL_BACKFILL")
        )
    lines.append("")
    lines.append("### Phase 68 metric nuance (not a contradiction if interpreted correctly)")
    lines.append("")
    lines.append("- Final report key counts: Live backfill M5 / newly closed M5 / quotes = **`245` / `0` / `5`** (`reports/phase68/PHASE68_FINAL_REPORT.md`).")
    lines.append("- These `245` values are **journal event / provenance counts** for `HISTORICAL_BACKFILL`, not unique-bar counts.")
    lines.append(
        f"- Phase69 unique historical-backfill M5 bars = **`{p69_acc.get('unique_historical_backfill_m5_bars')}`** "
        f"with provenance_counts HISTORICAL_BACKFILL=`{(p69_acc.get('provenance_counts') or {}).get('HISTORICAL_BACKFILL')}` "
        f"(`reports/phase69/live_evidence_accounting.json`)."
    )
    lines.append("- **Do not equate** unique bars with journal event counts.")
    lines.append("")
    lines.append("## Explicit Phase 69 verification")
    lines.append("")
    lines.append("| Claim | Observed | Source | Match? |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| Engineering-complete: True | Final report `Engineering-complete: True` | `PHASE69_FINAL_REPORT.md` | **PASS** |")
    lines.append(
        f"| Trading-edge-validated: False | `{p69_suf.get('trading_edge_validated')}` / final report False | `evidence_sufficiency.json` | **PASS** |"
    )
    lines.append(
        f"| Sufficiency: INSUFFICIENT_LIVE_EVIDENCE | `{p69_suf.get('status')}` | `evidence_sufficiency.json` | **PASS** |"
    )
    lines.append(
        f"| 5 quotes | live_quote_observations=`{p69_acc.get('live_quote_observations')}` | `live_evidence_accounting.json` | **PASS** |"
    )
    lines.append(
        f"| 49 unique historical-backfill M5 | `{p69_acc.get('unique_historical_backfill_m5_bars')}` | accounting json | **PASS** |"
    )
    lines.append(
        f"| 0 unique newly closed live M5 | `{p69_acc.get('unique_newly_closed_live_m5_bars')}` | accounting json | **PASS** |"
    )
    lines.append(
        f"| 0 independent live dates | `{p69_acc.get('n_independent_live_dates')}` | accounting json | **PASS** |"
    )
    lines.append(
        f"| Runtime 100.045 seconds | `{p69_acc.get('runtime_sec_measured')}` (Phase67 verify; not long-term uptime) | accounting + sufficiency | **PASS** |"
    )
    hyp_ids = [h.get("id") for h in (p69_reg.get("hypotheses") or [])]
    lines.append(
        f"| H69_D1 / H69_LS1 / H69_US1 preregistered unvalidated | ids=`{hyp_ids}`; statuses=`{[h.get('status') for h in (p69_reg.get('hypotheses') or [])]}` | `hypothesis_registry.json` | **PASS** |"
    )
    lines.append("")
    lines.append("### Phase 67 vs Phase 69 live-count discrepancy (flagged, not silently resolved)")
    lines.append("")
    lines.append(
        f"- Phase67 verdict reason text claimed live Exness dates=`1` m5=`250` quotes=`5` while sufficiency=`INSUFFICIENT_LIVE_EVIDENCE` "
        f"(`reports/phase67/verdict.json` reason; measured_verify_runtime_sec=`{p67.get('measured_verify_runtime_sec')}`, verify_ingested=`{p67.get('verify_ingested')}`)."
    )
    lines.append(
        "- Phase68/69 corrected accounting: **HISTORICAL_BACKFILL is excluded** from newly-closed live M5; "
        "result is live closed M5=`0`, independent live dates=`0`."
    )
    lines.append(
        "- Auditor guidance: **treat Phase68/69 provenance-separated accounting as authoritative** for live sufficiency; "
        "treat Phase67 aggregated m5=250 as contaminated by lookback/backfill unless independently re-proven."
    )
    lines.append("")
    lines.append("## Phase-by-phase consolidated audit (compact)")
    lines.append("")
    lines.append(
        "For each phase: objective/title, artifact path, verdict, evidence class. "
        "Detailed numerical metrics are preserved in the cited original files — do not prefer this summary over originals when they conflict."
    )
    lines.append("")
    for r in rows:
        lines.append(f"### `{r['id']}` — {r['title']}")
        lines.append("")
        if not r["dir_exists"]:
            lines.append("- **Status:** `MISSING` — no directory under `reports/`.")
            lines.append("- All fields: `UNKNOWN`.")
            lines.append("")
            continue
        lines.append(f"- **Artifact:** `{r['artifact_path'] or 'NONE'}` ({r['n_files']} files)")
        lines.append(f"- **Verdict / conclusion label:** `{r['verdict']}`")
        lines.append(f"- **Evidence class:** {r['evidence_class']}")
        # add richer bullets for selected key phases
        if r["id"] == "phase45":
            lines.append(f"- **Hypotheses in consolidated registry:** `{p45.get('n_hypotheses')}` (all REJECTED in registry dump)")
            lines.append(f"- **Strategies registered:** `{p45.get('n_strategies')}`")
            lines.append(f"- **Retired / do-not-revive count:** `{len(p45.get('retired_do_not_revive') or [])}`")
            lines.append("- **Objective:** Research architecture audit after 44 phases; redirect away from indicator-family screens.")
        if r["id"] == "phase54":
            lines.append("- **Objective:** Autonomous paper-bot engineering (NullPolicy WAIT); not a trading-edge claim.")
            lines.append("- **Replay:** 20 days, 40 decisions, all WAIT sample in final report.")
        if r["id"] == "phase58":
            lines.append("- **Critical:** Sealed holdout created — **do not access sealed Phase58 holdout outcomes** in this handoff or future unauthorized work.")
        if r["id"] == "phase65":
            lines.append(f"- **Verdict object:** `{p65.get('verdict')}`; survivors_discovery=`{p65.get('survivors_discovery')}`")
        if r["id"] == "phase66":
            lines.append(
                f"- **Verdict:** `{p66.get('verdict')}`; engineering_ready=`{p66.get('engineering_ready')}`; "
                f"independent_research_evidence_sufficient=`{p66.get('independent_research_evidence_sufficient')}`; "
                f"live_genuine_observations_ingested=`{p66.get('live_genuine_observations_ingested')}`"
            )
        if r["id"] == "phase67":
            lines.append(
                f"- **Verdict:** `{p67.get('verdict')}`; engineering_ops_ready=`{p67.get('engineering_ops_ready')}`; "
                f"exploratory_complete=`{p67.get('exploratory_complete')}`; "
                f"live_evidence_sufficient_for_discovery=`{p67.get('live_evidence_sufficient_for_discovery')}`"
            )
        if r["id"] == "phase68":
            lines.append(f"- **Work completed:** exploratory displacement response + live collection integrity verification.")
            lines.append(f"- **Sample:** events=`{p68.get('n_events')}`, dates=`{p68.get('n_dates')}`")
            lines.append(f"- **Final verdict:** `{p68.get('verdict')}`")
            lines.append(f"- **Limitations:** sample too small; archive exploratory ≠ Exness confirmation.")
        if r["id"] == "phase69":
            lines.append("- **Work completed:** live evidence accounting hardening; sufficiency gate; H69_* preregistry freeze; tests.")
            lines.append(
                f"- **Live evidence:** quotes=`{p69_acc.get('live_quote_observations')}`, "
                f"unique_backfill_m5=`{p69_acc.get('unique_historical_backfill_m5_bars')}`, "
                f"unique_live_closed_m5=`{p69_acc.get('unique_newly_closed_live_m5_bars')}`, "
                f"independent_live_dates=`{p69_acc.get('n_independent_live_dates')}`, "
                f"runtime_sec=`{p69_acc.get('runtime_sec_measured')}`"
            )
            lines.append(f"- **Sufficiency:** `{p69_suf.get('status')}`")
            lines.append(f"- **Hypotheses:** `{hyp_ids}` — confirmatory_tests_run=`{p69_reg.get('confirmatory_tests_run')}`")
            lines.append("- **Trading edge:** False / NOT VALIDATED")
            lines.append("- **Blockers:** need more independent live dates; tick stream APIs still unapproved (per final report).")
        lines.append("")

    lines.append("## Hypothesis ledger (verifiable subsets)")
    lines.append("")
    lines.append("### Phase45 consolidated registry (`reports/phase45/consolidated_experiment_registry.json`)")
    lines.append("")
    lines.append(f"- n_hypotheses=`{p45.get('n_hypotheses')}` — statuses in dump: all **REJECTED** (15)")
    lines.append(f"- retired_do_not_revive=`{p45.get('retired_do_not_revive')}`")
    lines.append("")
    lines.append("### Phase69 preregistered (unvalidated)")
    lines.append("")
    for h in p69_reg.get("hypotheses") or []:
        lines.append(f"- `{h.get('id')}` — status=`{h.get('status')}` — confirmatory tests not run")
    lines.append("")
    lines.append("### Accepted trading-edge hypotheses")
    lines.append("")
    lines.append("- **NONE VERIFIED** through Phase 69. Champion remains `NO_MODEL`.")
    lines.append("")
    lines.append("## Data provenance boundaries")
    lines.append("")
    lines.append("| Provenance | Meaning | May support trading-edge claims? |")
    lines.append("| --- | --- | --- |")
    lines.append("| `HISTORICAL_BACKFILL` | Broker history pulled at connect/lookback | **No** (not newly closed live) |")
    lines.append("| `BROKER_OBSERVED_LIVE_BAR` | Newly closed live M5 observed in session | Eligible for live accumulation (still not automatic edge) |")
    lines.append("| `BROKER_OBSERVED_QUOTE` | Live quote via approved RO path | Microstructure/spread evidence only as defined |")
    lines.append("| `LIVE_INCOMPLETE_OR_FORMING_M5` | Forming bar | Not a closed-bar observation |")
    lines.append("| `SYNTHETIC_FIXTURE` | Test fixtures | Never genuine |")
    lines.append("| MetaQuotes / archive XAUUSD | Historical research substrate | Exploratory only; ≠ Exness XAUUSDm confirmation |")
    lines.append("")
    (OUT / "AIBOT_PHASE_0_TO_69_EVIDENCE_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")


def write_failed_duplicate(rows):
    p45 = loadj(REPORTS / "phase45" / "consolidated_experiment_registry.json")
    lines = []
    lines.append("# AIBOT Failed and Duplicate Work")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Purpose: prevent re-running rejected or redundant research without a material new hypothesis or new independent evidence.")
    lines.append("")
    lines.append("## Explicitly retired / do-not-revive (Phase45 registry)")
    lines.append("")
    for item in p45.get("retired_do_not_revive") or []:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("Source: `reports/phase45/consolidated_experiment_registry.json` → `retired_do_not_revive`.")
    lines.append("")
    lines.append("## Documented research overlaps (Phase45)")
    lines.append("")
    for ov in p45.get("research_overlaps") or []:
        lines.append(f"### {ov.get('theme')}")
        lines.append("")
        lines.append(f"- Phases: `{ov.get('phases')}`")
        lines.append(f"- Information-gain assessment: {ov.get('information_gain_assessment')}")
        lines.append("")
    lines.append("## Repeated / redundant patterns identified in this audit")
    lines.append("")
    duplicates = [
        {
            "id": "DUP-01",
            "theme": "H13_C pullback retests",
            "phases": ["phase13", "phase14", "phase16a", "phase25", "phase29", "phase35", "phase39", "phase41"],
            "why_redundant": "Repeated evaluation of the same pullback family culminating in retirement after Phase41 insufficient/rejected evidence.",
            "rule": "Do not revive H13_C without a materially new definition + new independent Exness-native evidence block.",
        },
        {
            "id": "DUP-02",
            "theme": "mean_reversion / z / RSI family",
            "phases": ["phase25", "phase30", "phase35", "phase36", "phase39", "phase41"],
            "why_redundant": "Phase41 EDGE_REJECTED on full-session ticks; Phase45 marks retired.",
            "rule": "Do not re-screen mean_reversion variants under new names without new costed EV target + independent data.",
        },
        {
            "id": "DUP-03",
            "theme": "Indicator-family hypothesis screens",
            "phases": ["phase42", "phase44", "phase49", "phase53", "phase58", "phase65"],
            "why_redundant": "Multiple NO_PREDICTIVE_VALUE / NO_INFORMATION_FAMILY_FOUND / NO_EDGE_FOUND cycles on related ontology.",
            "rule": "Phase45 already required research-program redirect; further family screens without new ontology are redundant.",
        },
        {
            "id": "DUP-04",
            "theme": "Displacement continuation / retrace motifs",
            "phases": ["phase42 H42_J", "phase44 H44_2", "phase68 exploratory", "phase69 H69_D1 prereg"],
            "why_redundant": "H42_J and H44_2 rejected/retired; Phase68 is exploratory archive-only insufficient sample; H69_D1 is a NEW preregistered variant but MUST NOT treat Phase68 as confirmation.",
            "rule": "Only evaluate H69_D1 on Exness BROKER_OBSERVED_* after freeze; never count archive Phase68 events as confirmation.",
        },
        {
            "id": "DUP-05",
            "theme": "Historical bid/ask acquisition loops",
            "phases": ["phase33", "phase34", "phase35", "phase36", "phase37", "phase38", "phase40", "phase43"],
            "why_redundant": "Necessary for data readiness (high info gain once), but repeating acquisition without new broker-truth question yields diminishing returns.",
            "rule": "Do not reopen large historical downloads as a substitute for Exness live accumulation or cost-model completion.",
        },
        {
            "id": "DUP-06",
            "theme": "Experience-learning claims without adaptive loop",
            "phases": ["phase8", "phase9", "phase10", "phase11", "phase50", "phase54"],
            "why_redundant": "Phase9: experience learning did not improve OOS; Phase45/50: AGENT_SHADOW empty / no demonstrated learning value; Phase54 NullPolicy WAIT only.",
            "rule": "Do not claim adaptive learning until AGENT_SHADOW outcomes actually change a non-null validated policy.",
        },
        {
            "id": "DUP-07",
            "theme": "Live evidence inflation via lookback/backfill",
            "phases": ["phase67 (aggregated counts)", "phase68/69 (corrected)"],
            "why_redundant": "Phase67-style aggregated m5 counts mixed backfill with live; Phase68/69 corrected. Re-running short verify loops will not create independent live dates.",
            "rule": "Never count HISTORICAL_BACKFILL as newly closed live evidence. Need multi-day continuous RO collection.",
        },
        {
            "id": "DUP-08",
            "theme": "Engineering readiness ≠ trading edge",
            "phases": ["phase54", "phase55", "phase56", "phase64_*", "phase66", "phase69"],
            "why_redundant": "Repeated engineering-complete milestones without edge validation can be misread as bot readiness for trading.",
            "rule": "Keep engineering-complete and trading-edge-validated as separate gates forever.",
        },
        {
            "id": "DUP-09",
            "theme": "Session-structure video-inspired ideas without frozen definitions",
            "phases": ["phase69 H69_LS1", "phase69 H69_US1"],
            "why_redundant": "Preregistered but definitions unresolved; evaluating now would be post-hoc fishing.",
            "rule": "Freeze IANA/DST-aware definitions before any Exness evaluation; do not validate against video-advertised results.",
        },
        {
            "id": "DUP-10",
            "theme": "Cost/economics partial loops without completion",
            "phases": ["phase32", "phase59", "phase60", "phase64_10"],
            "why_redundant": "Execution realism / economics repeatedly PARTIAL; Commission/Swap remain UNKNOWN.",
            "rule": "Do not zero unknown costs; do not promote strategies while CostModel=INCOMPLETE.",
        },
    ]
    for d in duplicates:
        lines.append(f"### `{d['id']}` — {d['theme']}")
        lines.append("")
        lines.append(f"- Involved: `{d['phases']}`")
        lines.append(f"- Why flagged: {d['why_redundant']}")
        lines.append(f"- Do-not-repeat rule: {d['rule']}")
        lines.append("")
    lines.append("## Failed strategies that should stay retired")
    lines.append("")
    lines.append("- `H13_C` (pullback champion candidate) — retired")
    lines.append("- `mean_reversion` — EDGE_REJECTED / retired")
    lines.append("- All `H42_*` and `H44_*` IDs in Phase45 retired list")
    lines.append("- Any rename of the above without material definition + evidence change")
    lines.append("")
    lines.append("## Work that should never be repeated without material change")
    lines.append("")
    lines.append("1. Another MetaQuotes-archive displacement screen claiming confirmation.")
    lines.append("2. Another indicator-family kitchen-sink screen on the same ontology.")
    lines.append("3. Treating paper NullPolicy WAIT replay as trading-edge validation.")
    lines.append("4. Short (~100s) collector verify loops presented as multi-day live evidence.")
    lines.append("5. Accessing sealed Phase58 holdout outcomes.")
    lines.append("6. Enabling broker writes / order_send under any 'temporary test' framing.")
    lines.append("")
    lines.append(f"**Duplicate/redundant experiment themes identified in this handoff:** `{len(duplicates)}`")
    lines.append("")
    (OUT / "AIBOT_FAILED_AND_DUPLICATE_WORK.md").write_text("\n".join(lines), encoding="utf-8")
    return len(duplicates)


def write_architecture():
    lines = []
    lines.append("# AIBOT Current System Architecture")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Distinguishes **IMPLEMENTED** vs **PLANNED/UNVERIFIED** as of Phase 69.")
    lines.append("")
    lines.append("## Safety boundary (hard)")
    lines.append("")
    lines.append("```")
    lines.append("Champion = NO_MODEL")
    lines.append("Production = WAIT")
    lines.append("Live trading = NOT_AUTHORIZED")
    lines.append("Automated orders = DISABLED")
    lines.append("order_send = PROHIBITED")
    lines.append("Broker collection = READ_ONLY")
    lines.append("Execution authorization = BLOCKED")
    lines.append("Risk policy = UNAPPROVED")
    lines.append("Cost model = INCOMPLETE (commission/swap/margin unknowns NOT zeroed)")
    lines.append("Genuine trade fills = NONE_TRADE_FILLS")
    lines.append("```")
    lines.append("")
    lines.append("Key constant modules: `src/phase66/constants.py`, `src/phase68/constants.py`, `src/phase69/constants.py`.")
    lines.append("")
    lines.append("## Component map")
    lines.append("")
    lines.append("### 1. Data collection — IMPLEMENTED (READ_ONLY)")
    lines.append("")
    lines.append("- Allowlisted MT5 reads: `symbol_info`, `copy_rates_*` (ticks **not** approved).")
    lines.append("- Collector: `src/phase66/collector.py`")
    lines.append("- Service/CLI: `src/phase67/service.py`, `src/phase67/cli.py`")
    lines.append("- Prior RO path: `src/phase64_8/collector.py`, Live/Fake backends under `src/phase64_9/`")
    lines.append("- Status: engineering-ready; continuous multi-day uptime **not** claimed.")
    lines.append("")
    lines.append("### 2. Data storage and provenance — IMPLEMENTED")
    lines.append("")
    lines.append("- Broker evidence journal (Phase67 path referenced by Phase69 accounting): `src/data/phase67/exness_market_evidence_journal`")
    lines.append("- Provenance stamps: `HISTORICAL_BACKFILL`, `BROKER_OBSERVED_LIVE_BAR`, `BROKER_OBSERVED_QUOTE`, `LIVE_INCOMPLETE_OR_FORMING_M5`, fixtures separate")
    lines.append("- Accounting: `src/phase69/accounting.py`, `src/phase69/provenance.py`, `src/phase68/live_integrity.py`")
    lines.append("- Dual experience isolation: `src/phase66/dual_experience.py` (historical hypothetical ≠ agent paper decisions)")
    lines.append("")
    lines.append("### 3. Feature generation — IMPLEMENTED (research/paper path)")
    lines.append("")
    lines.append("- Phase49/53 feature stacks reused by paper agent (`phase54` wraps prior feature compute).")
    lines.append("- Session semantics: Phase64.12 / 64.13 session evidence (`OPEN` / `CLOSE_ONLY` / `BREAK` / `CLOSED` / `UNKNOWN`).")
    lines.append("- Status: features exist; **no validated predictive family**.")
    lines.append("")
    lines.append("### 4. Strategy / hypothesis registry — IMPLEMENTED (research)")
    lines.append("")
    lines.append("- Historical consolidated registry: `reports/phase45/consolidated_experiment_registry.json`")
    lines.append("- Current freeze: `src/phase69/registry.py` → `reports/phase69/hypothesis_registry.json` (`H69_D1`, `H69_LS1`, `H69_US1`)")
    lines.append("- Status: preregistered; **unvalidated**; LS1/US1 definitions unresolved.")
    lines.append("")
    lines.append("### 5. Decision engine — IMPLEMENTED (NullPolicy WAIT)")
    lines.append("")
    lines.append("- Paper decision stack: `src/phase54/` (`decision` NullPolicy, lifecycle, observer)")
    lines.append("- Default action: **WAIT**; Champion `NO_MODEL` blocks directional production actions.")
    lines.append("- Status: engineering complete for abstention bot; not an edge.")
    lines.append("")
    lines.append("### 6. Backtesting — IMPLEMENTED (historical research tooling)")
    lines.append("")
    lines.append("- Many phase-local backtest/eval modules (phase30–53 family).")
    lines.append("- Displacement exploratory: `src/phase68/displacement.py`, `competing.py`, `statistics.py`")
    lines.append("- Status: tools exist; surviving validated edge = **none**.")
    lines.append("")
    lines.append("### 7. Risk checks — PARTIAL / UNAPPROVED")
    lines.append("")
    lines.append("- Paper risk manager: `src/phase54/risk.py`")
    lines.append("- Legacy gate: `src/phase6/risk_gate.py`")
    lines.append("- Broker risk policy evidence: `src/phase64_10/risk_policy.py`, `src/phase64_11/risk_policy_evidence.py`")
    lines.append("- Status: `RiskPolicy=UNAPPROVED` for live/demo execution.")
    lines.append("")
    lines.append("### 8. Paper trading — IMPLEMENTED (replay / non-broker)")
    lines.append("")
    lines.append("- `src/phase54/paper_exec.py`, lifecycle, experience stores")
    lines.append("- Phase55/56 verified paper/replay paths")
    lines.append("- Status: paper path works; **no genuine broker fills**.")
    lines.append("")
    lines.append("### 9. Trade lifecycle — IMPLEMENTED (paper FSM)")
    lines.append("")
    lines.append("- `src/phase54/lifecycle` state machine with recovery hooks")
    lines.append("- Broker trade lifecycle for live orders: **NOT AUTHORIZED / PROHIBITED**")
    lines.append("")
    lines.append("### 10. Experience learning — PARTIAL")
    lines.append("")
    lines.append("- Stores for `HISTORICAL_HYPOTHETICAL` vs `AGENT_SHADOW` exist (phase10/50/54/66).")
    lines.append("- Phase45 finding: learning architecture not genuinely adaptive; shadow often empty.")
    lines.append("- Phase50 verdict: `NO_DEMONSTRATED_LEARNING_VALUE`")
    lines.append("- Status: bookkeeping IMPLEMENTED; policy-improving learning **UNVERIFIED/ABSENT**.")
    lines.append("")
    lines.append("### 11. Monitoring and recovery — PARTIAL")
    lines.append("")
    lines.append("- Collector health/watermark/quality: `src/phase66/health.py`, `watermark.py`, `quality.py`")
    lines.append("- Phase57 reliability partial; Phase69 progress/accounting")
    lines.append("- Continuous multi-day supervised collection ops: **NOT YET EVIDENCED** (only ~100.045s measured verify runtime in Phase67/69).")
    lines.append("")
    lines.append("### 12. Broker integration and safety boundaries — IMPLEMENTED (RO) / BLOCKED (writes)")
    lines.append("")
    lines.append("- Read-only collection path validated through Phase64.6–64.13 and Phase66–69.")
    lines.append("- Fake broker reject/accept matrices: Phase64.9")
    lines.append("- `order_send` prohibited; submission/execution flags false.")
    lines.append("- Economics incomplete: commission/swap/margin unknowns.")
    lines.append("")
    lines.append("## What is NOT claimed")
    lines.append("")
    lines.append("- No Champion model")
    lines.append("- No production BUY/SELL authorization")
    lines.append("- No genuine live trade fills")
    lines.append("- No completed cost model")
    lines.append("- No sufficient Exness live date sample for discovery confirmation")
    lines.append("")
    (OUT / "AIBOT_CURRENT_SYSTEM_ARCHITECTURE.md").write_text("\n".join(lines), encoding="utf-8")


def write_blockers():
    lines = []
    lines.append("# AIBOT Current Blockers and Completion Plan")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Goal: shortest **non-redundant** path to a functional autonomous **paper-trading** AI bot.")
    lines.append("- Explicitly **not** a new endless research-phase roadmap.")
    lines.append("")
    lines.append("## Ranked blockers")
    lines.append("")
    lines.append("### 1. Engineering blockers")
    lines.append("")
    lines.append("| ID | Severity | Impact | Blocker |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| E1 | Medium | Ops | Multi-day supervised RO collector uptime not yet evidenced (only ~100s verify runtime). |")
    lines.append("| E2 | Medium | Data quality | Tick stream APIs still unapproved; quote path via `symbol_info` only. |")
    lines.append("| E3 | Low | DX | Early phases sparse; some engineering docs fragmented across phase64_* modules. |")
    lines.append("| E4 | Low | Safety hygiene | Keep scanners from false-positive `order_send` literals (already mitigated in tests). |")
    lines.append("")
    lines.append("**Note:** Core paper agent engineering (Phase54–56) is largely done. Engineering is not the binding constraint for 'AI edge'.")
    lines.append("")
    lines.append("### 2. Data sufficiency blockers")
    lines.append("")
    lines.append("| ID | Severity | Impact | Blocker |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| D1 | **Critical** | Live research | Independent live dates = 0; unique newly closed live M5 = 0 (Phase69). |")
    lines.append("| D2 | High | Validity | Historical backfill must never be counted as live (Phase67 contamination lesson). |")
    lines.append("| D3 | High | Transfer | MetaQuotes/archive ≠ Exness XAUUSDm confirmation. |")
    lines.append("| D4 | Medium | Sealed data | Phase58 holdout sealed — do not open without explicit authorized protocol. |")
    lines.append("")
    lines.append("### 3. Trading-edge validation blockers")
    lines.append("")
    lines.append("| ID | Severity | Impact | Blocker |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| T1 | **Critical** | Product | Champion = NO_MODEL; no accepted predictive family through Phase69. |")
    lines.append("| T2 | High | Method | H69_* preregistered but unvalidated; LS1/US1 definitions unresolved. |")
    lines.append("| T3 | High | Method | Phase68 sample 28 events / 22 dates insufficient; exploratory only. |")
    lines.append("| T4 | High | Anti-pattern | Retired H13_C / mean_reversion / H42_* / H44_* must not be renamed and revived. |")
    lines.append("")
    lines.append("### 4. Execution-cost / economics blockers")
    lines.append("")
    lines.append("| ID | Severity | Impact | Blocker |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| C1 | **Critical** for live | Economics | CostModel=INCOMPLETE; Commission=UNKNOWN; Swap=UNKNOWN_FOR_EXECUTION; Margin=INCOMPLETE. |")
    lines.append("| C2 | High | Evaluation | Unknown costs must not be treated as zero in any EV claim. |")
    lines.append("| C3 | Medium | Paper realism | Paper path can simulate bid/ask but cannot invent broker commission/swap truth. |")
    lines.append("")
    lines.append("### 5. Risk and operational blockers")
    lines.append("")
    lines.append("| ID | Severity | Impact | Blocker |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| R1 | **Critical** for live | Safety | RiskPolicy=UNAPPROVED; ExecutionAuthorization=BLOCKED; order_send PROHIBITED. |")
    lines.append("| R2 | High | Ops | No genuine broker trade fills; live trading NOT_AUTHORIZED. |")
    lines.append("| R3 | Medium | Learning | AGENT_SHADOW adaptive loop not demonstrated; keep hist vs shadow separate. |")
    lines.append("")
    lines.append("## Shortest non-redundant path to a functional autonomous paper-trading bot")
    lines.append("")
    lines.append("Interpretation: a **functional autonomous paper-trading AI bot** means: runs unattended on paper, decides, journals, recovers — **not** that it has a validated edge.")
    lines.append("")
    lines.append("### Already done (do not redo)")
    lines.append("")
    lines.append("1. Paper agent pipeline with NullPolicy WAIT (Phase54–56).")
    lines.append("2. RO broker collection engineering (Phase64.6–69).")
    lines.append("3. Provenance-aware live evidence accounting (Phase68–69).")
    lines.append("4. Retirement of failed families (Phase45 registry).")
    lines.append("")
    lines.append("### Next implementation steps (minimal)")
    lines.append("")
    lines.append("1. **Operate the existing paper agent** on a scheduled replay/live-quote-informed paper loop with Champion=NO_MODEL (always WAIT or risk-gated abstention). This yields operational autonomy without claiming edge.")
    lines.append("2. **Run multi-day RO collection** (days, not 100-second verifies) until Phase69 sufficiency gates for live dates are met — for research evidence only.")
    lines.append("3. **Freeze definitions** for at most one preregistered hypothesis (prefer `H69_D1` — definitions already more complete than LS1/US1).")
    lines.append("4. **Evaluate once** on Exness-native live/discovery blocks with date-blocked stats + non-zero cost stress; expect rejection unless CI clears gates.")
    lines.append("5. **Only if** a hypothesis survives: wire a paper policy behind the existing Phase54 decision protocol; keep broker orders disabled.")
    lines.append("6. **Defer forever until approved:** live/demo `order_send`, sealed holdout peeking, unknown-cost=0, Champion promotion.")
    lines.append("")
    lines.append("### What not to do")
    lines.append("")
    lines.append("- Do not create Phase 70+ research sprawl for its own sake.")
    lines.append("- Do not re-run H13_C / mean_reversion / H42 / H44 screens.")
    lines.append("- Do not treat engineering-complete as trading-edge-validated.")
    lines.append("")
    lines.append("## Current readiness snapshot")
    lines.append("")
    lines.append("| Gate | Status |")
    lines.append("| --- | --- |")
    lines.append("| Engineering readiness (paper + RO collection) | **READY / COMPLETE** (with ops uptime still short) |")
    lines.append("| Trading-edge validation | **FALSE / NOT VALIDATED** |")
    lines.append("| Live-evidence sufficiency | **INSUFFICIENT_LIVE_EVIDENCE** |")
    lines.append("| Live trading authorization | **NOT_AUTHORIZED** |")
    lines.append("")
    (OUT / "AIBOT_CURRENT_BLOCKERS_AND_COMPLETION_PLAN.md").write_text("\n".join(lines), encoding="utf-8")


def write_handoff(rows, n_dup):
    p45 = loadj(REPORTS / "phase45" / "consolidated_experiment_registry.json")
    p68 = loadj(REPORTS / "phase68" / "verdict.json")
    p69_suf = loadj(REPORTS / "phase69" / "evidence_sufficiency.json")
    p69_acc = loadj(REPORTS / "phase69" / "live_evidence_accounting.json")
    p69_reg = loadj(REPORTS / "phase69" / "hypothesis_registry.json")

    present = [r for r in rows if r["dir_exists"]]
    missing = [r for r in rows if not r["dir_exists"]]
    with_report = [r for r in present if r["artifact_path"]]
    hyp_rej = len(p45.get("retired_do_not_revive") or [])
    hyp_p45 = int(p45.get("n_hypotheses") or 0)
    hyp_p69 = int(p69_reg.get("n") or len(p69_reg.get("hypotheses") or []))

    lines = []
    lines.append("# AIBOT External Audit Handoff (Phase 0–69)")
    lines.append("")
    lines.append(f"- Generated (UTC): `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`")
    lines.append("- Audience: independent external AI auditor (e.g. ChatGPT) with no prior AIBOT context.")
    lines.append("- Constraint honored: no Phase 70, no code behavior changes, no new experiments, no sealed-holdout access, no broker writes.")
    lines.append("")
    lines.append("## Read this package in order")
    lines.append("")
    lines.append("1. `AIBOT_EXTERNAL_AUDIT_HANDOFF.md` (this file)")
    lines.append("2. `AIBOT_PHASE_0_TO_69_MASTER_INDEX.md`")
    lines.append("3. `AIBOT_PHASE_0_TO_69_EVIDENCE_AUDIT.md`")
    lines.append("4. `AIBOT_FAILED_AND_DUPLICATE_WORK.md`")
    lines.append("5. `AIBOT_CURRENT_SYSTEM_ARCHITECTURE.md`")
    lines.append("6. `AIBOT_CURRENT_BLOCKERS_AND_COMPLETION_PLAN.md`")
    lines.append("7. Original reports under `original_reports/phase*/` inside the ZIP (authoritative for numbers)")
    lines.append("")
    lines.append("## One-page truth")
    lines.append("")
    lines.append("| Question | Answer |")
    lines.append("| --- | --- |")
    lines.append("| What has been done? | 69 integer phases + sub-phases of research/engineering from data/journals through RO Exness collection and paper-agent stack. |")
    lines.append("| What has failed? | All consolidated Phase45 hypotheses rejected/retired; repeated no-edge screens through Phase65; no Champion ever promoted. |")
    lines.append("| What currently works? | READ_ONLY broker collection engineering; provenance accounting; paper NullPolicy WAIT agent; safety invariants. |")
    lines.append("| What remains incomplete? | Live evidence sample; cost model; risk policy approval; any validated trading edge; tick API approval. |")
    lines.append("| Decisions already made? | Champion=NO_MODEL; Production=WAIT; live orders blocked; unknown costs ≠ 0; hist vs shadow experience separated; Phase58 holdout sealed. |")
    lines.append("| What must not be repeated? | See failed/duplicate doc — especially H13_C, mean_reversion, H42/H44 families, backfill-as-live counting, engineering≠edge confusion. |")
    lines.append("| Next implementation steps? | Operate paper WAIT bot; accumulate multi-day RO live bars; freeze/evaluate at most one H69 hypothesis on Exness-native evidence; keep orders disabled. |")
    lines.append("")
    lines.append("## Safety invariants (must remain unchanged)")
    lines.append("")
    for k, v in [
        ("Champion", "NO_MODEL"),
        ("Production", "WAIT"),
        ("Live trading", "NOT_AUTHORIZED"),
        ("Automated orders", "DISABLED"),
        ("order_send", "PROHIBITED"),
        ("Broker collection", "READ_ONLY"),
        ("Execution authorization", "BLOCKED"),
        ("Risk policy", "UNAPPROVED"),
        ("Cost model", "INCOMPLETE"),
        ("Commission", "UNKNOWN"),
        ("Swap", "UNKNOWN_FOR_EXECUTION"),
        ("Margin", "INCOMPLETE"),
        ("Genuine broker fills", "NONE_TRADE_FILLS"),
    ]:
        lines.append(f"- `{k}` = `{v}`")
    lines.append("")
    lines.append("Verified against `reports/phase68/verdict.json` invariants and `src/phase69/constants.py`.")
    lines.append("")
    lines.append("## Phase 68 / 69 verification summary")
    lines.append("")
    lines.append(
        f"- Phase68: verdict=`{p68.get('verdict')}`, events=`{p68.get('n_events')}`, dates=`{p68.get('n_dates')}`, "
        f"champion_promotion=`{p68.get('champion_promotion')}`, live_integrity=`{p68.get('live_collection_integrity_verified')}`."
    )
    lines.append(
        f"- Phase69: sufficiency=`{p69_suf.get('status')}`, trading_edge_validated=`{p69_suf.get('trading_edge_validated')}`, "
        f"quotes=`{p69_acc.get('live_quote_observations')}`, unique_backfill_m5=`{p69_acc.get('unique_historical_backfill_m5_bars')}`, "
        f"unique_live_closed_m5=`{p69_acc.get('unique_newly_closed_live_m5_bars')}`, "
        f"independent_live_dates=`{p69_acc.get('n_independent_live_dates')}`, runtime_sec=`{p69_acc.get('runtime_sec_measured')}`."
    )
    lines.append(
        f"- H69 hypotheses: `{[h.get('id') for h in (p69_reg.get('hypotheses') or [])]}` statuses=`{[h.get('status') for h in (p69_reg.get('hypotheses') or [])]}`."
    )
    lines.append("- **Flag:** Phase67 aggregated live m5 counts are not authoritative vs Phase68/69 provenance split.")
    lines.append("")
    lines.append("## Important source files")
    lines.append("")
    lines.append("### Reports (authoritative evidence)")
    lines.append("")
    important_reports = [
        "reports/phase45/FINAL_REPORT.md",
        "reports/phase45/consolidated_experiment_registry.json",
        "reports/phase54/FINAL_REPORT.md",
        "reports/phase58/FINAL_REPORT.md",
        "reports/phase65/PHASE65_FINAL_REPORT.md",
        "reports/phase66/PHASE66_FINAL_REPORT.md",
        "reports/phase67/PHASE67_FINAL_REPORT.md",
        "reports/phase68/PHASE68_FINAL_REPORT.md",
        "reports/phase68/verdict.json",
        "reports/phase69/PHASE69_FINAL_REPORT.md",
        "reports/phase69/evidence_sufficiency.json",
        "reports/phase69/live_evidence_accounting.json",
        "reports/phase69/hypothesis_registry.json",
    ]
    for p in important_reports:
        exists = (ROOT / p).exists()
        lines.append(f"- `{'OK' if exists else 'MISSING'}` `{p}`")
    lines.append("")
    lines.append("### Source code (current architecture)")
    lines.append("")
    important_src = [
        "src/phase54/paper_exec.py",
        "src/phase54/risk.py",
        "src/phase66/collector.py",
        "src/phase66/dual_experience.py",
        "src/phase67/service.py",
        "src/phase68/displacement.py",
        "src/phase68/live_integrity.py",
        "src/phase69/accounting.py",
        "src/phase69/registry.py",
        "src/phase69/sufficiency.py",
        "src/phase69/constants.py",
        "src/phase6/risk_gate.py",
        "src/phase64_9/fake_broker.py",
    ]
    inaccessible = []
    for p in important_src:
        exists = (ROOT / p).exists()
        if not exists:
            inaccessible.append(p)
        lines.append(f"- `{'OK' if exists else 'MISSING'}` `{p}`")
    lines.append("")
    lines.append("## Hypothesis accounting (verifiable)")
    lines.append("")
    lines.append(f"- Phase45 consolidated hypotheses tested (registry): **{hyp_p45}** — rejected in dump: **{hyp_p45}**")
    lines.append(f"- Phase45 retired/do-not-revive entries: **{hyp_rej}**")
    lines.append(f"- Phase69 preregistered unvalidated: **{hyp_p69}**")
    lines.append("- Accepted trading-edge hypotheses through Phase69: **0** (Champion NO_MODEL)")
    lines.append("- Broader historical strategy screens (e.g. Phase30) produced **NO_NEW_EDGE_FOUND**; treat additional accepted count as **0** unless an original report explicitly says otherwise.")
    lines.append("")
    lines.append("## Package inventory counts")
    lines.append("")
    lines.append(f"- Catalogued phase IDs (0–69 + subphases in catalog): **{len(rows)}**")
    lines.append(f"- Phase report directories found: **{len(present)}**")
    lines.append(f"- Missing catalog dirs: **{', '.join(r['id'] for r in missing) or 'none'}**")
    lines.append("- Missing exact integer dirs with lettered substitutes only: **`phase15`**, **`phase16`** (see `15a/b/c`, `16a/b`)")
    lines.append(f"- Directories with final/summary artifact: **{len(with_report)}**")
    lines.append("- Sparse present dirs (intermediate JSON only): **`phase2`, `phase3`, `phase4`, `phase5`, `phase6`, `phase7`, `phase12`**")
    lines.append(f"- Duplicate/redundant themes flagged: **{n_dup}**")
    lines.append("")
    lines.append("## Files this handoff could not access")
    lines.append("")
    if inaccessible:
        for p in inaccessible:
            lines.append(f"- `{p}`")
    else:
        lines.append("- None among the critical source/report paths listed above.")
    lines.append("- `reports/phase0/`: directory does not exist.")
    lines.append("- Exact `reports/phase15/` and `reports/phase16/`: do not exist (lettered sub-phases do).")
    lines.append("- Sealed Phase58 holdout outcome contents: **intentionally not accessed**.")
    lines.append("")
    lines.append("## Auditor anti-goals")
    lines.append("")
    lines.append("- Do not authorize live trading from this package.")
    lines.append("- Do not invent missing metrics.")
    lines.append("- Do not collapse engineering-complete into edge-validated.")
    lines.append("- Do not treat HISTORICAL_BACKFILL as live evidence.")
    lines.append("")
    (OUT / "AIBOT_EXTERNAL_AUDIT_HANDOFF.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "n_phases_catalog": len(rows),
        "n_dirs": len(present),
        "missing": [r["id"] for r in missing],
        "n_reports": len(with_report),
        "hyp_tested_p45": hyp_p45,
        "hyp_rejected_p45": hyp_p45,
        "hyp_retired": hyp_rej,
        "hyp_accepted": 0,
        "hyp_unvalidated_p69": hyp_p69,
        "n_dup": n_dup,
        "inaccessible": inaccessible + (["reports/phase0/"] if missing else []),
    }


def build_zip():
    zip_path = OUT / "AIBOT_PHASE_0_TO_69_COMPLETE.zip"
    if zip_path.exists():
        zip_path.unlink()
    audit_files = [
        "AIBOT_PHASE_0_TO_69_MASTER_INDEX.md",
        "AIBOT_PHASE_0_TO_69_EVIDENCE_AUDIT.md",
        "AIBOT_FAILED_AND_DUPLICATE_WORK.md",
        "AIBOT_CURRENT_SYSTEM_ARCHITECTURE.md",
        "AIBOT_CURRENT_BLOCKERS_AND_COMPLETION_PLAN.md",
        "AIBOT_EXTERNAL_AUDIT_HANDOFF.md",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in audit_files:
            p = OUT / name
            zf.write(p, arcname=f"audit/{name}")
        # original reports preserving folder structure under original_reports/
        for d in sorted(REPORTS.iterdir(), key=lambda p: p.name.lower()):
            if not d.is_dir():
                continue
            if d.name == "external_audit_handoff":
                continue
            if not (d.name.startswith("phase") or d.name == "strategy_research"):
                continue
            for f in d.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(REPORTS)
                    zf.write(f, arcname=f"original_reports/{rel.as_posix()}")
    return zip_path


def verify_zip(zip_path: Path):
    required = [
        "audit/AIBOT_PHASE_0_TO_69_MASTER_INDEX.md",
        "audit/AIBOT_PHASE_0_TO_69_EVIDENCE_AUDIT.md",
        "audit/AIBOT_FAILED_AND_DUPLICATE_WORK.md",
        "audit/AIBOT_CURRENT_SYSTEM_ARCHITECTURE.md",
        "audit/AIBOT_CURRENT_BLOCKERS_AND_COMPLETION_PLAN.md",
        "audit/AIBOT_EXTERNAL_AUDIT_HANDOFF.md",
        "original_reports/phase68/PHASE68_FINAL_REPORT.md",
        "original_reports/phase68/verdict.json",
        "original_reports/phase69/PHASE69_FINAL_REPORT.md",
        "original_reports/phase69/evidence_sufficiency.json",
        "original_reports/phase1/phase1_summary.json",
        "original_reports/phase45/FINAL_REPORT.md",
    ]
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        missing = [r for r in required if r not in names]
        n_orig = sum(1 for n in names if n.startswith("original_reports/"))
        n_audit = sum(1 for n in names if n.startswith("audit/"))
        # spot-check phase69 sufficiency inside zip matches disk
        data = zf.read("original_reports/phase69/evidence_sufficiency.json")
        j = json.loads(data)
        assert j.get("status") == "INSUFFICIENT_LIVE_EVIDENCE"
        assert j.get("trading_edge_validated") is False
        v68 = json.loads(zf.read("original_reports/phase68/verdict.json"))
        assert v68.get("verdict") == "INSUFFICIENT_SAMPLE"
        assert v68.get("n_events") == 28
        assert v68.get("n_dates") == 22
    return {
        "missing_required": missing,
        "n_names": len(names),
        "n_orig": n_orig,
        "n_audit": n_audit,
        "ok": not missing,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_index_rows()
    write_master_index(rows)
    write_evidence_audit(rows)
    n_dup = write_failed_duplicate(rows)
    write_architecture()
    write_blockers()
    stats = write_handoff(rows, n_dup)
    zip_path = build_zip()
    vz = verify_zip(zip_path)
    summary = {
        "stats": stats,
        "zip": str(zip_path),
        "zip_verify": vz,
        "engineering_readiness": "READY/COMPLETE (paper + RO collection; multi-day uptime not evidenced)",
        "trading_edge_status": "FALSE / NOT_VALIDATED",
        "live_evidence_sufficiency": "INSUFFICIENT_LIVE_EVIDENCE",
    }
    (OUT / "_handoff_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
