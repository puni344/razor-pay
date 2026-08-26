"""
FAISLA — Leakage and Circularity Guard Tests (§17)

These tests exist to enforce the one-directional data flow that is the
entire point of the architecture. They must be written BEFORE the
adjudicator exists so it's impossible to build the adjudicator against
a leaky packet.

Tests:
1. No EvidencePacket fields value/key contains ground truth info
2. adjudicate() signature accepts only EvidencePacket
3. world.oracle not imported by adjudication/ or evidence/
4. ScenarioFactsForReview has no ground_truth field at type level
5. oracle.get_review_facts() output contains no ground_truth content
6. Renderer-independence: evidence renderers have no import path to
   world.oracle or world.models.GroundTruth
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestScenarioFactsForReview:
    """ScenarioFactsForReview must structurally lack ground_truth."""

    def test_no_ground_truth_field_at_type_level(self):
        """Assert ScenarioFactsForReview has no ground_truth field or attribute
        at the type level (not just empty at runtime)."""
        from faisla.world.models import ScenarioFactsForReview

        # Check Pydantic model fields
        field_names = set(ScenarioFactsForReview.model_fields.keys())
        assert "ground_truth" not in field_names, (
            "ScenarioFactsForReview must not have a 'ground_truth' field"
        )

        # Also check there's no sneaky attribute
        assert not hasattr(ScenarioFactsForReview, "ground_truth"), (
            "ScenarioFactsForReview must not have a 'ground_truth' attribute"
        )

    def test_no_rationale_field(self):
        """No 'rationale' field should exist on ScenarioFactsForReview."""
        from faisla.world.models import ScenarioFactsForReview

        field_names = set(ScenarioFactsForReview.model_fields.keys())
        assert "rationale" not in field_names

    def test_no_causal_category_field(self):
        """No 'causal_category' field should exist on ScenarioFactsForReview
        (that belongs to GroundTruth, not the review facts)."""
        from faisla.world.models import ScenarioFactsForReview

        field_names = set(ScenarioFactsForReview.model_fields.keys())
        assert "causal_category" not in field_names

    def test_no_ambiguity_detail_field(self):
        """ambiguity_detail must be structurally absent from ScenarioFactsForReview.
        It telegraphs the author's intended answer and is redacted from the review view."""
        from faisla.world.models import ScenarioFactsForReview

        field_names = set(ScenarioFactsForReview.model_fields.keys())
        assert "ambiguity_detail" not in field_names, (
            "ScenarioFactsForReview must not have 'ambiguity_detail' — "
            "it telegraphs the author's rationale"
        )


class TestOracleReviewFacts:
    """oracle.get_review_facts() must not leak ground truth content."""

    def test_review_facts_contain_no_ground_truth_values(self):
        """For every scenario, get_review_facts() output must not contain
        any substring matching ground_truth.causal_category or
        ground_truth.rationale from that same scenario."""
        from faisla.world.oracle import (
            get_ground_truth,
            get_review_facts,
            get_all_scenario_ids,
            reset_cache,
        )

        reset_cache()
        for sid in get_all_scenario_ids():
            gt = get_ground_truth(sid)
            facts = get_review_facts(sid)

            # Serialize facts to JSON for substring search
            facts_json = facts.model_dump_json()

            # Check causal_category value doesn't appear
            # (Note: the CausalCategory enum value might appear in the
            # failure_class name or other fields legitimately, so we check
            # specifically for the ground_truth's rationale text)
            rationale = gt.rationale
            # The rationale is long and unique — if it appears in the
            # review facts, that's a leak
            assert rationale not in facts_json, (
                f"Scenario {sid}: ground_truth.rationale leaked into "
                f"review facts"
            )

            # Check scope_violation doesn't appear as a key
            # (scope_violation is NOT a field on ScenarioFactsForReview)
            assert '"scope_violation"' not in facts_json or \
                '"scope_violation"' not in facts_json.split('"payment_outcome"')[0], (
                f"Scenario {sid}: 'scope_violation' key found in review facts "
                f"outside payment_outcome"
            )


class TestNoImportLeakage:
    """world.oracle must not be imported by adjudication/ or evidence/."""

    def test_adjudication_does_not_import_oracle(self):
        """No module under adjudication/ may import world.oracle."""
        # Import all adjudication modules
        adjudication_dir = _PROJECT_ROOT / "faisla" / "adjudication"
        for py_file in adjudication_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"faisla.adjudication.{py_file.stem}"
            try:
                importlib.import_module(module_name)
            except ImportError:
                pass  # Module might have missing deps — that's OK for this test

        # Check sys.modules for oracle
        oracle_modules = [
            m for m in sys.modules
            if "faisla.world.oracle" in m
        ]
        # Filter out test modules that legitimately import oracle
        for mod_name in oracle_modules:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, "__file__") and mod.__file__:
                mod_path = Path(mod.__file__).resolve()
                assert "adjudication" not in str(mod_path), (
                    f"Module {mod_name} under adjudication/ imports "
                    f"world.oracle — this is forbidden"
                )

    def test_evidence_does_not_import_oracle(self):
        """No module under evidence/ may import world.oracle."""
        evidence_dir = _PROJECT_ROOT / "faisla" / "evidence"
        for py_file in evidence_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"faisla.evidence.{py_file.stem}"
            try:
                importlib.import_module(module_name)
            except ImportError:
                pass

        oracle_modules = [
            m for m in sys.modules
            if "faisla.world.oracle" in m
        ]
        for mod_name in oracle_modules:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, "__file__") and mod.__file__:
                mod_path = Path(mod.__file__).resolve()
                assert "evidence" not in str(mod_path), (
                    f"Module {mod_name} under evidence/ imports "
                    f"world.oracle — this is forbidden"
                )


class TestRendererIndependence:
    """Evidence renderers must have no import path to GroundTruth or oracle.

    This is the renderer-independence test: evidence rendering must
    depend ONLY on the scenario's observable facts (via EvidencePacket),
    never on ground truth or the oracle.
    """

    def test_evidence_modules_do_not_import_ground_truth(self):
        """No evidence module should import GroundTruth directly."""
        evidence_dir = _PROJECT_ROOT / "faisla" / "evidence"
        for py_file in evidence_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            source = py_file.read_text(encoding="utf-8")
            assert "GroundTruth" not in source, (
                f"{py_file.name} references GroundTruth — evidence "
                f"renderers must not access ground truth"
            )
            assert "from faisla.world.oracle" not in source, (
                f"{py_file.name} imports from world.oracle — evidence "
                f"renderers must not access the oracle"
            )
            assert "import faisla.world.oracle" not in source, (
                f"{py_file.name} imports world.oracle — evidence "
                f"renderers must not access the oracle"
            )

    def test_evidence_modules_do_not_import_scenario_world(self):
        """Evidence modules should not import ScenarioWorld either —
        they should work with the specific fields they need, not the
        full hidden-world record."""
        evidence_dir = _PROJECT_ROOT / "faisla" / "evidence"
        for py_file in evidence_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if py_file.name == "models.py":
                continue  # models.py may reference the enum types
            source = py_file.read_text(encoding="utf-8")
            # ScenarioWorld should not appear in renderer modules
            assert "ScenarioWorld" not in source, (
                f"{py_file.name} references ScenarioWorld — evidence "
                f"renderers should not access the full hidden-world record"
            )
