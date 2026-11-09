"""Pandas-free helpers. Windows Application Control blocks pandas DLLs in this session."""

from __future__ import annotations

import builtins
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from phase3.constants import HOLDOUT_NAME, RESEARCH_CUTOFF, SEED, TIME_FORMAT

GUARD = {"test_open_attempts": 0, "cutoff": None, "csv_reads": []}
_real_open = builtins.open


def install_guards() -> None:
    def guarded(file, *args, **kwargs):
        name = Path(str(file)).name
        if name == HOLDOUT_NAME:
            GUARD["test_open_attempts"] += 1
            raise RuntimeError("TEST DATASET ACCESS DETECTED")
        handle = _real_open(file, *args, **kwargs)
        if name.endswith(".csv"):
            GUARD["csv_reads"].append(name)
        return handle

    builtins.open = guarded
    GUARD["cutoff"] = RESEARCH_CUTOFF


def holdout_status() -> dict:
    return {
        "test_open_attempts": GUARD["test_open_attempts"],
        "cutoff": GUARD["cutoff"],
        "csv_reads": sorted(set(GUARD["csv_reads"])),
        "test_path_in_reads": HOLDOUT_NAME in GUARD["csv_reads"],
    }


def assert_holdout_untouched() -> None:
    if GUARD["test_open_attempts"] != 0 or HOLDOUT_NAME in GUARD["csv_reads"]:
        raise RuntimeError("TEST DATASET ACCESS DETECTED")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with _real_open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def parse_time(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value), TIME_FORMAT)


def fmt_time(value) -> str:
    if isinstance(value, datetime):
        return value.strftime(TIME_FORMAT)
    return str(value)


def read_csv_dicts(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv_dicts(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    names = fieldnames or list(rows[0].keys())
    with _real_open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def col(rows: list[dict], name: str, dtype=float) -> np.ndarray:
    if dtype is object:
        return np.array([row[name] for row in rows], dtype=object)
    return np.array([row[name] for row in rows], dtype=dtype)


def jsonable(obj):
    if obj is None or isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else str(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return v if math.isfinite(v) else str(v)
    if isinstance(obj, datetime):
        return obj.strftime(TIME_FORMAT)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    return str(obj)


def wrap(name: str, finding_class: str, configuration: dict, result: dict, seed: int) -> dict:
    return jsonable({
        "report": name,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finding_class": finding_class,
        "seed": seed,
        "configuration": configuration,
        "holdout": holdout_status(),
        "result": result,
    })


def save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def profit_factor(net: np.ndarray) -> float:
    net = np.asarray(net, dtype=float)
    if len(net) == 0:
        return float("nan")
    gains = float(net[net > 0].sum())
    losses = float(-net[net < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return gains / losses


def max_drawdown(net: np.ndarray) -> float:
    net = np.asarray(net, dtype=float)
    if len(net) == 0:
        return 0.0
    equity = np.cumsum(net)
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def win_rate(net: np.ndarray) -> float:
    net = np.asarray(net, dtype=float)
    return float((net > 0).mean()) if len(net) else float("nan")


def day_cluster_bootstrap_mean(times: list, values: np.ndarray, n_samples: int = 2000,
                               seed: int = SEED) -> dict:
    values = np.asarray(values, dtype=float)
    groups = {}
    for t, v in zip(times, values):
        day = fmt_time(t)[:10] if not isinstance(t, str) else t[:10]
        groups.setdefault(day, []).append(v)
    keys = list(groups)
    packed = [np.asarray(groups[k], dtype=float) for k in keys]
    n_days = len(packed)
    if n_days < 2 or len(values) < 2:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_mean_le_0": float("nan"), "n_samples": n_samples, "seed": seed,
                "method": "day_cluster", "n_days": n_days}
    rng = np.random.default_rng(seed)
    means = np.empty(n_samples)
    for i in range(n_samples):
        pick = rng.integers(0, n_days, size=n_days)
        means[i] = np.concatenate([packed[j] for j in pick]).mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(values.mean()), "ci_low": float(lo), "ci_high": float(hi),
        "p_mean_le_0": float((means <= 0).mean()),
        "n_samples": n_samples, "seed": seed, "method": "day_cluster", "n_days": n_days,
    }
