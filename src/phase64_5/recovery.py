"""Recovery & crash tests for evidence journal."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from phase64_5.constants import PARSER_VERSION, SIMULATED_LABEL, canonical_json_sha256
from phase64_5.import_pipeline import import_csv_file, write_simulated_fixtures
from phase64_5.journal import BrokerEvidenceJournal
from phase64_5.normalize import normalize_deal_row
from phase64_5.reconciliation import reconcile_twice


def run_recovery_suite() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixtures = write_simulated_fixtures(root / "fx")

        # Same file twice
        j = BrokerEvidenceJournal(root / "j1", allow_synthetic=True, store_label=SIMULATED_LABEL)
        r1 = import_csv_file(j, Path(fixtures["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
        r2 = import_csv_file(j, Path(fixtures["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
        cases.append(
            {
                "name": "same_file_imported_twice",
                "pass": r1["stats"]["ingested"] > 0 and r2["stats"]["duplicates"] >= r2["stats"].get("deals", 0),
                "evidence": SIMULATED_LABEL,
            }
        )

        # Restart: new journal instance same root
        j1b = BrokerEvidenceJournal(root / "j1", allow_synthetic=True, store_label=SIMULATED_LABEL)
        n_before = len(j1b.all_events())
        r3 = import_csv_file(j1b, Path(fixtures["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
        cases.append(
            {
                "name": "same_file_after_restart",
                "pass": r3["stats"]["duplicates"] > 0 and len(j1b.all_events()) == n_before,
                "evidence": SIMULATED_LABEL,
            }
        )

        # Different file with already-seen deal ids
        j2 = BrokerEvidenceJournal(root / "j2", allow_synthetic=True, store_label=SIMULATED_LABEL)
        import_csv_file(j2, Path(fixtures["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
        dup_file = root / "fx" / "dup_deals.csv"
        dup_file.write_text(Path(fixtures["deals"]).read_text(encoding="utf-8"), encoding="utf-8")
        r4 = import_csv_file(j2, dup_file, synthetic=True, evidence_label=SIMULATED_LABEL)
        cases.append(
            {
                "name": "different_file_already_seen_records",
                "pass": r4["stats"]["duplicates"] > 0,
                "evidence": SIMULATED_LABEL,
            }
        )

        # Duplicate deal identical vs conflicting
        j3 = BrokerEvidenceJournal(root / "j3", allow_synthetic=True, store_label=SIMULATED_LABEL)
        batch = j3.begin_batch(source_file="manual", source_sha256="x", parser_version=PARSER_VERSION)
        mapped = {
            "broker_deal_id": "DCONF1",
            "broker_order_id": "O1",
            "symbol": "XAUUSDm",
            "direction": "buy",
            "volume": "0.01",
            "price": "2650.0",
            "timestamp_raw": "2026-01-05 10:00:00",
            "commission": None,
        }
        prov = {"synthetic": True, "evidence_label": SIMULATED_LABEL, "source_file_sha256": "x"}
        rec, _ = normalize_deal_row(mapped, provenance=prov)
        assert rec
        a = j3.append_event(rec, import_batch_id=batch)
        b = j3.append_event(rec, import_batch_id=batch)
        mapped2 = dict(mapped)
        mapped2["price"] = "2651.0"
        rec2, _ = normalize_deal_row(mapped2, provenance=prov)
        assert rec2
        c = j3.append_event(rec2, import_batch_id=batch)
        cases.append(
            {
                "name": "duplicate_deal_identical",
                "pass": a["status"] == "INGESTED" and b["status"] == "DUPLICATE_SUPPRESSED",
                "evidence": SIMULATED_LABEL,
            }
        )
        cases.append(
            {
                "name": "duplicate_deal_conflicting",
                "pass": c["status"] == "QUARANTINED" and len(j3.incidents()) >= 1,
                "evidence": SIMULATED_LABEL,
            }
        )

        # Interrupted journal append (WAL crash)
        j4 = BrokerEvidenceJournal(root / "j4", allow_synthetic=True, store_label=SIMULATED_LABEL)
        batch4 = j4.begin_batch(source_file="wal", source_sha256="y", parser_version=PARSER_VERSION)
        mapped3 = dict(mapped)
        mapped3["broker_deal_id"] = "DWAL1"
        rec3, _ = normalize_deal_row(mapped3, provenance=prov)
        assert rec3
        crashed = False
        try:
            j4.append_event(rec3, import_batch_id=batch4, crash_after_wal=True)
        except RuntimeError as exc:
            crashed = "CrashInjected" in str(exc)
        # recover via new instance
        j4b = BrokerEvidenceJournal(root / "j4", allow_synthetic=True, store_label=SIMULATED_LABEL)
        cases.append(
            {
                "name": "interrupted_journal_append_wal_recovery",
                "pass": crashed and any(e.get("broker_deal_id") == "DWAL1" for e in j4b.all_events()),
                "evidence": SIMULATED_LABEL,
            }
        )

        # Interrupted index rebuild
        j5 = BrokerEvidenceJournal(root / "j5", allow_synthetic=True, store_label=SIMULATED_LABEL)
        import_csv_file(j5, Path(fixtures["deals"]), synthetic=True, evidence_label=SIMULATED_LABEL)
        j5.index_path.write_text("{}", encoding="utf-8")
        rebuilt = j5.reconstruct_index()
        cases.append(
            {
                "name": "interrupted_index_rebuild",
                "pass": rebuilt.get("n", 0) == len(j5.all_events()),
                "evidence": SIMULATED_LABEL,
            }
        )

        # Repeated reconciliation
        rt = reconcile_twice(j5.all_events(), aibot_intents=[{"intent_id": "INTENT_SIM_1", "decision_id": "DEC1"}])
        cases.append({"name": "repeated_reconciliation", "pass": rt["pass"], "evidence": SIMULATED_LABEL})

        # Subprocess crash during import
        sub = _subprocess_crash_import(root / "sub", Path(fixtures["deals"]))
        cases.append(sub)

    out = {
        "cases": cases,
        "n_cases": len(cases),
        "n_pass": sum(1 for c in cases if c.get("pass")),
        "suite_pass": all(c.get("pass") for c in cases),
        "evidence_label": SIMULATED_LABEL,
    }
    out["sha256"] = canonical_json_sha256({k: v for k, v in out.items() if k != "sha256"})
    return out


def _subprocess_crash_import(work: Path, csv_path: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=True)
    src_dir = Path(__file__).resolve().parents[1]
    script = work / "child.py"
    journal_root = work / "journal"
    script.write_text(
        "\n".join(
            [
                "import os, sys",
                "from pathlib import Path",
                f"sys.path.insert(0, r'{src_dir}')",
                "from phase64_5.journal import BrokerEvidenceJournal",
                "from phase64_5.normalize import normalize_deal_row",
                f"j = BrokerEvidenceJournal(Path(r'{journal_root}'), allow_synthetic=True, store_label='SIMULATED_FIXTURE')",
                "batch = j.begin_batch(source_file='child', source_sha256='z', parser_version='phase64_5_parser_v1')",
                "mapped = {'broker_deal_id':'DSUB1','broker_order_id':'O','symbol':'XAUUSDm','direction':'buy',"
                "'volume':'0.01','price':'1.0','timestamp_raw':'2026-01-05 10:00:00'}",
                "prov={'synthetic':True,'evidence_label':'SIMULATED_FIXTURE','source_file_sha256':'z'}",
                "rec,_=normalize_deal_row(mapped, provenance=prov)",
                "try:",
                "    j.append_event(rec, import_batch_id=batch, crash_after_wal=True)",
                "except Exception as e:",
                f"    Path(r'{work / 'marker.txt'}').write_text(str(e), encoding='utf-8')",
                "    os._exit(99)",
                "os._exit(0)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_dir)
    proc = subprocess.run([sys.executable, str(script)], cwd=str(work), env=env, capture_output=True, text=True, timeout=60)
    marker = work / "marker.txt"
    j = BrokerEvidenceJournal(journal_root, allow_synthetic=True, store_label=SIMULATED_LABEL)
    recovered = any(e.get("broker_deal_id") == "DSUB1" for e in j.all_events())
    return {
        "name": "subprocess_crash_wal_recovery",
        "pass": marker.is_file() and proc.returncode == 99 and recovered,
        "evidence": SIMULATED_LABEL,
        "child_exitcode": proc.returncode,
    }
