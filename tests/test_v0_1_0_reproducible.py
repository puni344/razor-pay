"""
FAISLA — v0.1.0 Reproducibility Guard

dev-calibration-0.1.0 is the pilot's ONE unbiased held-out estimate: the rules
were frozen before the held-out split was touched. v0.2.0 is held-out-informed
and cannot substitute for it.

That makes results/adjudication_dev-calibration-0.1.0.jsonl the single most
load-bearing artefact in the repository — and for a while it was also the least
reproducible, because run_holdout.py runs whichever adjudicator is live
(now v0.2.0). Deleting the file lost the headline number permanently.

These tests pin the recovery path: the archived v0.1.0 source must stay
byte-preserved, and re-running it must reproduce the committed artefact
exactly. A failure here means the headline 8/18 can no longer be verified by
anyone, which is worse than the number being wrong.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.adjudication import frozen_v0_1_0
from faisla.adjudication import deterministic

RESULTS = _PROJECT_ROOT / "results" / "adjudication_dev-calibration-0.1.0.jsonl"


class TestArchivedSourceIntegrity:
    """The archive must stay what it claims to be."""

    def test_archived_version_string_is_pinned(self):
        assert frozen_v0_1_0.RULE_VERSION == "dev-calibration-0.1.0"

    def test_archive_is_not_the_live_adjudicator(self):
        """If these ever converge, the archive has stopped being an archive."""
        assert frozen_v0_1_0.RULE_VERSION != deterministic.RULE_VERSION

    def test_archive_exposes_the_same_entry_point(self):
        import inspect
        assert list(inspect.signature(frozen_v0_1_0.adjudicate).parameters) == ["packet"]


class TestCommittedResultsAreReproducible:
    """The committed v0.1.0 artefact must be regenerable from the archive."""

    def test_results_file_exists(self):
        assert RESULTS.exists(), (
            "the pilot's only unbiased held-out estimate is missing"
        )

    def test_every_row_is_stamped_v0_1_0(self):
        rows = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(rows) == 24
        for r in rows:
            assert r["E0"]["rule_version"] == "dev-calibration-0.1.0", r["scenario_id"]
            assert r["E3"]["rule_version"] == "dev-calibration-0.1.0", r["scenario_id"]

    def test_regeneration_is_byte_identical(self):
        """The load-bearing test: --verify must pass against the committed file."""
        proc = subprocess.run(
            [sys.executable, "reproduce_v0_1_0.py", "--verify"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"v0.1.0 is NOT reproducible from the archive.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        assert "VERIFIED" in proc.stdout

    def test_headline_metric_holds(self):
        """7/18 causal correctness — the number the README leads with.

        Scored against the CURRENT corpus ground truth, so a ground-truth
        correction is expected to move it. If this fails after a correction,
        update it deliberately and cascade the README, chart and report.
        """
        from faisla.world.oracle import get_ground_truth, reset_cache
        reset_cache()
        rows = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        held = [r for r in rows if r["split"] == "holdout"]
        correct = sum(
            1 for r in held
            if r["E3"]["causal_category"]
            == get_ground_truth(r["scenario_id"]).causal_category.value
        )
        assert (correct, len(held)) == (7, 18)
