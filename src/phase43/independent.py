"""Independent reload + SHA-256 verification of Phase43 manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase43.constants import MANIFESTS, file_sha256
from phase43.storage import load_jsonl


def verify_manifests() -> dict[str, Any]:
    results = []
    ok = True
    if not MANIFESTS.exists():
        return {"ok": False, "reason": "no_manifests", "n_manifests": 0, "n_fail": 0, "results": []}
    for man in sorted(MANIFESTS.glob("*.manifest.json")):
        meta = json.loads(man.read_text(encoding="utf-8"))
        path = Path(meta["file_path"])
        row: dict[str, Any] = {"manifest": man.name}
        if not path.is_file():
            row["ok"] = False
            row["error"] = "missing_file"
            ok = False
        else:
            dig = file_sha256(path)
            rows = load_jsonl(path)
            rc = meta.get("record_count")
            row["sha256_ok"] = dig == meta.get("sha256")
            row["count_ok"] = rc is not None and len(rows) == int(rc)
            row["reload_n"] = len(rows)
            row["ok"] = row["sha256_ok"] and row["count_ok"]
            if not row["ok"]:
                ok = False
        results.append(row)
    fails = [r for r in results if not r.get("ok")]
    return {
        "ok": ok,
        "n_manifests": len(results),
        "n_fail": len(fails),
        "fail_sample": fails[:20],
        "results": results,
    }
