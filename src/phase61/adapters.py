"""Read-only adapters — no Phase 0–60 mutation; no live MT5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phase54.decision import NullPolicy
from phase60.constants import PHASE58_SPLITS as P60_SPLITS
from phase61.constants import EXPECTED_NULL_POLICY, PHASE58_SPLITS, PHASE60_REPORTS, PROJECT_ROOT


def null_policy_ok() -> bool:
    return NullPolicy().version == EXPECTED_NULL_POLICY


def phase58_holdout() -> list[str]:
    path = PHASE58_SPLITS if PHASE58_SPLITS.is_file() else P60_SPLITS
    if not path.is_file():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    return list(obj.get("holdout_sealed") or [])


def load_phase60_validation() -> dict[str, Any]:
    p = PHASE60_REPORTS / "validation_results.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def scan_repo_broker_hints() -> dict[str, Any]:
    """Non-secret configuration scan for Exness/account clues."""
    hints: dict[str, Any] = {
        "env_keys_present": [],
        "exness_string_hits": [],
        "source_server_labels": [],
        "terminal_path_hints": [],
        "credentials_scanned": False,
        "credentials_stored": False,
    }
    env = PROJECT_ROOT / ".env"
    env_ex = PROJECT_ROOT / ".env.example"
    for p in (env, env_ex):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=", 1)[0].strip()
                if key:
                    hints["env_keys_present"].append(key)
    # Source labels from known constants modules (import-safe strings)
    for rel in (
        "src/phase53/constants.py",
        "src/phase49/constants.py",
        "src/phase46/constants.py",
        "src/phase38/constants.py",
    ):
        p = PROJECT_ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if "SOURCE_SERVER_LABEL" in text and "MetaQuotes-Demo" in text:
            hints["source_server_labels"].append({"file": rel, "label": "MetaQuotes-Demo"})
        if "TERMINAL_PATH" in text:
            for line in text.splitlines():
                if line.strip().startswith("TERMINAL_PATH"):
                    hints["terminal_path_hints"].append({"file": rel, "line": line.strip()[:120]})
    # Search docs for Exness mentions (no secrets)
    docs = PROJECT_ROOT / "docs"
    if docs.is_dir():
        for p in docs.rglob("*.md"):
            try:
                t = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "exness" in t.lower():
                hints["exness_string_hits"].append(str(p.relative_to(PROJECT_ROOT)))
    hints["env_keys_present"] = sorted(set(hints["env_keys_present"]))
    return hints
