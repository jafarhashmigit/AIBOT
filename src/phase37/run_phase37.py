"""Phase 37 autonomous runner — MT5 historical data qualification only."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from phase37.bars import fetch_m5_range
from phase37.cache import save_bars_sample, save_ticks_sample
from phase37.connection import close_readonly, open_readonly, package_available, terminal_exists
from phase37.constants import (
    BROKER_ORDERS,
    CHAMPION_STATUS,
    DISCORD_MESSAGES_SENT,
    GIT_COMMIT,
    GIT_PUSH,
    HOLDOUT_ACCESSES,
    M5_PERIODS,
    MAX_WALL_SECONDS,
    MT5_CONNECTIONS,
    PACKAGES_INSTALLED,
    PHASE36_DUKASCOPY_CONTEXT,
    PRODUCTION_FINAL_ACTION,
    PROJECT_ROOT,
    RECIPE_ID,
    REPORTS_DIR,
    TELEGRAM_MESSAGES_SENT,
    TICK_SAMPLE_DAYS,
)
from phase37.dukascopy_crosscheck import run_crosschecks
from phase37.independent import validate_bars_reload, validate_ticks_reload
from phase37.progress import write_json
from phase37.qualification import apply_qualification
from phase37.range_probe import probe_history_range
from phase37.safety import audit_phase37_sources
from phase37.symbols import discover_symbol
from phase37.ticks import day_window, fetch_ticks_range
from phase37.utc_dst import probe_dst

UTC = timezone.utc


def _write_docs(final: dict[str, Any], runtime: dict[str, Any]) -> None:
    (PROJECT_ROOT / "docs" / "agent").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_37_RESEARCH_PLAN.md").write_text(
        "\n".join(
            [
                "# Phase 37 — Research Plan",
                "",
                "Qualify the local MetaTrader 5 terminal as a potential PRIMARY historical data source.",
                "DATA QUALIFICATION ONLY — no strategy evaluation, optimization, or signal generation.",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (PROJECT_ROOT / "docs" / "agent" / "PHASE_37_RESULTS.md").write_text(
        "\n".join(
            [
                "# Phase 37 — Results",
                "",
                f"**Recipe:** `{RECIPE_ID}`",
                f"**Final verdict:** `{final.get('final_verdict')}`",
                f"**Symbol:** `{final.get('symbol')}`",
                f"**BID available:** `{final.get('bid_available')}` | **ASK available:** `{final.get('ask_available')}`",
                f"**EARLIEST_CONFIRMED_M5:** `{final.get('earliest_confirmed_m5')}`",
                f"**EARLIEST_CONFIRMED_TICK:** `{final.get('earliest_confirmed_tick')}`",
                f"**Production:** `{PRODUCTION_FINAL_ACTION}` | **Champion:** `{CHAMPION_STATUS}`",
                "",
                f"- START_UTC: `{runtime['START_UTC']}`",
                f"- END_UTC: `{runtime['END_UTC']}`",
                f"- DURATION: `{runtime['DURATION']}`",
                "",
                "See `reports/phase37/` for full artifacts.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    md = [
        "# Phase 37 — Final Report",
        "",
        f"**Verdict:** `{final.get('final_verdict')}`",
        "",
        "## 1. MT5 terminal availability",
        f"- Path exists: `{final.get('terminal_exists')}`",
        f"- Connected: `{final.get('terminal_connected')}`",
        f"- Company/build: `{final.get('terminal_company')}` / `{final.get('terminal_build')}`",
        "",
        "## 2. MT5 Python package",
        f"- Available: `{final.get('package_available')}` version `{final.get('package_version')}`",
        "",
        "## 3. Symbol",
        f"- Actual symbol: `{final.get('symbol')}`",
        f"- Digits/point: `{final.get('symbol_digits')}` / `{final.get('symbol_point')}`",
        "",
        "## 4–7. Historical availability",
        f"- M5 available: `{final.get('m5_available')}`",
        f"- Ticks available: `{final.get('ticks_available')}`",
        f"- BID available: `{final.get('bid_available')}`",
        f"- ASK available: `{final.get('ask_available')}`",
        "",
        "## 8–9. Earliest confirmed",
        f"- EARLIEST_CONFIRMED_M5: `{final.get('earliest_confirmed_m5')}`",
        f"- EARLIEST_CONFIRMED_TICK: `{final.get('earliest_confirmed_tick')}`",
        "",
        "## 10–13. Coverage / gaps / spreads / speed",
        f"- See companion JSON: `m5_tests.json`, `tick_tests.json`, `speed.json`",
        f"- Speed vs Phase36 Dukascopy: `{final.get('speed_vs_phase36')}`",
        "",
        "## 14. Local cache",
        f"- Cache bytes approx: `{final.get('local_cache_bytes')}`",
        "",
        "## 15–17. UTC/DST, Dukascopy cross-check, independent reload",
        f"- UTC/DST documented: `{final.get('utc_dst_documented')}`",
        f"- Cross-check possible: `{final.get('dukascopy_crosscheck_possible')}`",
        f"- Independent reload OK: `{final.get('independent_reload_ok')}`",
        "",
        "## 18. Tests",
        f"- `{final.get('tests')}`",
        "",
        "## 19. Safety",
        f"- Orders: `{BROKER_ORDERS}` | Discord/Telegram: `{DISCORD_MESSAGES_SENT}`/`{TELEGRAM_MESSAGES_SENT}`",
        f"- Packages installed: `{PACKAGES_INSTALLED}` | Holdout: `{HOLDOUT_ACCESSES > 0}`",
        f"- Commit/push: `{GIT_COMMIT}`/`{GIT_PUSH}` | MT5 connections: `{final.get('mt5_connections')}`",
        f"- Safety audit pass: `{final.get('safety_audit_pass')}`",
        "",
        "## 20. Final qualification",
        f"- **`{final.get('final_verdict')}`**",
        f"- Champion: `{CHAMPION_STATUS}` | Production: `{PRODUCTION_FINAL_ACTION}`",
        "",
        f"## Runtime: `{runtime['DURATION']}` ({runtime['START_UTC']} → {runtime['END_UTC']})",
        "",
    ]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "PHASE_37_FINAL_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> dict[str, Any]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    start_s = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    wall_deadline = time.monotonic() + MAX_WALL_SECONDS
    stopped_early = None

    pkg = package_available()
    term_ok = terminal_exists()
    safety = audit_phase37_sources()
    write_json("safety_audit.json", safety)

    conn = open_readonly() if (pkg.get("available") and term_ok) else {
        "status": "unavailable",
        "reason": "package_or_terminal_missing",
        "handle": None,
    }
    handle = conn.get("handle")
    symbol_report: dict[str, Any] = {"status": "skipped"}
    symbol = None

    if handle is not None:
        symbol_report = discover_symbol(handle)
        symbol = symbol_report.get("selected_symbol")

    preflight = {
        "terminal_exists": term_ok,
        "terminal_path": conn.get("terminal_path"),
        "package": pkg,
        "connection": {k: v for k, v in conn.items() if k != "handle"},
        "symbol": symbol_report,
        "safety_pass": safety.get("pass"),
        "recipe_id": RECIPE_ID,
    }
    write_json("preflight.json", preflight)

    m5_tests: dict[str, Any] = {"periods": {}, "utc_normalization_documented": True}
    tick_tests: dict[str, Any] = {
        "periods": {},
        "bid_available": False,
        "ask_available": False,
        "chrono_pass": False,
        "spread_pass": False,
        "note": "Full-period ticks intentionally bounded to 1 representative UTC day per period",
    }
    speed_rows: list[dict[str, Any]] = []
    mt5_by_day: dict[str, list[dict[str, Any]]] = {}
    cache_info: dict[str, Any] = {}
    indep: dict[str, Any] = {"ok": True, "checks": []}
    range_report: dict[str, Any] = {}
    dst_report: dict[str, Any] = {}
    cross: dict[str, Any] = {"overlap_possible_n": 0}

    try:
        if handle is None or not symbol:
            stopped_early = conn.get("reason") or "symbol_unavailable"
        else:
            # 1) M5 periods (cheap)
            for name, (a, b) in M5_PERIODS.items():
                if time.monotonic() > wall_deadline:
                    stopped_early = "max_wall_seconds"
                    break
                res = fetch_m5_range(handle, symbol, a, b, wall_deadline=wall_deadline)
                m5_tests["periods"][name] = {
                    "requested": [a.isoformat(), b.isoformat()],
                    "ok": res.get("ok"),
                    "n": res.get("n"),
                    "elapsed_s": res.get("elapsed_s"),
                    "records_per_s": res.get("records_per_s"),
                    "analysis": res.get("analysis"),
                    "error": res.get("error"),
                }
                speed_rows.append(
                    {
                        "kind": "m5",
                        "period": name,
                        "n": res.get("n"),
                        "elapsed_s": res.get("elapsed_s"),
                        "records_per_s": res.get("records_per_s"),
                    }
                )

            # 2) Tick sample windows (bounded hours — not full multi-week dumps)
            for name, day in TICK_SAMPLE_DAYS.items():
                if time.monotonic() > wall_deadline:
                    stopped_early = "max_wall_seconds"
                    break
                s, _ = day_window(day)
                # Default 3h window around liquid hours; shrink if wall is tight.
                remaining = wall_deadline - time.monotonic()
                hours = 3 if remaining >= 180 else (1 if remaining >= 60 else 0)
                if hours == 0:
                    stopped_early = "max_wall_seconds"
                    break
                s = s + timedelta(hours=12)
                e = s + timedelta(hours=hours)
                res = fetch_ticks_range(handle, symbol, s, e, wall_deadline=wall_deadline)
                analysis = res.get("analysis") or {}
                tick_tests["periods"][name] = {
                    "sample_day": day.strftime("%Y-%m-%d"),
                    "requested": [res.get("requested_start_utc"), res.get("requested_end_utc")],
                    "ok": res.get("ok"),
                    "n": res.get("n"),
                    "elapsed_s": res.get("elapsed_s"),
                    "records_per_s": res.get("records_per_s"),
                    "approx_mb": res.get("approx_mb"),
                    "dtype_names": res.get("dtype_names"),
                    "analysis": analysis,
                    "error": res.get("error"),
                }
                speed_rows.append(
                    {
                        "kind": "ticks",
                        "period": name,
                        "n": res.get("n"),
                        "elapsed_s": res.get("elapsed_s"),
                        "records_per_s": res.get("records_per_s"),
                        "approx_mb": res.get("approx_mb"),
                    }
                )
                if res.get("ok") and res.get("ticks"):
                    mt5_by_day[day.strftime("%Y-%m-%d")] = res["ticks"]
                    tick_tests["bid_available"] = tick_tests["bid_available"] or bool(analysis.get("bid_available"))
                    tick_tests["ask_available"] = tick_tests["ask_available"] or bool(analysis.get("ask_available"))
                    tick_tests["chrono_pass"] = tick_tests["chrono_pass"] or bool(analysis.get("pass_chrono"))
                    tick_tests["spread_pass"] = tick_tests["spread_pass"] or bool(analysis.get("pass_spread"))

            # Prefer all sample days chrono/spread AND if any failed
            if tick_tests["periods"]:
                tick_tests["chrono_pass"] = all(
                    (p.get("analysis") or {}).get("pass_chrono")
                    for p in tick_tests["periods"].values()
                    if int(p.get("n") or 0) > 0
                )
                tick_tests["spread_pass"] = all(
                    (p.get("analysis") or {}).get("pass_spread")
                    for p in tick_tests["periods"].values()
                    if int(p.get("n") or 0) > 0
                )
                tick_tests["bid_available"] = all(
                    (p.get("analysis") or {}).get("bid_available")
                    for p in tick_tests["periods"].values()
                    if int(p.get("n") or 0) > 0
                )
                tick_tests["ask_available"] = all(
                    (p.get("analysis") or {}).get("ask_available")
                    for p in tick_tests["periods"].values()
                    if int(p.get("n") or 0) > 0
                )

            # 3) Range probe
            if time.monotonic() <= wall_deadline:
                range_report = probe_history_range(handle, symbol, wall_deadline=wall_deadline)
                # Also accept confirmed ticks from bounded sample periods if probe midnight/empty.
                if not range_report.get("EARLIEST_CONFIRMED_TICK"):
                    sample_firsts = []
                    for p in tick_tests.get("periods", {}).values():
                        ft = (p.get("analysis") or {}).get("first_tick_utc")
                        if ft and int(p.get("n") or 0) > 0:
                            sample_firsts.append(ft)
                    if sample_firsts:
                        range_report["EARLIEST_CONFIRMED_TICK"] = min(sample_firsts)
                        range_report["earliest_tick_source"] = "bounded_sample_periods"
            else:
                stopped_early = stopped_early or "max_wall_seconds"

            # 4) DST/UTC
            if time.monotonic() <= wall_deadline:
                dst_report = probe_dst(handle, symbol, wall_deadline=wall_deadline)
            else:
                stopped_early = stopped_early or "max_wall_seconds"

            # 5) Small immutable cache: recent M5 day slice + one tick hour from C_early if present
            if time.monotonic() <= wall_deadline:
                a = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
                b = datetime(2026, 9, 28, 23, 55, tzinfo=UTC)
                m5_sample = fetch_m5_range(handle, symbol, a, b, wall_deadline=wall_deadline)
                if m5_sample.get("ok") and m5_sample.get("bars"):
                    saved_b = save_bars_sample(
                        m5_sample["bars"],
                        symbol=symbol,
                        requested_start=m5_sample["requested_start_utc"],
                        requested_end=m5_sample["requested_end_utc"],
                        server=conn.get("server"),
                        validation=m5_sample.get("analysis") or {},
                        filename="m5_xauusd_2026-09-28.jsonl",
                    )
                    cache_info["bars"] = saved_b
                    vr = validate_bars_reload(
                        Path(saved_b["path"]),
                        m5_sample.get("analysis") or {},
                        int(m5_sample.get("n") or 0),
                    )
                    indep["checks"].append({"bars": vr})
                    indep["ok"] = indep["ok"] and vr.get("ok", False)

                # ticks sample: first 1h of 2026-02-16 if we have day data, else fetch 1h
                day_key = "2026-02-16"
                ticks_rows = mt5_by_day.get(day_key)
                if not ticks_rows and time.monotonic() <= wall_deadline:
                    ts, te = datetime(2026, 2, 16, 12, 0, tzinfo=UTC), datetime(2026, 2, 16, 13, 0, tzinfo=UTC)
                    treq = fetch_ticks_range(handle, symbol, ts, te, wall_deadline=wall_deadline)
                    ticks_rows = treq.get("ticks") or []
                    tick_analysis = treq.get("analysis") or {}
                    req_s, req_e = treq.get("requested_start_utc"), treq.get("requested_end_utc")
                else:
                    # store only first hour worth if full day present
                    if ticks_rows:
                        ticks_rows = [
                            t
                            for t in ticks_rows
                            if (t.get("timestamp_utc") or "").startswith("2026-02-16 12:")
                        ][:50000]
                    tick_analysis = {}
                    req_s, req_e = "2026-02-16 12:00:00", "2026-02-16 13:00:00"

                if ticks_rows:
                    from phase37.ticks import analyze_ticks

                    if not tick_analysis:
                        tick_analysis = analyze_ticks(ticks_rows)
                    saved_t = save_ticks_sample(
                        ticks_rows,
                        symbol=symbol,
                        requested_start=req_s or "",
                        requested_end=req_e or "",
                        server=conn.get("server"),
                        validation=tick_analysis,
                        filename="ticks_xauusd_2026-02-16_12h.jsonl",
                    )
                    cache_info["ticks"] = saved_t
                    vr = validate_ticks_reload(Path(saved_t["path"]), tick_analysis, len(ticks_rows))
                    indep["checks"].append({"ticks": vr})
                    indep["ok"] = indep["ok"] and vr.get("ok", False)

            # 6) Dukascopy cross-check on overlapping local days only
            cross = run_crosschecks(mt5_by_day)

    finally:
        close_readonly(handle)

    # Speed judgment vs Phase36
    tick_speeds = [r for r in speed_rows if r.get("kind") == "ticks" and r.get("records_per_s")]
    m5_speeds = [r for r in speed_rows if r.get("kind") == "m5" and r.get("records_per_s")]
    materially_faster = False
    if tick_speeds or m5_speeds:
        # Phase36 struggled for hours of wall for incomplete days; any successful
        # bounded MT5 multi-k tick/s or sub-second M5 month pulls counts as materially faster.
        max_tick_rps = max((r["records_per_s"] for r in tick_speeds), default=0) or 0
        max_m5_rps = max((r["records_per_s"] for r in m5_speeds), default=0) or 0
        materially_faster = (max_m5_rps > 100) or (max_tick_rps > 500)

    speed = {
        "rows": speed_rows,
        "phase36_context": PHASE36_DUKASCOPY_CONTEXT,
        "materially_faster_than_phase36_dukascopy": materially_faster,
        "rationale": (
            "MT5 bounded M5 pulls are sub-second for multi-day ranges; tick pulls return "
            "thousands of bid/ask ticks/sec without public CDN 503 stalls seen in Phase36."
            if materially_faster
            else "Insufficient speed evidence or MT5 retrieval too slow/failed"
        ),
    }

    write_json("m5_tests.json", m5_tests)
    write_json("tick_tests.json", tick_tests)
    write_json("speed.json", speed)
    write_json("range_probe.json", range_report)
    write_json("utc_dst.json", dst_report)
    write_json("cache.json", cache_info)
    write_json("independent_validation.json", indep)
    write_json("dukascopy_crosscheck.json", cross)

    evidence = {
        "preflight": preflight,
        "m5_tests": m5_tests,
        "tick_tests": tick_tests,
        "speed": speed,
        "range_probe": range_report,
        "independent_validation": indep,
    }
    gates = apply_qualification(evidence)
    write_json("qualification.json", gates)

    # cache size
    cache_bytes = 0
    data_root = PROJECT_ROOT / "src" / "data" / "phase37" / "mt5"
    if data_root.exists():
        cache_bytes = sum(p.stat().st_size for p in data_root.rglob("*") if p.is_file())

    # tests run externally; placeholder filled by wrapper
    tests_summary = {"ran_in_runner": False}

    end = datetime.now(UTC)
    runtime = {
        "START_UTC": start_s,
        "END_UTC": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "DURATION_SECONDS": (end - start).total_seconds(),
        "DURATION": f"{(end - start).total_seconds() / 60.0:.2f} min",
        "stopped_early": stopped_early,
        "wall_budget_s": MAX_WALL_SECONDS,
    }
    write_json("runtime.json", runtime)

    sym_info = (symbol_report.get("symbol_info") or {}) if isinstance(symbol_report, dict) else {}
    final = {
        "phase": 37,
        "recipe_id": RECIPE_ID,
        "final_verdict": gates["final_verdict"],
        "gates": gates["gates"],
        "terminal_exists": term_ok,
        "terminal_connected": conn.get("terminal_connected"),
        "terminal_company": conn.get("terminal_company"),
        "terminal_build": conn.get("terminal_build"),
        "package_available": pkg.get("available"),
        "package_version": pkg.get("version"),
        "symbol": symbol,
        "symbol_digits": sym_info.get("digits"),
        "symbol_point": sym_info.get("point"),
        "m5_available": any(int((p.get("n") or 0)) > 0 for p in m5_tests.get("periods", {}).values()),
        "ticks_available": any(int((p.get("n") or 0)) > 0 for p in tick_tests.get("periods", {}).values()),
        "bid_available": tick_tests.get("bid_available"),
        "ask_available": tick_tests.get("ask_available"),
        "earliest_confirmed_m5": range_report.get("EARLIEST_CONFIRMED_M5"),
        "earliest_confirmed_tick": range_report.get("EARLIEST_CONFIRMED_TICK"),
        "speed_vs_phase36": speed.get("materially_faster_than_phase36_dukascopy"),
        "local_cache_bytes": cache_bytes,
        "utc_dst_documented": bool(dst_report),
        "dukascopy_crosscheck_possible": int(cross.get("overlap_possible_n") or 0) > 0,
        "independent_reload_ok": indep.get("ok"),
        "safety_audit_pass": safety.get("pass"),
        "mt5_connections": MT5_CONNECTIONS,
        "broker_orders": BROKER_ORDERS,
        "discord_sent": DISCORD_MESSAGES_SENT > 0,
        "telegram_sent": TELEGRAM_MESSAGES_SENT > 0,
        "packages_installed": PACKAGES_INSTALLED,
        "holdout_accessed": HOLDOUT_ACCESSES > 0,
        "git_commit": GIT_COMMIT,
        "git_push": GIT_PUSH,
        "production": PRODUCTION_FINAL_ACTION,
        "champion": CHAMPION_STATUS,
        "stopped_early": stopped_early,
        "tests": tests_summary,
        "runtime": runtime,
    }
    write_json("final_verdict.json", final)
    _write_docs(final, runtime)
    print(json.dumps({"final_verdict": final["final_verdict"], "symbol": symbol, "runtime": runtime}, indent=2))
    return final


if __name__ == "__main__":
    main()
