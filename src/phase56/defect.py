"""Reproduce Phase55-identified LifecycleEngine SL/TP wiring defect (read-only)."""

from __future__ import annotations

import inspect
from typing import Any

from phase54.lifecycle import LifecycleEngine
from phase54.paper_exec import force_horizon_exit_from_bars, monitor_and_maybe_exit
from phase56.constants import REPORTS_DIR
from phase56.progress import write_json


def reproduce_sl_tp_defect() -> dict[str, Any]:
    src = inspect.getsource(LifecycleEngine.process_bar)
    report = {
        "defect_id": "P55_LIFECYCLE_HORIZON_ONLY",
        "description": (
            "LifecycleEngine.process_bar calls force_horizon_exit_from_bars only; "
            "monitor_and_maybe_exit (SL/TP) is never invoked."
        ),
        "process_bar_calls_force_horizon": "force_horizon_exit_from_bars(" in src,
        "process_bar_calls_monitor": "monitor_and_maybe_exit(" in src,
        "monitor_exists": callable(monitor_and_maybe_exit),
        "force_horizon_exists": callable(force_horizon_exit_from_bars),
        "defect_confirmed": ("force_horizon_exit_from_bars(" in src) and ("monitor_and_maybe_exit(" not in src),
        "remediation": (
            "phase56.lifecycle.IntegratedLifecycleEngine subclasses LifecycleEngine and "
            "overrides process_bar to monitor SL/TP before horizon; also monitors open "
            "positions on every new observation. Phase54 source left unmodified."
        ),
    }
    write_json(REPORTS_DIR / "defect_reproduction.json", report)
    return report
