"""Read-only OOXML (.xlsx) sheet reader — stdlib only (no openpyxl dependency)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx_rows(path: Path, *, max_rows: int | None = None) -> dict[str, Any]:
    """Return sheet rows as lists of cell values (shared-string resolved)."""
    data = path.read_bytes()
    with zipfile.ZipFile(path) as z:
        strings: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss.findall("m:si", NS):
                texts = [
                    (t.text or "")
                    for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                ]
                strings.append("".join(texts))
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in z.namelist():
            sheets = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            if not sheets:
                return {"ok": False, "error": "no_worksheet", "rows": [], "n_shared_strings": len(strings)}
            sheet_name = sorted(sheets)[0]
        sheet = ET.fromstring(z.read(sheet_name))
        rows: list[list[Any]] = []
        for row in sheet.findall("m:sheetData/m:row", NS):
            vals: list[Any] = []
            for c in row.findall("m:c", NS):
                t = c.get("t")
                v = c.find("m:v", NS)
                if v is None or v.text is None:
                    vals.append(None)
                    continue
                if t == "s":
                    idx = int(v.text)
                    vals.append(strings[idx] if 0 <= idx < len(strings) else None)
                else:
                    vals.append(v.text)
            rows.append(vals)
            if max_rows is not None and len(rows) >= max_rows:
                break
    return {
        "ok": True,
        "rows": rows,
        "n_rows": len(rows),
        "n_shared_strings": len(strings),
        "bytes_len": len(data),
    }
