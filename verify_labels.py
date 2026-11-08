"""Independent check of src/label_m5.py output using a slow bar-by-bar loop."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import pandas as pd
import label_m5 as L

raw = pd.read_csv(L.RAW_PATH, parse_dates=["time"])
feat = pd.read_csv(L.FEATURES_PATH, parse_dates=["time"])
out = pd.read_csv(L.OUTPUT_PATH, parse_dates=["time"])
pos = {t: i for i, t in enumerate(raw.time)}
lab = dict(zip(out.time, out.target))

forbidden = {"open", "high", "low", "close", "time_utc"}
print("forbidden columns in output:", sorted(forbidden & set(out.columns)))
print("output times subset of features:", set(out.time) <= set(feat.time))

def slow_label(t, atr):
    p = pos[t]
    if p + 12 > len(raw) - 1:
        return None
    for j in range(p + 1, p + 13):
        if raw.time[j] - raw.time[j - 1] != pd.Timedelta(minutes=5):
            return None
    sp = lambda i: max(raw.spread[i], 15) * 0.01
    le = raw.open[p + 1] + sp(p + 1) + 0.05
    se = raw.open[p + 1] - 0.05
    long_res = short_res = None
    for j in range(p + 1, p + 13):
        if long_res is None:
            sl_hit = raw.low[j] - 0.05 <= le - atr
            tp_hit = raw.high[j] - 0.05 >= le + 1.5 * atr
            long_res = "SL" if sl_hit else ("TP" if tp_hit else None)
        if short_res is None:
            sl_hit = raw.high[j] + sp(j) + 0.05 >= se + atr
            tp_hit = raw.low[j] + sp(j) + 0.05 <= se - 1.5 * atr
            short_res = "SL" if sl_hit else ("TP" if tp_hit else None)
    assert not (long_res == "TP" and short_res == "TP")
    return 1 if long_res == "TP" else (-1 if short_res == "TP" else 0)

random.seed(0)
sample = random.sample(range(len(feat)), 3000)
mismatch = 0
for i in sample:
    t, atr = feat.time[i], feat.atr_14[i]
    expected = slow_label(t, atr)
    got = lab.get(t)
    if expected != got:
        mismatch += 1
print("sample size 3000, mismatches:", mismatch)

boundary = out.time[30000]
train = out[out.time < boundary]
purged = L.purge_before_boundary(train, boundary)
print("purged rows at contiguous boundary:", len(train) - len(purged))
print("last kept train time + 60 min < boundary:", purged.time.iloc[-1] + pd.Timedelta(minutes=60) < boundary)
