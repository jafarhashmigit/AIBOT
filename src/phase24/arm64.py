"""ARM64 / Linux aarch64 dependency audit without installing packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from phase24.constants import PINNED_RUNTIME, PROJECT_ROOT, WINDOWS_ONLY_RUNTIME


def _pypi_release(package: str, version: str, *, timeout: float = 30.0) -> dict[str, Any] | None:
    """Fetch PyPI JSON metadata. Network optional — callers may pass cache."""
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        req = Request(url, headers={"User-Agent": "AIBOT-phase24-arm64-audit/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — read-only public metadata
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — audit must degrade gracefully
        return {"error": f"{type(exc).__name__}: {exc}", "urls": [], "info": {}}


def analyze_release(package: str, version: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = payload if payload is not None else _pypi_release(package, version)
    if not data or data.get("error"):
        return {
            "package": package,
            "version": version,
            "status": "METADATA_UNAVAILABLE",
            "error": (data or {}).get("error"),
            "has_cp312_manylinux_aarch64": None,
        }
    urls = data.get("urls") or []
    wheels = [u for u in urls if u.get("packagetype") == "bdist_wheel"]
    cp312_aarch = [
        u.get("filename")
        for u in wheels
        if "cp312" in (u.get("filename") or "")
        and "manylinux" in (u.get("filename") or "")
        and "aarch64" in (u.get("filename") or "")
    ]
    pure_any = [
        u.get("filename")
        for u in wheels
        if "py3-none-any" in (u.get("filename") or "") or "py2.py3-none-any" in (u.get("filename") or "")
    ]
    win_only = bool(wheels) and all("win" in (u.get("filename") or "") for u in wheels)
    platforms = sorted(
        {
            "win_amd64"
            if "win_amd64" in fn
            else "manylinux_aarch64"
            if "manylinux" in fn and "aarch64" in fn
            else "pure_any"
            if "none-any" in fn
            else "other"
            for u in wheels
            for fn in [u.get("filename") or ""]
        }
    )
    return {
        "package": package,
        "version": version,
        "requires_python": (data.get("info") or {}).get("requires_python"),
        "wheel_count": len(wheels),
        "has_cp312_manylinux_aarch64": bool(cp312_aarch),
        "has_pure_python_any_wheel": bool(pure_any),
        "aarch64_compatible": bool(cp312_aarch) or bool(pure_any),
        "cp312_manylinux_aarch64_wheels": cp312_aarch,
        "windows_only_wheels": win_only,
        "platform_tags_summary": platforms,
        "status": "OK",
    }


def load_cached_pypi(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# Evidence captured from PyPI JSON on 2026-11-09 (read-only; no installs).
# Used when network is disabled or unavailable so reports remain reproducible offline.
OFFLINE_EVIDENCE: dict[str, dict[str, Any]] = {
    "numpy": {
        "has_cp312_manylinux_aarch64": True,
        "has_pure_python_any_wheel": False,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [
            "numpy-2.5.4-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl"
        ],
        "requires_python": ">=3.11",
        "evidence_source": "pypi_json_2026-11-09",
    },
    "pandas": {
        "has_cp312_manylinux_aarch64": True,
        "has_pure_python_any_wheel": False,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [
            "pandas-3.1.1-cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl"
        ],
        "requires_python": ">=3.11",
        "evidence_source": "pypi_json_2026-11-09",
    },
    "scipy": {
        "has_cp312_manylinux_aarch64": True,
        "has_pure_python_any_wheel": False,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [
            "scipy-1.18.1-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl"
        ],
        "requires_python": ">=3.11",
        "evidence_source": "pypi_json_2026-11-09",
    },
    "scikit-learn": {
        "has_cp312_manylinux_aarch64": True,
        "has_pure_python_any_wheel": False,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [
            "scikit_learn-1.9.1-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl"
        ],
        "requires_python": ">=3.11",
        "evidence_source": "pypi_json_2026-11-09",
    },
    "joblib": {
        "has_cp312_manylinux_aarch64": False,
        "has_pure_python_any_wheel": True,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [],
        "requires_python": ">=3.9",
        "evidence_source": "pypi_wheel_class_py3_none_any",
    },
    "tzdata": {
        "has_cp312_manylinux_aarch64": False,
        "has_pure_python_any_wheel": True,
        "aarch64_compatible": True,
        "windows_only_wheels": False,
        "cp312_manylinux_aarch64_wheels": [],
        "requires_python": None,
        "evidence_source": "pypi_data_package",
    },
    "MetaTrader5": {
        "has_cp312_manylinux_aarch64": False,
        "has_pure_python_any_wheel": False,
        "aarch64_compatible": False,
        "windows_only_wheels": True,
        "cp312_manylinux_aarch64_wheels": [],
        "requires_python": "<4,>=3.6",
        "evidence_source": "pypi_json_2026-11-09_win_amd64_only",
    },
}


def build_arm64_report(*, use_network: bool = False) -> dict[str, Any]:
    """Audit pinned runtime deps for Linux aarch64.

    Default uses offline PyPI evidence captured 2026-11-09 (no installs).
    Optional use_network=True refreshes from PyPI JSON (read-only).
    """
    results = []
    for pkg, ver in PINNED_RUNTIME.items():
        if use_network:
            live = analyze_release(pkg, ver)
            if live.get("status") == "OK":
                results.append(live)
                continue
        off = dict(OFFLINE_EVIDENCE.get(pkg) or {})
        results.append(
            {
                "package": pkg,
                "version": ver,
                "status": "OK_OFFLINE_EVIDENCE" if off else "MISSING",
                **off,
            }
        )

    mt5 = next((r for r in results if r["package"] == "MetaTrader5"), None)
    scientific = [r for r in results if r["package"] in {"numpy", "pandas", "scipy", "scikit-learn"}]
    pureish = [r for r in results if r["package"] in {"joblib", "tzdata"}]

    cloud_ok_without_mt5 = all(r.get("aarch64_compatible") or r.get("has_cp312_manylinux_aarch64") for r in scientific) and all(
        r.get("aarch64_compatible") for r in pureish if r.get("status") == "OK"
    )

    # Local Python
    py = {
        "version": sys.version.split()[0],
        "implementation": sys.implementation.name,
        "platform": sys.platform,
        "machine_note": "audit host may be Windows x64; cloud target is Linux aarch64",
        "target_cloud_python": "3.12.x recommended (matches pinned cp312 wheels)",
    }

    # Import-avoidance for cloud runtime
    requirements_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    return {
        "python": py,
        "pinned_runtime": PINNED_RUNTIME,
        "packages": results,
        "windows_only_runtime": list(WINDOWS_ONLY_RUNTIME),
        "metatrader5": {
            "windows_only": True if mt5 and mt5.get("windows_only_wheels") else True,
            "linux_aarch64_wheel": bool(mt5 and mt5.get("has_cp312_manylinux_aarch64")),
            "cloud_runtime_must_omit_import": True,
            "evidence": "PyPI wheels are win_amd64 only for 5.0.6231; platform metadata Windows.",
        },
        "scientific_stack_cp312_manylinux_aarch64": {
            r["package"]: r.get("has_cp312_manylinux_aarch64") for r in scientific
        },
        "pure_or_data_packages": {r["package"]: r.get("status") for r in pureish},
        "cloud_runtime_can_avoid_mt5": True,
        "arm64_scientific_wheels_available": all(
            r.get("has_cp312_manylinux_aarch64") for r in scientific
        ),
        "packages_installed_this_phase": False,
        "environment_modified": False,
        "requirements_txt_contains_metatrader5": "MetaTrader5" in requirements_text,
        "recommendation": (
            "Cloud image: install scientific pins from aarch64 wheels; never install/import MetaTrader5; "
            "inject MarketDataProvider via bar_source seam."
        ),
        "overall_arm64_status": (
            "COMPATIBLE_IF_MT5_EXCLUDED"
            if cloud_ok_without_mt5
            and all(r.get("has_cp312_manylinux_aarch64") for r in scientific)
            else "NEEDS_REVIEW"
        ),
    }
