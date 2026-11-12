"""Forward labels — causal; missing horizon stays None."""

from __future__ import annotations

from typing import Any

from phase44.constants import HORIZONS


def attach_forward_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    n = len(rows)
    out = []
    for i, r in enumerate(rows):
        row = dict(r)
        c0 = float(r["close"])
        a0 = r.get("atr_14")
        for h in HORIZONS:
            j = i + h
            if j >= n or rows[j]["day"] != r["day"]:
                row[f"ret_h{h}"] = None
                row[f"ret_atr_h{h}"] = None
                row[f"abs_ret_atr_h{h}"] = None
                row[f"mfe_atr_h{h}"] = None
                row[f"mae_atr_h{h}"] = None
                continue
            cj = float(rows[j]["close"])
            ret = cj - c0
            row[f"ret_h{h}"] = ret
            row[f"ret_atr_h{h}"] = (ret / a0) if a0 else None
            row[f"abs_ret_atr_h{h}"] = (abs(ret) / a0) if a0 else None
            mfe = mae = 0.0
            for k in range(i + 1, j + 1):
                dd = float(rows[k]["close"]) - c0
                mfe = max(mfe, dd)
                mae = min(mae, dd)
            row[f"mfe_atr_h{h}"] = (mfe / a0) if a0 else None
            row[f"mae_atr_h{h}"] = (mae / a0) if a0 else None
        out.append(row)
    return out
