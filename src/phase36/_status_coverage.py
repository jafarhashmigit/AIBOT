from pathlib import Path

raw = Path("src/data/phase36/raw")
for d in sorted(raw.iterdir() if raw.exists() else []):
    miss = []
    for h in range(24):
        bi5 = d / f"{h:02d}h_ticks.bi5"
        empty = d / f"{h:02d}h_ticks.empty"
        if not bi5.is_file() and not empty.is_file():
            miss.append(h)
    bi5_n = len(list(d.glob("*.bi5")))
    empty_n = len(list(d.glob("*.empty")))
    print(f"{d.name}: bi5={bi5_n} empty={empty_n} have={24-len(miss)} missing={miss}")

for src in ["src/data/phase34/raw", "src/data/phase25/raw", "src/data/phase33/raw"]:
    p = Path(src)
    print(src, "exists", p.exists(), "ndays", len(list(p.iterdir())) if p.exists() else 0)
    if p.exists():
        overlap = []
        sel = [
            "2026-02-16",
            "2026-02-27",
            "2026-03-13",
            "2026-03-25",
            "2026-04-07",
            "2026-04-17",
            "2026-04-29",
            "2026-05-11",
            "2026-05-22",
            "2026-06-03",
            "2026-06-16",
            "2026-06-26",
            "2026-07-09",
            "2026-07-21",
            "2026-07-31",
            "2026-08-12",
            "2026-08-25",
            "2026-09-04",
            "2026-09-17",
            "2026-09-29",
        ]
        for day in sel:
            if (p / day).is_dir():
                overlap.append(day)
        print("  overlap_selected", overlap)
