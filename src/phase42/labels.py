"""Forward labels — causal, no fabricated fills. Missing horizon → None."""

from __future__ import annotations

from typing import Any

from phase42.constants import HORIZONS


def attach_forward_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach forward mid returns, realized vol, MFE/MAE from subsequent OHLC (not ticks)."""
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
                row[f"realized_vol_h{h}"] = None
                row[f"mfe_atr_h{h}"] = None
                row[f"mae_atr_h{h}"] = None
                row[f"fav_before_adv_h{h}"] = None
                continue
            cj = float(rows[j]["close"])
            ret = cj - c0
            row[f"ret_h{h}"] = ret
            row[f"ret_atr_h{h}"] = (ret / a0) if a0 else None
            row[f"abs_ret_atr_h{h}"] = (abs(ret) / a0) if a0 else None
            # path vol
            rets = []
            mfe = mae = 0.0
            for k in range(i + 1, j + 1):
                rets.append(float(rows[k]["close"]) - float(rows[k - 1]["close"]))
                dd = float(rows[k]["close"]) - c0
                mfe = max(mfe, dd)
                mae = min(mae, dd)
            if len(rets) >= 2:
                mu = sum(rets) / len(rets)
                row[f"realized_vol_h{h}"] = (sum((x - mu) ** 2 for x in rets) / len(rets)) ** 0.5
            else:
                row[f"realized_vol_h{h}"] = abs(rets[0]) if rets else None
            row[f"mfe_atr_h{h}"] = (mfe / a0) if a0 else None
            row[f"mae_atr_h{h}"] = (mae / a0) if a0 else None
            # favorable-before-adverse: did MFE reach +0.5ATR before MAE -0.5ATR along path?
            fav = None
            if a0:
                hit_fav = hit_adv = False
                for k in range(i + 1, j + 1):
                    dd = (float(rows[k]["close"]) - c0) / a0
                    if dd >= 0.5:
                        hit_fav = True
                        break
                    if dd <= -0.5:
                        hit_adv = True
                        break
                if hit_fav:
                    fav = True
                elif hit_adv:
                    fav = False
                else:
                    fav = None
            row[f"fav_before_adv_h{h}"] = fav
        out.append(row)
    return out
