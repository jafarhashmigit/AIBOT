"""Research: does the SCHEDULED TIMING of major US macro releases (CPI, NFP, FOMC)
improve out-of-sample classification of the current XAUUSD M5 label?

Diagnostic only. Nothing is tuned and no production strategy is produced.

* Only release timing is used - never an actual, forecast, previous or surprise value.
* Label: current label (TP 1.5 ATR / SL 1.0 ATR / 12 bars), rebuilt with the verified
  research_m5_label_horizon.build_labels. RF parameters are the fixed train_rf_m5.RF_PARAMS.
* Evaluation: existing train/validation boundary plus the same three walk-forward windows
  as every earlier experiment; primary metric = walk-forward balanced accuracy.

Schedule provenance (official sources, archived copies on the Internet Archive):
* CPI  - BLS "Schedule of Releases for the Consumer Price Index"
         https://www.bls.gov/schedule/news_release/cpi.htm (times in Eastern Time)
* NFP  - BLS "Schedule of Releases for the Employment Situation"
         https://www.bls.gov/schedule/news_release/empsit.htm (times in Eastern Time)
* FOMC - Federal Reserve "Meeting calendars and information"
         https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm (dates) and the
         Board's monthly calendars https://www.federalreserve.gov/newsevents/2026-<month>.htm
         ("2:00 p.m. FOMC Meeting" = statement release, Eastern Time)
`known_from_utc` is the capture time of the first archived copy that shows the exact date
and time; `superseded_utc` is the capture time of the first copy showing a different
date/time for the same release. A schedule entry is usable at decision time tau only if
known_from_utc <= tau < superseded_utc. Archive capture times are UTC.

Clocks: XAUUSD `time` is the MT5 bar-open time on the broker server clock, which follows
EET/EEST (IANA Europe/Athens: UTC+2, UTC+3 from 2026-03-29). It is converted to UTC and the
decision time is the bar close, tau = bar open (UTC) + 5 minutes. Release times are converted
from America/New_York to UTC.

Test safety: the guards of research_kronos_m5 are reused (raw/feature CSVs are read only up
to the last purge-gap bar; any attempt to open the test CSV raises immediately).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from backtest_rf_m5 import WARNINGS as BACKTEST_WARNINGS
from backtest_rf_m5 import check_against_validation, generate_signals, load_market, load_validation_period, run_backtest
from features_m5 import BAR_MINUTES
from label_m5 import FEATURES_PATH, RAW_PATH, TARGET_COLUMN, TARGET_NAMES
from research_kronos_m5 import GUARD, assert_no_test_rows, install_guards, rows_through, snapshot_files
from research_m5_feature_families import evaluate, near_duplicates, paired_block_bootstrap
from research_m5_label_horizon import (
    FIXED_RF,
    build_labels,
    check_current_reproduced,
    load_research_data,
    purged_split,
    research_boundary,
)
from research_m5_label_horizon import evaluate as evaluate_rf_only
from research_rf_m5_model_comparison import trade_metrics
from train_rf_m5 import FORBIDDEN_INPUTS, RF_FEATURES, RF_PARAMS, VALIDATION_PATH

SRC_DIR = Path(__file__).resolve().parent
DATA_DIR = SRC_DIR / "data"
FEATURES_OUT = DATA_DIR / "economic_calendar_m5_features.csv"
RESULTS_PATH = DATA_DIR / "economic_calendar_m5_research.csv"
REPORT_PATH = DATA_DIR / "economic_calendar_m5_research_report.txt"

BAR = pd.Timedelta(minutes=BAR_MINUTES)
SERVER_TZ = "Europe/Athens"
EVENT_TZ = "America/New_York"
CLASS_ORDER = [1, -1, 0]
CLASS_LABELS = [TARGET_NAMES[c] for c in CLASS_ORDER]
CHANCE = 1 / 3

WAYBACK = "https://web.archive.org/web/{}/{}"
BLS_CPI_URL = "https://www.bls.gov/schedule/news_release/cpi.htm"
BLS_NFP_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
FED_CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_MONTH_URL = "https://www.federalreserve.gov/newsevents/2026-{}.htm"

# (event, reference period, scheduled Eastern Time, known_from capture, superseded capture,
#  date source, time source, archived copies confirming this exact entry)
_CPI_KNOWN, _NFP_KNOWN = "20260131025646", "20260130204053"
SCHEDULE_ROWS = [
    ("CPI", "December 2025", "2026-01-13 08:30", "20251011012756", None, BLS_CPI_URL, BLS_CPI_URL, 42),
    ("CPI", "January 2026", "2026-02-11 08:30", _CPI_KNOWN, "20260207070202", BLS_CPI_URL, BLS_CPI_URL, 1),
    ("CPI", "January 2026", "2026-02-13 08:30", "20260207070202", None, BLS_CPI_URL, BLS_CPI_URL, 28),
    ("CPI", "February 2026", "2026-03-11 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "March 2026", "2026-04-10 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "April 2026", "2026-05-12 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "May 2026", "2026-06-10 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "June 2026", "2026-07-14 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "July 2026", "2026-08-12 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "August 2026", "2026-09-11 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("CPI", "September 2026", "2026-10-14 08:30", _CPI_KNOWN, None, BLS_CPI_URL, BLS_CPI_URL, 29),
    ("NFP", "December 2025", "2026-01-09 08:30", "20251118191021", None, BLS_NFP_URL, BLS_NFP_URL, 21),
    ("NFP", "January 2026", "2026-02-06 08:30", _NFP_KNOWN, "20260207205057", BLS_NFP_URL, BLS_NFP_URL, 1),
    ("NFP", "January 2026", "2026-02-11 08:30", "20260207205057", None, BLS_NFP_URL, BLS_NFP_URL, 16),
    ("NFP", "February 2026", "2026-03-06 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "March 2026", "2026-04-03 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "April 2026", "2026-05-08 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "May 2026", "2026-06-05 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "June 2026", "2026-07-02 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "July 2026", "2026-08-07 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "August 2026", "2026-09-04 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    ("NFP", "September 2026", "2026-10-02 08:30", _NFP_KNOWN, None, BLS_NFP_URL, BLS_NFP_URL, 17),
    # FOMC: dates on the Fed calendar since the 2024-09-01 capture; statement time from the
    # Board's monthly calendar captured before each meeting (April page was never archived).
    ("FOMC", "January 27-28", "2026-01-28 14:00", "20251231192943", None, FED_CAL_URL,
     FED_MONTH_URL.format("january"), 1),
    ("FOMC", "March 17-18", "2026-03-18 14:00", "20260124000000", None, FED_CAL_URL,
     FED_MONTH_URL.format("march"), 2),
    ("FOMC", "April 28-29", "2026-04-29 14:00", "20240901071426", None, FED_CAL_URL,
     "standing 2:00 p.m. statement time; no pre-meeting archived April calendar page", 0),
    ("FOMC", "June 16-17", "2026-06-17 14:00", "20260124000000", None, FED_CAL_URL,
     FED_MONTH_URL.format("june"), 2),
    ("FOMC", "July 28-29", "2026-07-29 14:00", "20260124000000", None, FED_CAL_URL,
     FED_MONTH_URL.format("july"), 2),
    ("FOMC", "September 15-16", "2026-09-16 14:00", "20260124000000", None, FED_CAL_URL,
     FED_MONTH_URL.format("september"), 1),
    ("FOMC", "October 27-28", "2026-10-28 14:00", "20260123050553", None, FED_CAL_URL,
     FED_MONTH_URL.format("october"), 2),
]
FOMC_DATES_KNOWN = "20240901071426"
SCHEDULE_COLUMNS = {"event", "reference_period", "scheduled_et", "scheduled_utc", "known_from_utc",
                    "superseded_utc", "date_source", "time_source", "archived_copies_confirming"}
FORBIDDEN_NAME_PARTS = ("actual", "forecast", "previous", "consensus", "surprise", "value", "decision", "outcome",
                        "rate", "yield", "dxy")

EVENTS = ["CPI", "NFP", "FOMC"]
PRE_WINDOWS = [("pre60", 30, 60), ("pre30", 15, 30), ("pre15", 5, 15), ("pre5", -1, 5)]      # lo < minutes_until <= hi
POST_WINDOWS = [("post0_5", 0, 5), ("post5_15", 5, 15), ("post15_30", 15, 30), ("post30_60", 30, 60)]  # lo < since <= hi


def feature_names(event: str) -> list[str]:
    e = event.lower()
    return ([f"{e}_release_day", f"{e}_min_until", f"{e}_min_since"]
            + [f"{e}_win_{w}" for w, _, _ in PRE_WINDOWS] + [f"{e}_win_{w}" for w, _, _ in POST_WINDOWS])


FAMILIES = {e: feature_names(e) for e in EVENTS}
FAMILY_NAMES = {"CPI": "CPI timing", "NFP": "NFP timing", "FOMC": "FOMC timing"}
CONFIGS = {"BASELINE": [], "A_CPI": ["CPI"], "B_NFP": ["NFP"], "C_FOMC": ["FOMC"], "D_ALL": ["CPI", "NFP", "FOMC"]}

WF_BOUNDARY_FRACTIONS = (0.55, 0.70, 0.85)
EXPECTED_WF_WINDOWS = [
    ("2026-06-19 03:05:00", "2026-07-23 11:25:00"),
    ("2026-07-23 11:25:00", "2026-08-26 13:55:00"),
    ("2026-08-26 13:55:00", "2026-09-29 17:50:00"),
]
MEANINGFUL_DELTA = 0.01
GAP_ABSOLUTE_WARNING = 0.10
GAP_INCREASE_WARNING = 0.03
LEAKAGE_CHECK_POINTS = 12
TEST_STATEMENT = "The untouched TEST dataset was not loaded, opened or used."


# --------------------------------------------------------------------------
# Schedule and clocks
# --------------------------------------------------------------------------

def capture_time(stamp):
    return pd.NaT if stamp is None else pd.to_datetime(stamp, format="%Y%m%d%H%M%S").tz_localize("UTC")


def load_schedule() -> pd.DataFrame:
    s = pd.DataFrame(SCHEDULE_ROWS, columns=["event", "reference_period", "scheduled_et", "known_from", "superseded",
                                             "date_source", "time_source", "archived_copies_confirming"])
    s["scheduled_utc"] = (pd.to_datetime(s["scheduled_et"], format="%Y-%m-%d %H:%M")
                          .dt.tz_localize(EVENT_TZ, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC"))
    s["known_from_utc"] = [capture_time(v) for v in s.pop("known_from")]
    s["superseded_utc"] = pd.to_datetime(pd.Series([capture_time(v) for v in s.pop("superseded")]), utc=True)
    fomc_dates_known = capture_time(FOMC_DATES_KNOWN)
    fomc = s["event"] == "FOMC"
    s.loc[fomc, "known_from_utc"] = s.loc[fomc, "known_from_utc"].clip(lower=fomc_dates_known)
    assert set(s.columns) == SCHEDULE_COLUMNS, "schedule may only hold timing and provenance columns"
    return s


def server_to_utc(times: pd.Series) -> pd.Series:
    return times.dt.tz_localize(SERVER_TZ, ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")


def to_ns(ts) -> np.ndarray:
    return pd.DatetimeIndex(ts).tz_convert("UTC").tz_localize(None).as_unit("ns").asi8


def ny_day(ns: np.ndarray) -> np.ndarray:
    out = np.full(len(ns), -1, dtype=np.int64)
    ok = ns != np.iinfo(np.int64).min
    days = pd.DatetimeIndex(pd.to_datetime(ns[ok], utc=True)).tz_convert(EVENT_TZ).normalize().tz_localize(None)
    out[ok] = days.as_unit("ns").asi8 // 86_400_000_000_000
    return out


def family_frame(decision_utc: pd.Series, sched: pd.DataFrame, event: str, point_in_time: bool = True) -> pd.DataFrame:
    """Timing features of one event family plus the schedule entries used (diagnostics)."""
    nat = np.iinfo(np.int64).min
    tau = to_ns(decision_utc)
    s = sched[sched["event"] == event].reset_index(drop=True)
    ev, known = to_ns(s["scheduled_utc"]), to_ns(s["known_from_utc"])
    sup = np.where(s["superseded_utc"].isna(), np.iinfo(np.int64).max,
                   to_ns(s["superseded_utc"].fillna(pd.Timestamp("2262-01-01", tz="UTC"))))
    nxt, prv = np.full(len(tau), nat), np.full(len(tau), nat)
    nxt_i, prv_i = np.full(len(tau), -1), np.full(len(tau), -1)
    if point_in_time:
        breaks = np.unique(np.concatenate([known, sup[sup < np.iinfo(np.int64).max]]))
        segment = np.searchsorted(breaks, tau, side="right")
        reps = np.concatenate([[nat], breaks])
    else:
        segment, reps = np.zeros(len(tau), dtype=int), np.array([0])
    for g in np.unique(segment):
        rows = np.flatnonzero(segment == g)
        active = (known <= reps[g]) & (sup > reps[g]) if point_in_time else s["superseded_utc"].isna().to_numpy()
        idx = np.flatnonzero(active)
        idx = idx[np.argsort(ev[idx])]
        times = ev[idx]
        pos = np.searchsorted(times, tau[rows], side="left")
        has_next, has_prev = pos < len(times), pos > 0
        nxt[rows[has_next]], nxt_i[rows[has_next]] = times[pos[has_next]], idx[pos[has_next]]
        prv[rows[has_prev]], prv_i[rows[has_prev]] = times[pos[has_prev] - 1], idx[pos[has_prev] - 1]
    e = event.lower()
    until = np.where(nxt != nat, (nxt - tau) / 60e9, np.nan)
    since = np.where(prv != nat, (tau - prv) / 60e9, np.nan)
    today = ny_day(tau)
    out = pd.DataFrame({f"{e}_release_day": ((ny_day(nxt) == today) | (ny_day(prv) == today)).astype(float),
                        f"{e}_min_until": until, f"{e}_min_since": since})
    for name, lo, hi in PRE_WINDOWS:
        out[f"{e}_win_{name}"] = ((until > lo) & (until <= hi)).astype(float)
    for name, lo, hi in POST_WINDOWS:
        out[f"{e}_win_{name}"] = ((since > lo) & (since <= hi)).astype(float)
    out.loc[np.isnan(until) | np.isnan(since), FAMILIES[event]] = np.nan
    out[f"_{e}_next_idx"], out[f"_{e}_prev_idx"] = nxt_i, prv_i
    return out


def calendar_features(decision_utc: pd.Series, sched: pd.DataFrame, point_in_time: bool = True) -> pd.DataFrame:
    return pd.concat([family_frame(decision_utc, sched, e, point_in_time) for e in EVENTS], axis=1)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_utc_conversion(times: pd.Series, sched: pd.DataFrame) -> list[str]:
    anchors = {("CPI", "2026-02-13 08:30"): "2026-02-13 13:30", ("CPI", "2026-03-11 08:30"): "2026-03-11 12:30",
               ("NFP", "2026-07-02 08:30"): "2026-07-02 12:30", ("FOMC", "2026-03-18 14:00"): "2026-03-18 18:00",
               ("FOMC", "2026-09-16 14:00"): "2026-09-16 18:00"}
    for (event, et), utc in anchors.items():
        got = sched.loc[(sched.event == event) & (sched.scheduled_et == et), "scheduled_utc"].iloc[0]
        assert got == pd.Timestamp(utc, tz="UTC"), f"{event} {et} ET converted to {got}"
    assert server_to_utc(pd.Series(pd.to_datetime(["2026-02-20 15:30", "2026-03-20 14:30", "2026-07-14 15:30"]))
                         ).tolist() == [pd.Timestamp(x, tz="UTC") for x in ["2026-02-20 13:30", "2026-03-20 12:30",
                                                                             "2026-07-14 12:30"]]
    # The spot-gold daily session reopens at 18:00 New York time. Locate each weekday reopen
    # (first bar after a 30 min - 6 h gap around the server midnight) and convert it under
    # three candidate server clocks; only the correct clock maps (almost) every reopen to 18:00 NY.
    gap = times.diff()
    reopen = times[(gap > pd.Timedelta(minutes=30)) & (gap < pd.Timedelta(hours=6))
                   & times.dt.hour.isin([0, 1]) & (times.dt.day_of_week < 5)]
    candidates = {
        "EET/EEST (Europe/Athens)": server_to_utc(reopen),
        "fixed UTC+2": (reopen - pd.Timedelta(hours=2)).dt.tz_localize("UTC"),
        "New York + 7 h": (reopen - pd.Timedelta(hours=7)).dt.tz_localize(EVENT_TZ).dt.tz_convert("UTC"),
    }
    share = {k: float((v.dt.tz_convert(EVENT_TZ).dt.strftime("%H:%M") == "18:00").mean()) for k, v in candidates.items()}
    best = max(share, key=share.get)
    assert best == "EET/EEST (Europe/Athens)" and share[best] >= 0.95, f"server clock check failed: {share}"
    return [f"{len(reopen)} daily reopens mapped to 18:00 New York: " + ", ".join(f"{k} {v:.1%}" for k, v in share.items())]


def prefix_invariance(times_utc: pd.Series, sched: pd.DataFrame, full: pd.DataFrame, cols, check_taus) -> tuple[int, int]:
    detected, compared = 0, 0
    for tau in check_taus:
        sub = times_utc[times_utc <= tau].reset_index(drop=True)
        known = sched[sched["known_from_utc"] <= tau]
        prefix = calendar_features(sub, known)[cols].to_numpy(float)
        ref = full.iloc[:len(sub)][cols].to_numpy(float)
        compared += prefix.size
        detected += bool((~np.isclose(prefix, ref, equal_nan=True)).any())
    return detected, compared


def entries_used_known(feat: pd.DataFrame, decision_utc: pd.Series, sched: pd.DataFrame) -> int:
    tau = to_ns(decision_utc)
    n = 0
    for e in EVENTS:
        s = sched[sched.event == e].reset_index(drop=True)
        ev, known = to_ns(s["scheduled_utc"]), to_ns(s["known_from_utc"])
        sup = s["superseded_utc"]
        for kind in ("next", "prev"):
            idx = feat[f"_{e.lower()}_{kind}_idx"].to_numpy()
            assert (idx >= 0).all(), f"{e}: a research row has no {kind} scheduled event"
            assert (known[idx] <= tau).all(), f"{e}: a schedule entry was used before it was published"
            sup_ns = np.where(sup.isna().to_numpy()[idx], np.iinfo(np.int64).max,
                              to_ns(sup.fillna(pd.Timestamp("2262-01-01", tz="UTC")))[idx])
            assert (sup_ns > tau).all(), f"{e}: a superseded schedule entry was used after its revision"
            if kind == "next":
                assert (ev[idx] >= tau).all()
            else:
                assert (ev[idx] < tau).all(), f"{e}: 'since' refers to an event that had not happened"
            n += len(idx)
    return n


# --------------------------------------------------------------------------
# Summary and report
# --------------------------------------------------------------------------

def summarize(ev: pd.DataFrame, boot: dict) -> pd.DataFrame:
    bal = ev.pivot(index="config", columns="evaluation", values="val_balanced_accuracy").reindex(list(CONFIGS))
    gap = ev.pivot(index="config", columns="evaluation", values="train_val_gap").reindex(list(CONFIGS))
    wf = ["WF1", "WF2", "WF3"]
    base = bal.loc["BASELINE"]
    rows = []
    for name in CONFIGS:
        delta = bal.loc[name] - base
        better, worse = int((delta[wf] > MEANINGFUL_DELTA).sum()), int((delta[wf] < -MEANINGFUL_DELTA).sum())
        row = {"section": "summary", "config": name, "families": "+".join(CONFIGS[name]) or "-",
               "feature_count": int(ev[ev.config == name]["feature_count"].iloc[0]),
               "main_val_balanced_accuracy": bal.loc[name, "main"],
               **{f"{w}_val_balanced_accuracy": bal.loc[name, w] for w in wf},
               "wf_mean_balanced_accuracy": bal.loc[name, wf].mean(),
               "wf_std_balanced_accuracy": bal.loc[name, wf].std(ddof=1),
               "main_gap": gap.loc[name, "main"], "wf_mean_gap": gap.loc[name, wf].mean(),
               "delta_main": delta["main"], **{f"delta_{w}": delta[w] for w in wf}, "delta_wf_mean": delta[wf].mean(),
               "wf_windows_better": better, "wf_windows_worse": worse}
        for e in ["main"] + wf:
            row[f"delta_{e}_ci_low"], row[f"delta_{e}_ci_high"] = boot.get((name, e), (np.nan, np.nan))
        row["wf_ci_all_above_zero"] = (name != "BASELINE") and all(row[f"delta_{w}_ci_low"] > 0 for w in wf)
        warnings = []
        if name == "BASELINE":
            verdict = "-"
        else:
            verdict = ("CONSISTENT IMPROVEMENT" if better == 3 else "PARTIAL IMPROVEMENT" if better >= 2 and worse == 0
                       else "WORSE" if worse >= 2 else "NO CONSISTENT IMPROVEMENT")
            if row["main_gap"] > gap.loc["BASELINE", "main"] + GAP_INCREASE_WARNING:
                warnings.append(f"main gap exceeds baseline gap by > {GAP_INCREASE_WARNING}")
            if row["wf_mean_gap"] > gap.loc["BASELINE", wf].mean() + GAP_INCREASE_WARNING:
                warnings.append(f"walk-forward gap exceeds baseline by > {GAP_INCREASE_WARNING}")
            if delta["main"] > MEANINGFUL_DELTA and delta[wf].mean() <= MEANINGFUL_DELTA:
                warnings.append("main-split gain not confirmed by walk-forward mean")
        if row["main_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"main gap {row['main_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        if row["wf_mean_gap"] > GAP_ABSOLUTE_WARNING:
            warnings.append(f"walk-forward mean gap {row['wf_mean_gap']:.3f} > {GAP_ABSOLUTE_WARNING}")
        row["verdict"], row["warnings"] = verdict, "; ".join(warnings) or "none"
        rows.append(row)
    return pd.DataFrame(rows)


def pct(v) -> str:
    return "-" if pd.isna(v) else f"{v:.1%}"


def eval_table(ev: pd.DataFrame, evaluation: str) -> str:
    sub = ev[ev["evaluation"] == evaluation].set_index("config").reindex(list(CONFIGS))
    cols = ["feature_count", "train_rows", "val_rows", "train_balanced_accuracy", "val_balanced_accuracy",
            "train_val_gap", "val_macro_f1", "buy_precision", "buy_recall", "sell_precision", "sell_recall",
            "wait_precision", "wait_recall"]
    t = sub[cols].copy()
    for c in cols[3:]:
        t[c] = t[c].map(lambda v, c=c: f"{v:+.4f}" if c == "train_val_gap" else f"{v:.4f}" if c == "val_macro_f1"
                        else pct(v))
    t[cols[:3]] = t[cols[:3]].astype(int)
    return t.to_string()


def audit_lines(audit: pd.DataFrame) -> list[str]:
    L = []
    for _, a in audit.iterrows():
        L.append(f"   [{a['case']}]")
        L.append(f"     XAUUSD bar {a['xau_server_time']} server = {a['xau_bar_utc']} UTC; decision (bar close) "
                 f"{a['decision_utc']} UTC")
        L.append(f"     event {a['event']} {a['relation']}: scheduled {a['scheduled_et']} ET = {a['scheduled_utc']} UTC; "
                 f"{a['minutes']}")
        L.append(f"     features: {a['feature_values']}")
        L.append(f"     known because: {a['known_reason']}")
    return L


def build_report(ev, summary, backtest, sched, audit, wf_windows, boundary, checks, confusions) -> list[str]:
    val_start, val_end, _ = boundary
    s = summary.set_index("config")
    wf = ["WF1", "WF2", "WF3"]
    L = ["XAUUSD M5 scheduled economic-calendar timing research (classification diagnostic only)", "=" * 84,
         TEST_STATEMENT,
         "Question: does knowing the scheduled timing of CPI, NFP and FOMC releases improve walk-forward",
         "out-of-sample balanced accuracy of the existing 12-bar label? Only release TIMING is used.",
         "Label: current triple-barrier label (TP 1.5 ATR, SL 1.0 ATR, 12 bars), unchanged.",
         "Fixed RF for every configuration: " + ", ".join(f"{k}={v}" for k, v in RF_PARAMS.items()),
         f"Rows: {checks['research_rows']} labeled research rows, identical for every configuration (no row dropped).",
         ""]

    L += ["1. HISTORICAL CALENDAR SOURCE",
          "   No economic calendar existed in the project or environment. Official primary sources were used:",
          f"   CPI : U.S. Bureau of Labor Statistics, Schedule of Releases for the Consumer Price Index ({BLS_CPI_URL})",
          f"   NFP : U.S. Bureau of Labor Statistics, Schedule of Releases for the Employment Situation ({BLS_NFP_URL})",
          f"   FOMC: Federal Reserve Board, FOMC meeting calendar ({FED_CAL_URL}) for dates and the Board's monthly",
          "         calendars (newsevents/2026-<month>.htm, '2:00 p.m. FOMC Meeting') for the statement release time.",
          "   Point-in-time versions were reconstructed from Internet Archive (web.archive.org) captures of those pages:",
          f"   {checks['captures']}",
          "   Each entry's known_from is the capture time of the first copy showing that exact date and time; an entry is",
          "   usable only from known_from until the capture that first shows a different date/time (superseded).",
          "   Post-hoc confirmation: BLS archives list every 2026 CPI and Employment Situation release as published; the five",
          "   2026 FOMC statements in range carry 'For release at 2:00 p.m. EDT'. No actual/forecast/previous value is",
          "   stored anywhere in this experiment.", ""]

    L += ["2. TIMEZONES AND CONVERSION",
          "   Event source timezone: US Eastern Time (America/New_York; EST UTC-5 until 2026-03-08, EDT UTC-4 after).",
          "   XAUUSD source timezone: MT5 broker server clock = EET/EEST (Europe/Athens; UTC+2, UTC+3 from 2026-03-29).",
          "     Evidence: (a) the spot-gold daily reopen (18:00 New York) lands at server 01:00 in winter, 00:00 between",
          "     the US (03-08) and EU (03-29) DST changes and 01:00 again after - only EET/EEST explains all three;",
          "     (b) the six FX pairs downloaded in the previous experiment close every Friday at 17:00 New York under the",
          "     same mapping; (c) the MT5 terminal's last EURUSD tick on Friday 2026-11-06 (after both DST ends) is 23:59:55",
          "     server = 21:59:55 UTC = 16:59:55 New York.",
          "   Conversion: XAUUSD bar time (server) -> tz_localize(Europe/Athens) -> UTC; the decision time is the bar close,",
          "   tau = bar open (UTC) + 5 min, the moment the bar's features become available. Release time (ET) ->",
          "   tz_localize(America/New_York) -> UTC. All comparisons are done in UTC.",
          f"   Automated check: {checks['utc'][0]}", ""]

    L += ["3. EVENT DEFINITIONS AND HISTORICAL SCHEDULED TIMESTAMPS",
          "   CPI  = BLS Consumer Price Index news release (08:30 ET).",
          "   NFP  = BLS Employment Situation news release (nonfarm payrolls; 08:30 ET).",
          "   FOMC = FOMC policy statement release on the final day of each scheduled meeting (14:00 ET).",
          "   Server time = XAUUSD file clock. superseded = date/time later revised by the source."]
    t = sched.copy()
    t["scheduled_server"] = t["scheduled_utc"].dt.tz_convert(SERVER_TZ).dt.strftime("%Y-%m-%d %H:%M")
    t["scheduled_utc"] = t["scheduled_utc"].dt.strftime("%Y-%m-%d %H:%M")
    t["known_from_utc"] = t["known_from_utc"].dt.strftime("%Y-%m-%d %H:%M")
    t["superseded_utc"] = t["superseded_utc"].dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    L += ["   " + line for line in t[["event", "reference_period", "scheduled_et", "scheduled_utc", "scheduled_server",
                                       "known_from_utc", "superseded_utc", "archived_copies_confirming"]]
          .to_string(index=False).splitlines()]
    L += ["   Schedule revisions: the January 2026 CPI (02-11 -> 02-13) and Employment Situation (02-06 -> 02-11) were",
          "   rescheduled; the revised dates first appear in the 2026-02-07 captures. The first research row",
          f"   ({checks['first_research_row']} server) is after every known_from, so revisions affect no research row; the",
          "   point-in-time logic is still applied row by row (see leakage check 3 and the control audit case).",
          "   FOMC dates were on the Fed calendar from the 2024-09-01 capture, unchanged in every monthly capture through",
          "   2026-09. Release times: CPI/NFP times are in the BLS tables; FOMC 2:00 p.m. appears on the pre-meeting",
          "   monthly calendars for January, March, June, July, September and October. LIMITATION: no pre-meeting copy",
          "   of the April 2026 monthly page exists; its 2:00 p.m. time rests on the standing practice shown for every",
          "   other meeting and on the statement header (post hoc). The date itself was known since 2024.", ""]

    L += ["4. EVENT-WINDOW DEFINITIONS (fixed before any result)",
          "   minutes_until = scheduled time - tau (next scheduled release at or after tau);",
          "   minutes_since = tau - scheduled time (last scheduled release strictly before tau).",
          "   pre60: 30 < until <= 60   pre30: 15 < until <= 30   pre15: 5 < until <= 15   pre5: 0 <= until <= 5",
          "   post0_5: 0 < since <= 5   post5_15: 5 < since <= 15   post15_30: 15 < since <= 30   post30_60: 30 < since <= 60",
          "   With tau on the 5-minute grid, pre5 covers the bar ending at the release and the one before; post0_5 is the",
          "   bar that contains the release (decision 5 minutes after it). Windows are non-overlapping.", ""]

    L += ["5. FEATURES (11 per event family; all derived only from scheduled timestamps)"]
    for e in EVENTS:
        n = e.lower()
        L += [f"   {FAMILY_NAMES[e]}:",
              f"     {n}_release_day   1 if a scheduled {e} release falls on tau's New York calendar date",
              f"     {n}_min_until     minutes until the next scheduled {e} release",
              f"     {n}_min_since     minutes since the last scheduled {e} release",
              f"     {n}_win_pre60 / pre30 / pre15 / pre5 / post0_5 / post5_15 / post15_30 / post30_60   window flags"]
    L.append("")

    L += ["6. CONFIGURATIONS"] + [f"   {n:<9} {int(s.loc[n, 'feature_count']):3d} features  "
                                  + ("BASELINE + " + " + ".join(FAMILY_NAMES[f] for f in CONFIGS[n]) if CONFIGS[n]
                                     else "existing 30 RF_FEATURES") for n in CONFIGS] + [""]

    L += [f"7. MAIN SPLIT (existing boundary; validation {val_start} -> {val_end})", eval_table(ev, "main"), "",
          "   Confusion matrices (rows = true BUY/SELL/WAIT, columns = predicted BUY/SELL/WAIT):"]
    L += [f"   {n:<9} " + " | ".join(" ".join(f"{v:5d}" for v in row) for row in cm) for n, cm in confusions.items()]
    L.append("")

    L += ["8. WALK-FORWARD RESULTS (expanding train, 12-bar purge; same windows as all earlier experiments)"]
    L += [f"   WF{i}: validation {a} -> {b}" for i, (a, b) in enumerate(wf_windows, 1)]
    for w in wf:
        L += [f"\n   {w}", eval_table(ev, w)]
        L += [f"   confusion {n:<9} " + ev[(ev.config == n) & (ev.evaluation == w)]["confusion_matrix"].iloc[0]
              for n in CONFIGS]
    dist = ev[ev.config == "BASELINE"].set_index("evaluation")
    L += ["", "   Class distribution (identical rows for every configuration):",
          "   " + "evaluation  train BUY/SELL/WAIT        validation BUY/SELL/WAIT"]
    L += [f"   {e:<10}  {pct(dist.loc[e, 'buy_train_share'])} / {pct(dist.loc[e, 'sell_train_share'])} / "
          f"{pct(dist.loc[e, 'wait_train_share'])}       {pct(dist.loc[e, 'buy_val_share'])} / "
          f"{pct(dist.loc[e, 'sell_val_share'])} / {pct(dist.loc[e, 'wait_val_share'])}" for e in ["main"] + wf]
    L.append("")

    t = s[["feature_count", "main_val_balanced_accuracy"] + [f"{w}_val_balanced_accuracy" for w in wf]
          + ["wf_mean_balanced_accuracy", "wf_std_balanced_accuracy"]].copy()
    t.columns = ["features", "main", *wf, "wf_mean", "wf_std"]
    for c in t.columns[1:]:
        t[c] = t[c].map(lambda v: f"{v:.4f}")
    L += ["9. WALK-FORWARD BALANCED ACCURACY: MEAN AND STANDARD DEVIATION (sample std, n=3)", t.to_string(),
          f"   Chance level {CHANCE:.4f}.", ""]

    L += ["10. CHANGE VERSUS BASELINE (config - baseline; 95% paired block-bootstrap interval, 288-bar blocks, 1000 draws)",
          "   The main validation period overlaps WF3, so main and WF3 are not independent evidence."]
    for n in list(CONFIGS)[1:]:
        r = s.loc[n]
        L.append(f"   {n}: " + "; ".join(f"{e} {r[f'delta_{e}']:+.4f} [{r[f'delta_{e}_ci_low']:+.4f}, "
                                         f"{r[f'delta_{e}_ci_high']:+.4f}]" for e in ["main"] + wf))
        L.append(f"      walk-forward mean delta {r['delta_wf_mean']:+.4f}; better by > {MEANINGFUL_DELTA} in "
                 f"{int(r['wf_windows_better'])}/3 windows, worse in {int(r['wf_windows_worse'])}/3; "
                 f"CI above zero in all 3 windows: {'yes' if r['wf_ci_all_above_zero'] else 'no'}")
    L.append("")

    L += ["11. GENERALIZATION / OVERFITTING WARNINGS (rules fixed before running)"]
    L += [f"   {n:<9} gap main {s.loc[n, 'main_gap']:+.4f}, walk-forward mean {s.loc[n, 'wf_mean_gap']:+.4f}: "
          f"{s.loc[n, 'warnings']}" for n in CONFIGS]
    for fam, d in checks["near_duplicates"].items():
        L.append(f"   {FAMILY_NAMES[fam]} near-duplicates of baseline features (|r| > 0.95): " +
                 (", ".join(f"{c} ~ {b} ({v:.3f})" for c, (b, v) in d.items()) or "none"))
    L += [f"   Event coverage in the research rows: {checks['coverage']}", ""]

    L += ["12. POINT-IN-TIME AUDIT"] + audit_lines(audit) + [""]
    L += ["13. LEAKAGE, TEST-DATA SAFETY AND FILE INTEGRITY CHECKS"] + [f"   {c}" for c in checks["lines"]] + [""]

    L += ["14. DECISION",
          f"   Rule: CONSISTENT = better by > {MEANINGFUL_DELTA} in all 3 walk-forward windows; PARTIAL = 2/3 with none "
          f"worse by > {MEANINGFUL_DELTA}; WORSE = worse in >= 2/3. A higher mean alone is not an improvement."]
    L += [f"   {n:<9} {s.loc[n, 'verdict']}" for n in list(CONFIGS)[1:]]
    L += [f"   {line}" for line in checks["verdict_lines"]]
    L += ["   Four configurations were compared on the same windows; the best-looking delta is optimistically biased.", ""]

    L += ["15. LIMITATIONS",
          "   - Schedule vintages are bounded by archive capture times: known_from is the first capture showing an entry,",
          "     so the real publication was earlier (conservative). Supersession uses the first capture showing the",
          "     change; in the 2026-01-31..02-07 interval the old entry stays active, which affects no research row.",
          "   - April 2026 FOMC release time lacks a pre-meeting archived source (see section 3).",
          "   - The server-clock mapping is inferred from market-structure anchors (daily reopen, FX weekly close, live",
          "     terminal tick); it is consistent for every week but is not a broker-published statement.",
          "   - Release times are scheduled times; actual publication could deviate by seconds. Unscheduled events",
          "     (speeches, intermeeting actions) are excluded by design.",
          "   - Only 8 CPI, 8 NFP and 5 FOMC releases fall inside the research rows; each walk-forward window contains",
          "     roughly one or two of each, so event-window flags are active on very few rows (section 11).", ""]

    bt = backtest.set_index("config").reindex(list(CONFIGS))
    L += ["APPENDIX - SECONDARY BACKTEST DIAGNOSTIC (main validation period; NOT used for selection)",
          "   Unchanged backtest_rf_m5 engine; models from the main split. $ per ounce; drawdown = closed-trade equity."]
    t = pd.DataFrame({
        "trades": bt["trades"].astype(int), "net_pnl": bt["net_pnl"].map("{:.2f}".format),
        "avg_r": bt["avg_r"].map("{:+.4f}".format), "profit_factor": bt["profit_factor"].map("{:.3f}".format),
        "max_dd": bt["max_closed_trade_dd"].map("{:.2f}".format), "buy_trades": bt["buy_trades"].astype(int),
        "buy_net": bt["buy_net_pnl"].map("{:.2f}".format), "sell_trades": bt["sell_trades"].astype(int),
        "sell_net": bt["sell_net_pnl"].map("{:.2f}".format)})
    L += [t.to_string(), "   One validation period; P&L differences between configurations are not evidence of edge."]
    L += [f"   - {w}" for w in BACKTEST_WARNINGS]
    L += ["", "No production strategy is recommended. All results are research diagnostics.", TEST_STATEMENT]
    return L


# --------------------------------------------------------------------------
# Point-in-time audit
# --------------------------------------------------------------------------

def build_audit(features, cal, decision_utc, sched, control_rows) -> pd.DataFrame:
    s = sched.reset_index(drop=True)

    def row_at(server_time):
        hit = np.flatnonzero(features["time"].to_numpy() == np.datetime64(pd.Timestamp(server_time)))
        assert len(hit) == 1, f"audit bar {server_time} not found"
        return int(hit[0])

    def bar_for_decision(event, et, offset_min):
        e_utc = s.loc[(s.event == event) & (s.scheduled_et == et), "scheduled_utc"].iloc[0]
        bar_utc = e_utc + pd.Timedelta(minutes=offset_min) - BAR
        return bar_utc.tz_convert(SERVER_TZ).tz_localize(None)

    cases = [("normal non-event period", "FOMC", row_at("2026-05-20 12:00")),
             ("normal non-event period", "CPI", row_at("2026-08-25 18:00"))]
    for event, et, offs in [("CPI", "2026-07-14 08:30", [-60, -15, 0, 5]), ("NFP", "2026-08-07 08:30", [-30, -5, 15, 60]),
                            ("FOMC", "2026-09-16 14:00", [-60, 5, 30])]:
        for o in offs:
            label = "pre-event" if o <= 0 else "immediate post-event" if o <= 15 else "post-event"
            cases.append((f"{label} ({o:+d} min)", event, row_at(bar_for_decision(event, et, o))))
    cases.append(("US/EU DST mismatch week, post-event (+5 min)", "CPI", row_at(bar_for_decision("CPI", "2026-03-11 08:30", 5))))
    t = features["time"]
    gap = t.diff()
    weekend = np.flatnonzero((gap > pd.Timedelta(hours=24)).to_numpy() & (t.dt.date.astype(str) == "2026-06-01").to_numpy())
    cases.append(("market closure: first bar after the weekend, NFP week", "NFP", int(weekend[0])))
    daily = np.flatnonzero(((gap > pd.Timedelta(minutes=30)) & (gap < pd.Timedelta(hours=6))).to_numpy()
                           & (t.dt.date.astype(str) == "2026-09-16").to_numpy())
    cases.append(("market closure: first bar after the daily break, FOMC day", "FOMC", int(daily[0])))

    out = []
    for case, event, i in cases:
        out.append(audit_record(case, event, features["time"].iloc[i], decision_utc.iloc[i], cal.iloc[i], s))
    for case, event, server_time, tau, frame in control_rows:
        out.append(audit_record(case, event, server_time, tau, frame, s))
    return pd.DataFrame(out)


def audit_record(case, event, server_time, tau, frow, s) -> dict:
    e = event.lower()
    until, since = frow[f"{e}_min_until"], frow[f"{e}_min_since"]
    use_next = until <= since
    idx = int(frow[f"_{e}_next_idx" if use_next else f"_{e}_prev_idx"])
    entry = s[s["event"] == event].reset_index(drop=True).iloc[idx]
    flags = [c.replace(f"{e}_win_", "") for c in FAMILIES[event] if "_win_" in c and frow[c] == 1]
    sup = "never revised" if pd.isna(entry.superseded_utc) else f"revised at {entry.superseded_utc:%Y-%m-%d %H:%M} UTC"
    reason = (f"entry first archived {entry.known_from_utc:%Y-%m-%d %H:%M} UTC <= decision {tau:%Y-%m-%d %H:%M} UTC; "
              f"{sup}; source {entry.date_source}")
    if entry.event == "FOMC":
        reason += f"; time source {entry.time_source}"
    return {"case": case, "event": event, "relation": "next release" if use_next else "last release",
            "xau_server_time": f"{pd.Timestamp(server_time):%Y-%m-%d %H:%M}",
            "xau_bar_utc": f"{tau - BAR:%Y-%m-%d %H:%M}", "decision_utc": f"{tau:%Y-%m-%d %H:%M}",
            "scheduled_et": entry.scheduled_et, "scheduled_utc": f"{entry.scheduled_utc:%Y-%m-%d %H:%M}",
            "minutes": f"minutes until {until:.0f}, minutes since {since:.0f}",
            "feature_values": f"{e}_release_day={frow[f'{e}_release_day']:.0f}, {e}_min_until={until:.0f}, "
                              f"{e}_min_since={since:.0f}, active windows={flags or 'none'}",
            "known_reason": reason}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    outputs = [FEATURES_OUT, RESULTS_PATH, REPORT_PATH]
    for path in outputs:
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing file {path}")
    skip = {p.resolve() for p in outputs} | {Path(__file__).resolve()}
    hashes_before, test_stat_before = snapshot_files(skip)
    install_guards()
    assert RF_PARAMS == FIXED_RF, "train_rf_m5.RF_PARAMS differs from the fixed research configuration"

    boundary = research_boundary()
    val_start, val_end, cutoff = boundary
    GUARD["cutoff"] = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    for path in (RAW_PATH, FEATURES_PATH):
        GUARD["safe_nrows"][path.resolve()] = rows_through(path, GUARD["cutoff"])
    raw, features, positions = load_research_data(val_end, cutoff)
    assert_no_test_rows(raw)
    assert_no_test_rows(features)
    for frame in (raw, features):
        assert frame["time"].is_unique and frame["time"].is_monotonic_increasing, "duplicate XAUUSD timestamps"

    times = features["time"]
    starts = [times.iloc[int(len(times) * f)] for f in WF_BOUNDARY_FRACTIONS]
    wf_windows = [(starts[i], starts[i + 1] if i + 1 < len(starts) else val_end) for i in range(len(starts))]
    assert [(str(a), str(b)) for a, b in wf_windows] == EXPECTED_WF_WINDOWS, "walk-forward windows changed"

    sched = load_schedule()
    for e in EVENTS:
        active = sched[(sched.event == e) & sched.superseded_utc.isna()]
        assert active["scheduled_utc"].is_unique and sched[sched.event == e]["scheduled_utc"].is_unique, \
            f"duplicate {e} timestamps"
    utc_lines = check_utc_conversion(raw["time"], sched)
    times_utc = server_to_utc(times)
    assert times_utc.is_unique and times_utc.is_monotonic_increasing, "duplicate/unsorted UTC timestamps"
    decision_utc = times_utc + BAR

    cal = calendar_features(decision_utc, sched)
    cal_cols = [c for cols in FAMILIES.values() for c in cols]
    assert not set(cal_cols) & set(features.columns)
    assert not any(p in c for c in cal_cols + list(sched.columns) for p in FORBIDDEN_NAME_PARTS
                   if c not in {"reference_period"}), "a feature or schedule column suggests an economic value"
    assert all(pd.api.types.is_datetime64_any_dtype(sched[c]) or pd.api.types.is_string_dtype(sched[c])
               or c == "archived_copies_confirming" for c in sched.columns), "schedule holds a non-timing value"

    labels = build_labels(raw, features, positions, 1.5, 1.0, 12)
    keep = ~labels["excluded"].to_numpy()
    full_labeled = features[keep].assign(**{TARGET_COLUMN: labels.loc[keep, TARGET_COLUMN].to_numpy()})
    train_full, val_full = purged_split(full_labeled, 12, val_start, val_end, inclusive_stop=True)
    _, _, model_full = evaluate_rf_only(train_full, val_full)
    check_current_reproduced(labels, train_full, val_full, model_full)
    print("existing pipeline reproduced (labels, splits, saved model)")

    research_cal = cal[keep].reset_index(drop=True)
    assert np.isfinite(research_cal[cal_cols].to_numpy(float)).all(), "a research row lacks a scheduled event"
    research = pd.concat([full_labeled.reset_index(drop=True), research_cal[cal_cols]], axis=1)
    research_tau = decision_utc[keep].reset_index(drop=True)
    n_entries = entries_used_known(research_cal, research_tau, sched)
    first_row_tau = research_tau.min()
    assert (sched["known_from_utc"] <= first_row_tau).all()

    # Leakage checks on the calendar features.
    check_taus = [research_tau.iloc[int(f * (len(research_tau) - 1))] for f in np.linspace(0.05, 1.0, LEAKAGE_CHECK_POINTS)]
    detected, compared = prefix_invariance(decision_utc, sched, cal, cal_cols, check_taus)
    assert detected == 0, "calendar features changed when future data / later schedule entries were removed"
    again = calendar_features(decision_utc.iloc[::-1].reset_index(drop=True), sched).iloc[::-1].reset_index(drop=True)
    assert np.array_equal(again[cal_cols].to_numpy(float), cal[cal_cols].to_numpy(float), equal_nan=True), \
        "calendar features are not deterministic"
    final_sched = calendar_features(decision_utc, sched, point_in_time=False)
    assert np.array_equal(final_sched[keep][cal_cols].to_numpy(float), research_cal[cal_cols].to_numpy(float)), \
        "schedule revisions would change a research row"
    control_taus = pd.Series(pd.to_datetime(["2026-02-05 12:00", "2026-02-10 14:00"]).tz_localize("UTC"))
    pit, leaky = calendar_features(control_taus, sched), calendar_features(control_taus, sched, point_in_time=False)
    differs = (~np.isclose(pit[cal_cols].to_numpy(float), leaky[cal_cols].to_numpy(float), equal_nan=True)).any(axis=1)
    assert differs[0] and not differs[1], "point-in-time control failed to track the January 2026 reschedule"
    print(f"calendar leakage checks passed ({compared:,} values; revision control passed)")

    cols_by_config = {n: RF_FEATURES + [c for f in fams for c in FAMILIES[f]] for n, fams in CONFIGS.items()}
    for n, cols in cols_by_config.items():
        assert len(cols) == len(set(cols)) and not FORBIDDEN_INPUTS & set(cols), n
    splits = {"main": purged_split(research, 12, val_start, val_end, inclusive_stop=True)}
    for i, (a, b) in enumerate(wf_windows, 1):
        splits[f"WF{i}"] = purged_split(research, 12, a, b, inclusive_stop=i == 3)
    assert np.array_equal(splits["main"][1]["time"].to_numpy(), val_full["time"].to_numpy())
    assert np.array_equal(splits["main"][0]["time"].to_numpy(), train_full["time"].to_numpy())

    rows, confusions, preds, main_models = [], {}, {}, {}
    for name in CONFIGS:
        for ev_name, (train, val) in splits.items():
            out, cm, model, y_val, p_val = evaluate(train, val, cols_by_config[name])
            out["val_macro_f1"] = f1_score(y_val, p_val, labels=CLASS_ORDER, average="macro")
            y_tr = train[TARGET_COLUMN].to_numpy()
            for cls, lab in zip(CLASS_ORDER, CLASS_LABELS):
                out[f"{lab.lower()}_train_share"] = float((y_tr == cls).mean())
            rows.append({"section": "evaluation", "config": name, "evaluation": ev_name,
                         "families": "+".join(CONFIGS[name]) or "-", **out})
            preds[(name, ev_name)] = (y_val, p_val)
            if ev_name == "main":
                confusions[name], main_models[name] = cm, model
        print(f"finished {name:<9} features {len(cols_by_config[name])}  main {rows[-4]['val_balanced_accuracy']:.4f}  "
              f"walk-forward {' / '.join(f'{r['val_balanced_accuracy']:.4f}' for r in rows[-3:])}")
    ev = pd.DataFrame(rows)
    base_pred = model_full.predict(val_full[RF_FEATURES])
    assert np.array_equal(preds[("BASELINE", "main")][1], base_pred), "baseline predictions do not reproduce"
    for e in splits:
        assert all(np.array_equal(preds[(n, e)][0], preds[("BASELINE", e)][0]) for n in CONFIGS), "labels differ"

    boot = {}
    for name in list(CONFIGS)[1:]:
        for e in splits:
            y, p = preds[(name, e)]
            boot[(name, e)] = paired_block_bootstrap(y, p, preds[("BASELINE", e)][1])
    summary = summarize(ev, boot)
    dupes = near_duplicates(splits["main"][0], FAMILIES)

    # Secondary backtest diagnostic with the unchanged engine.
    val_bt, bt_start, bt_end = load_validation_period(VALIDATION_PATH)
    raw_bt, feats_bt, pos_bt, _ = load_market(bt_start, bt_end)
    assert_no_test_rows(raw_bt)
    check_against_validation(feats_bt, val_bt, RF_FEATURES)
    cal_bt = calendar_features(server_to_utc(feats_bt["time"]) + BAR, sched)
    feats_bt = pd.concat([feats_bt.reset_index(drop=True), cal_bt[cal_cols]], axis=1)
    assert np.isfinite(feats_bt[cal_cols].to_numpy(float)).all()
    bt_rows = []
    for name, model in main_models.items():
        trades, _ = run_backtest(raw_bt, feats_bt, pos_bt, generate_signals(model, feats_bt, cols_by_config[name]))
        m = trade_metrics(trades)
        for side in ("BUY", "SELL"):
            m.update(trade_metrics(trades[trades["side"] == side], prefix=f"{side.lower()}_"))
        bt_rows.append({"section": "backtest", "config": name, "evaluation": "main_validation_backtest", **m})
    backtest = pd.DataFrame(bt_rows)

    control_rows = [("CONTROL (not a research row): before the January 2026 reschedule became public", "NFP",
                     control_taus.iloc[0].tz_convert(SERVER_TZ).tz_localize(None) - BAR, control_taus.iloc[0], pit.iloc[0]),
                    ("CONTROL (not a research row): after the reschedule, before the release", "NFP",
                     control_taus.iloc[1].tz_convert(SERVER_TZ).tz_localize(None) - BAR, control_taus.iloc[1], pit.iloc[1])]
    audit = build_audit(features, cal, decision_utc, sched, control_rows)
    print("\nPOINT-IN-TIME AUDIT")
    print("\n".join(audit_lines(audit)))

    hashes_after, test_stat_after = snapshot_files(skip)
    changed = sorted(str(p) for p in set(hashes_before) | set(hashes_after) if hashes_before.get(p) != hashes_after.get(p))
    if changed:
        raise AssertionError(f"existing files changed: {changed}")
    assert test_stat_after == test_stat_before and GUARD["test_open_attempts"] == 0

    s = summary.set_index("config")
    cand = [n for n in list(CONFIGS)[1:]]
    best = max(cand, key=lambda n: s.loc[n, "wf_mean_balanced_accuracy"])
    consistent = [n for n in cand if s.loc[n, "verdict"] == "CONSISTENT IMPROVEMENT"]
    partial = [n for n in cand if s.loc[n, "verdict"] == "PARTIAL IMPROVEMENT"]
    ci_support = [n for n in cand if s.loc[n, "wf_ci_all_above_zero"]]
    verdict_lines = [
        f"Highest walk-forward mean among event configurations: {best} ({s.loc[best, 'wf_mean_balanced_accuracy']:.4f}, "
        f"{s.loc[best, 'delta_wf_mean']:+.4f} vs baseline).",
        "Answer: " + (f"yes - {', '.join(consistent)} improved consistently." if consistent else
                      f"partially - {', '.join(partial)}." if partial else
                      "no; scheduled CPI/NFP/FOMC timing did not improve walk-forward balanced accuracy consistently."),
    ]
    coverage = "; ".join(
        f"{e}: {int((research[f'{e.lower()}_release_day'] == 1).sum())} rows on release days, "
        f"{int(research[[c for c in FAMILIES[e] if '_win_' in c]].sum(axis=1).gt(0).sum())} rows in a +/-60 min window"
        for e in EVENTS)
    reads = ", ".join(sorted({p.name for p in GUARD["csv_reads"]}))
    checks = {
        "research_rows": len(research), "near_duplicates": dupes, "coverage": coverage, "utc": utc_lines,
        "first_research_row": f"{full_labeled['time'].iloc[0]}", "verdict_lines": verdict_lines,
        "captures": ("CPI schedule 50 captures 2025-06..2026-10; Employment Situation schedule 31 captures (29 with the "
                     "table) 2025-06..2026-10; FOMC calendar monthly captures 2024-01..2026-09; Board monthly calendars "
                     "2025-12-31 (January), 2026-01-23 (March, June, July, September, October)."),
        "lines": [
            f"[PASS] 1. No future XAUUSD data: calendar features depend only on each row's own timestamp; recomputed from "
            f"only the rows <= tau at {len(check_taus)} check points, all {compared:,} values matched; baseline features "
            "are the existing CSV columns (unchanged).",
            "[PASS] 2. No actual economic values: the schedule holds only event name, reference period, scheduled times, "
            "archive capture times and source URLs (column whitelist asserted); no feature or column name refers to an "
            "actual/forecast/previous/surprise/decision value.",
            f"[PASS] 3. No future event timestamps: all {n_entries:,} schedule entries used by research rows were archived "
            "before the decision time and not yet superseded; recomputing with only entries known at tau gave identical "
            "values; control (decision times before the first research row): on 2026-02-05 the features used the "
            "pre-revision NFP 02-06 / CPI 02-11 dates and differed from the final schedule, on 2026-02-10 (after the "
            "revision was archived) they matched it.",
            f"[PASS] 4. No test-period XAUUSD access: CSVs read only up to {GUARD['cutoff']}; CSVs read: {reads}; audit "
            "hook recorded 0 attempts to open the test CSV (any attempt raises immediately).",
            f"[PASS] 5. Correct UTC conversion: 5 ET->UTC anchors across EST/EDT matched; server->UTC anchors matched; "
            f"{utc_lines[0]}.",
            "[PASS] 6. No duplicate event timestamps within any event family (all vintages and active schedule).",
            "[PASS] 7. No duplicate XAUUSD timestamps (server and UTC, raw and features; strictly increasing).",
            "[PASS] 8. Deterministic: recomputing the calendar features in reversed row order reproduced every value.",
            "[PASS] 9. No information after prediction time: every 'since' event is strictly before tau, every 'until' "
            "event is at/after tau and was scheduled publicly before tau; tau = bar close, when the bar's features exist.",
            f"[PASS] 10. Same rows and labels across configurations: {len(research)} rows; validation labels identical for "
            "all configurations in main and WF1-WF3.",
            "[PASS] 11. Existing RF baseline reproduces exactly: labels, train/validation rows and the retrained RF match "
            "the existing CSVs and saved model; BASELINE main-split predictions are identical to that model's.",
            f"[PASS] 12. Existing files unchanged: SHA-256 of {len(hashes_before)} files in src/, src/data/, src/models/ "
            "identical before and after (test CSV checked by size/modification time only, never opened).",
        ],
    }

    lines = build_report(ev, summary, backtest, sched, audit, wf_windows, boundary, checks, confusions)
    feat_out = pd.DataFrame({"time": times.dt.strftime("%Y-%m-%d %H:%M:%S"),
                             "time_utc": times_utc.dt.strftime("%Y-%m-%d %H:%M:%S"),
                             "decision_utc": decision_utc.dt.strftime("%Y-%m-%d %H:%M:%S")})
    feat_out = pd.concat([feat_out, cal[cal_cols]], axis=1)
    sched_out = sched.assign(section="schedule", config=sched["event"],
                             scheduled_utc=sched["scheduled_utc"].astype(str),
                             known_from_utc=sched["known_from_utc"].astype(str),
                             superseded_utc=sched["superseded_utc"].astype(str))
    audit_out = audit.assign(section="audit", config=audit["case"])
    feat_out.to_csv(FEATURES_OUT, index=False)
    pd.concat([summary, ev, backtest, sched_out, audit_out], ignore_index=True).to_csv(RESULTS_PATH, index=False)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert snapshot_files(skip)[0] == hashes_before, "existing files changed while writing outputs"
    print()
    print("\n".join(lines))

    wf = ["WF1", "WF2", "WF3"]
    fmt = lambda n: " / ".join(f"{s.loc[n, f'{w}_val_balanced_accuracy']:.4f}" for w in wf) + \
        f" / mean {s.loc[n, 'wf_mean_balanced_accuracy']:.4f}"
    print("\nFINAL SUMMARY")
    print(f" 1. Baseline WF1/WF2/WF3/mean: {fmt('BASELINE')}")
    print(f" 2. CPI config:  {fmt('A_CPI')}")
    print(f" 3. NFP config:  {fmt('B_NFP')}")
    print(f" 4. FOMC config: {fmt('C_FOMC')}")
    print(f" 5. ALL config:  {fmt('D_ALL')}")
    print(f" 6. Best configuration (highest WF mean): {best}")
    print(f" 7. Mean improvement versus baseline: {s.loc[best, 'delta_wf_mean']:+.4f} (" +
          ", ".join(f"{n} {s.loc[n, 'delta_wf_mean']:+.4f}" for n in cand) + ")")
    print(f" 8. Consistent improvement: {', '.join(consistent) if consistent else 'none'} "
          f"({'; '.join(f'{n}: {s.loc[n, 'verdict']}' for n in cand)})")
    print(f" 9. Bootstrap CI above zero in all three windows: {', '.join(ci_support) if ci_support else 'none'}")
    print(" 10. Calendar source: BLS CPI and Employment Situation release schedules; Federal Reserve FOMC calendar and "
          "monthly calendars; point-in-time versions from Internet Archive captures")
    print(" 11. Leakage checks: all 12 passed")
    print(" 12. Test-data safety: test CSV never opened (0 attempts; guarded reads end at "
          f"{GUARD['cutoff']})")
    print(f" 13. Existing-file integrity: {len(hashes_before)} files unchanged")
    print(" 14. Final verdict: " + verdict_lines[1].replace("Answer: ", ""))
    print(f"\nSaved: {FEATURES_OUT}\n       {RESULTS_PATH}\n       {REPORT_PATH}")


if __name__ == "__main__":
    main()
