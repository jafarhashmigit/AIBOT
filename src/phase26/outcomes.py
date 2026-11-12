"""Richer research labels: MFE/MAE/forward metrics after next-bar entry."""

from __future__ import annotations

import numpy as np

from phase26.constants import ADV_ATR, FAV_ATR, HORIZONS


def _window_valid(gap_flags: np.ndarray, minutes: np.ndarray, entry_i: int, end_i: int) -> bool:
    """Reject if any bar in (entry_i, end_i] is after a gap / long pause."""
    if end_i >= len(gap_flags):
        return False
    for j in range(entry_i + 1, end_i + 1):
        if gap_flags[j] >= 1.0:
            return False
        if minutes[j] > 10.0:  # M5 expected ~5; >10 implies missing/closure
            return False
    return True


def build_rich_outcomes(feats: dict[str, np.ndarray], n: int) -> dict[str, dict[int, np.ndarray]]:
    """
    Decision index i uses closed bar i.
    Entry at open of i+1.
    Path uses bars i+1 .. i+H inclusive for horizon H.
    MFE/MAE are price excursions from entry open, in ATR units of bar i (not net R).
    """
    o = feats["_open"]
    h = feats["_high"]
    l = feats["_low"]
    c = feats["_close"]
    atr = feats["_atr"]
    gap = feats["_gap"]
    minutes = feats["_minutes_gap"]

    out: dict[str, dict[int, np.ndarray]] = {
        "mfe_buy_atr": {},
        "mae_buy_atr": {},
        "mfe_sell_atr": {},
        "mae_sell_atr": {},
        "fwd_ret_buy": {},
        "fwd_ret_sell": {},
        "fwd_vol": {},
        "t_fav_buy": {},
        "t_adv_buy": {},
        "fav_before_adv_buy": {},
        "neither_buy": {},
        "eligible": {},
    }

    for H in HORIZONS:
        mfe_b = np.full(n, np.nan)
        mae_b = np.full(n, np.nan)
        mfe_s = np.full(n, np.nan)
        mae_s = np.full(n, np.nan)
        fr_b = np.full(n, np.nan)
        fr_s = np.full(n, np.nan)
        fvol = np.full(n, np.nan)
        tf = np.full(n, np.nan)
        ta = np.full(n, np.nan)
        fba = np.full(n, np.nan)
        neither = np.full(n, np.nan)
        elig = np.zeros(n)

        for i in range(n - (H + 1)):
            entry_i = i + 1
            end_i = i + H
            if atr[i] <= 0 or not np.isfinite(atr[i]):
                continue
            if not _window_valid(gap, minutes, entry_i, end_i):
                continue
            entry = o[entry_i]
            if not np.isfinite(entry):
                continue
            # path bars from entry through horizon end
            hh = h[entry_i : end_i + 1]
            ll = l[entry_i : end_i + 1]
            cc = c[entry_i : end_i + 1]
            if len(hh) < H:
                continue

            # BUY excursions from entry open
            mfe_b[i] = (float(np.max(hh)) - entry) / atr[i]
            mae_b[i] = (entry - float(np.min(ll))) / atr[i]
            # SELL
            mfe_s[i] = (entry - float(np.min(ll))) / atr[i]
            mae_s[i] = (float(np.max(hh)) - entry) / atr[i]

            fr_b[i] = (cc[-1] - entry) / entry
            fr_s[i] = (entry - cc[-1]) / entry

            if H >= 2:
                lr = np.diff(np.log(np.maximum(cc, 1e-12)))
                fvol[i] = float(np.std(lr)) if len(lr) else np.nan
            else:
                fvol[i] = np.nan

            fav_lvl = entry + FAV_ATR * atr[i]
            adv_lvl = entry - ADV_ATR * atr[i]
            t_fav = np.nan
            t_adv = np.nan
            for k in range(len(hh)):
                if not np.isfinite(t_fav) and hh[k] >= fav_lvl:
                    t_fav = float(k + 1)
                if not np.isfinite(t_adv) and ll[k] <= adv_lvl:
                    t_adv = float(k + 1)
                if np.isfinite(t_fav) and np.isfinite(t_adv):
                    break
            tf[i] = t_fav
            ta[i] = t_adv
            if np.isfinite(t_fav) and np.isfinite(t_adv):
                fba[i] = 1.0 if t_fav < t_adv else 0.0
                neither[i] = 0.0
            elif np.isfinite(t_fav) and not np.isfinite(t_adv):
                fba[i] = 1.0
                neither[i] = 0.0
            elif np.isfinite(t_adv) and not np.isfinite(t_fav):
                fba[i] = 0.0
                neither[i] = 0.0
            else:
                fba[i] = np.nan
                neither[i] = 1.0
            elig[i] = 1.0

        out["mfe_buy_atr"][H] = mfe_b
        out["mae_buy_atr"][H] = mae_b
        out["mfe_sell_atr"][H] = mfe_s
        out["mae_sell_atr"][H] = mae_s
        out["fwd_ret_buy"][H] = fr_b
        out["fwd_ret_sell"][H] = fr_s
        out["fwd_vol"][H] = fvol
        out["t_fav_buy"][H] = tf
        out["t_adv_buy"][H] = ta
        out["fav_before_adv_buy"][H] = fba
        out["neither_buy"][H] = neither
        out["eligible"][H] = elig

    return out


def target_vector(outcomes: dict, target_id: str, n: int) -> np.ndarray:
    if target_id == "fwd_vol_12":
        return outcomes["fwd_vol"][12]
    if target_id == "mfe_buy_12_atr":
        return outcomes["mfe_buy_atr"][12]
    if target_id == "mae_buy_12_atr":
        return outcomes["mae_buy_atr"][12]
    if target_id == "fwd_ret_buy_6":
        return outcomes["fwd_ret_buy"][6]
    if target_id == "fav_before_adv_buy_12":
        return outcomes["fav_before_adv_buy"][12]
    raise KeyError(target_id)
