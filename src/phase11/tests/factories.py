"""SYNTHETIC fixtures for isolated unit tests.

Never insert these into the real HistoricalExperienceStore / PaperExperienceStore
built from Phase 2 OOS or Phase 9 replay.
"""

from __future__ import annotations

from phase10.tests.factories import entry, hist_exp, paper_decision

SYNTHETIC = True
LABEL = "SYNTHETIC — isolated unit test; not a real experience record"

__all__ = ["SYNTHETIC", "LABEL", "hist_exp", "paper_decision", "entry"]
