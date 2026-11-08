"""Machine-readable evaluation reports.

Every report records seed, configuration, finding class (reproduction /
exploratory / confirmatory) and holdout-guard status.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.integrity import holdout_status, write_json


def jsonable(obj):
    """Convert numpy/pandas scalars so reports can be written as JSON."""
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
    if isinstance(obj, (pd.Timestamp, datetime)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if isinstance(obj, pd.Series):
        return jsonable(obj.to_dict())
    return str(obj)


def wrap(name: str, finding_class: str, configuration: dict, result: dict,
         seed: int, extras: dict | None = None) -> dict:
    payload = {
        "report": name,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finding_class": finding_class,
        "seed": seed,
        "configuration": configuration,
        "holdout": holdout_status(),
        "result": result,
    }
    if extras:
        payload.update(extras)
    return jsonable(payload)


def save(path: Path, payload: dict) -> Path:
    write_json(path, jsonable(payload))
    return path
