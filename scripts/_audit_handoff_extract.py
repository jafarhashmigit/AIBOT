"""One-shot extractor for external audit handoff. Does not modify project behavior."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("reports")
OUT = Path("reports/external_audit_handoff/_extract_cache.json")


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_parse_error": str(e)}


def pick_verdict(j: dict):
    if not isinstance(j, dict):
        return None
    for k in (
        "verdict",
        "final_verdict",
        "status",
        "conclusion",
        "result",
        "phase_verdict",
        "overall_verdict",
    ):
        v = j.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            return (
                v.get("verdict")
                or v.get("status")
                or v.get("label")
                or json.dumps(v, sort_keys=True)[:200]
            )
        return str(v)
    # nested common shapes
    for nest in ("summary", "final", "outcome"):
        n = j.get(nest)
        if isinstance(n, dict):
            vv = pick_verdict(n)
            if vv:
                return vv
    return None


def first_heading(text: str) -> str | None:
    for line in text.splitlines()[:40]:
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:160]
    return None


def extract_md_bits(text: str) -> dict:
    out = {}
    h = first_heading(text)
    if h:
        out["title"] = h
    # common bold fields
    for key in (
        "Verdict",
        "Final Verdict",
        "Engineering-complete",
        "Engineering complete",
        "Trading-edge-validated",
        "Trading edge validated",
        "Sufficiency",
        "Champion",
        "Production",
        "Live trading",
    ):
        m = re.search(
            rf"(?:\*\*)?{re.escape(key)}(?:\*\*)?\s*[:=]\s*`?([^`\n*]+)`?",
            text,
            re.I,
        )
        if m:
            out[key.lower().replace(" ", "_")] = m.group(1).strip()
    # sample size patterns
    for label, pat in [
        ("events_28", r"\b28\s+events\b"),
        ("dates_22", r"\b22\s+dates\b"),
        ("quotes_5", r"\b5\s+quotes\b"),
        ("runtime_100", r"100\.0?45\s*seconds?"),
    ]:
        if re.search(pat, text, re.I):
            out[label] = True
    return out


def main():
    rows = []
    for d in sorted(ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name.startswith("external_audit"):
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        jsons = [p for p in files if p.suffix == ".json"]
        mds = [p for p in files if p.suffix.lower() == ".md"]

        verdict = None
        verdict_src = None
        preferred_json = []
        for name in (
            "verdict.json",
            "final_verdict.json",
            "final_qualification.json",
        ):
            preferred_json.extend([p for p in jsons if p.name == name])
        preferred_json.extend(
            sorted(
                [
                    p
                    for p in jsons
                    if "summary" in p.name.lower() or "conclusion" in p.name.lower()
                ],
                key=lambda p: p.name,
            )
        )
        for p in preferred_json:
            j = load_json(p)
            v = pick_verdict(j)
            if v:
                verdict = v
                verdict_src = str(p).replace("\\", "/")
                break
            # keep raw keys of interest
            if verdict is None and isinstance(j, dict) and "_parse_error" not in j:
                slim = {
                    k: j[k]
                    for k in j
                    if k
                    in (
                        "engineering_complete",
                        "trading_edge_validated",
                        "sufficiency",
                        "champion",
                        "production",
                        "live_trading",
                        "n_events",
                        "n_dates",
                        "n_quotes",
                        "unique_historical_backfill_m5",
                        "unique_newly_closed_live_m5",
                        "independent_live_dates",
                        "runtime_seconds",
                        "hypotheses",
                        "status",
                    )
                    or k.endswith("_complete")
                    or "sufficien" in k.lower()
                    or "edge" in k.lower()
                }
                if slim:
                    verdict = slim
                    verdict_src = str(p).replace("\\", "/")
                    break

        final_md = None
        md_bits = {}
        for p in sorted(mds, key=lambda x: (0 if "FINAL" in x.name.upper() else 1, x.name)):
            if "FINAL" in p.name.upper() or p.name.upper() == "FINAL_REPORT.MD":
                final_md = str(p).replace("\\", "/")
                text = p.read_text(encoding="utf-8", errors="replace")
                md_bits = extract_md_bits(text)
                if verdict is None:
                    verdict = md_bits.get("verdict") or md_bits.get("final_verdict")
                    if verdict:
                        verdict_src = final_md
                break
        if final_md is None and mds:
            p = mds[0]
            final_md = str(p).replace("\\", "/")
            md_bits = extract_md_bits(p.read_text(encoding="utf-8", errors="replace"))

        rows.append(
            {
                "dir": d.name,
                "path": str(d).replace("\\", "/"),
                "n_files": len(files),
                "n_md": len(mds),
                "n_json": len(jsons),
                "final_md": final_md,
                "verdict": verdict,
                "verdict_src": verdict_src,
                "md_bits": md_bits,
                "json_names": sorted({p.name for p in jsons})[:40],
                "md_names": sorted({p.name for p in mds})[:40],
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUT} rows={len(rows)}")
    print("WITH_FINAL_MD", sum(1 for r in rows if r["final_md"] and "FINAL" in (r["final_md"] or "").upper()))
    print("WITH_ANY_MD", sum(1 for r in rows if r["n_md"] > 0))
    print("WITH_VERDICT", sum(1 for r in rows if r["verdict"] is not None))
    # phase0 check
    print("HAS_PHASE0", any(r["dir"] == "phase0" for r in rows))
    print("DIRS", [r["dir"] for r in rows])


if __name__ == "__main__":
    main()
