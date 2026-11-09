"""Phase 25 approved-data loader. Extends feature keep without editing Phase 14."""

from __future__ import annotations

from phase3.nplib import read_csv_dicts
from phase14.data import fold_of, load_bundle as load_phase14_bundle
from phase25.constants import (
    FEATURE_KEEP,
    FEATURES_PATH,
    HOLDOUT_NAME,
    MAX_DECISION_TIME_UTC,
    RESEARCH_CUTOFF_UTC,
)


def enrich_bundle_features(bundle: dict) -> dict:
    features: dict[str, dict] = {}
    feature_times: list[str] = []
    for row in read_csv_dicts(FEATURES_PATH):
        t = row["time"]
        if t > RESEARCH_CUTOFF_UTC:
            continue
        feat = {k: row[k] for k in FEATURE_KEEP if k in row}
        features[t] = feat
        feature_times.append(t)
    feature_times.sort()
    bundle = dict(bundle)
    bundle["features"] = features
    bundle["feature_times"] = feature_times
    bundle["feature_index"] = {t: i for i, t in enumerate(feature_times)}
    return bundle


def load_research_bundle() -> dict:
    assert HOLDOUT_NAME not in str(FEATURES_PATH)
    base = load_phase14_bundle()
    bundle = enrich_bundle_features(base)
    bundle["timestamps"] = [t for t in bundle["timestamps"] if t <= MAX_DECISION_TIME_UTC]
    bundle["bounds"] = dict(bundle.get("bounds") or {})
    bundle["bounds"]["research_cutoff"] = RESEARCH_CUTOFF_UTC
    bundle["bounds"]["max_decision_time"] = MAX_DECISION_TIME_UTC
    bundle["bounds"]["holdout_opened"] = False
    return bundle


def fold_counts(timestamps: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in timestamps:
        fid = fold_of(t)
        if fid is None:
            continue
        out[fid] = out.get(fid, 0) + 1
    return out
