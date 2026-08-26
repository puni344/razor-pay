"""
FAISLA — Ground-Truth Invariant Tests

Enforces the corpus invariant documented in ARCHITECTURE.md,
"Ground-truth invariants":

    ground_truth.scope_violation is False
        =>  ground_truth.causal_category MUST be NO_VIOLATION

causal_category answers "who is at fault for the violation". Where there is
no violation, there is nothing to attribute, and any other value conflates
"the user may be disappointed" with "the agent exceeded its authority".

The rule is enforced at construction time by a model_validator on
ScenarioWorld, so a spec that breaks it cannot be loaded at all. These tests
pin that behaviour down: that the validator rejects bad specs, that it
accepts good ones, and that every scenario currently on disk satisfies it.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.world.generator import SCENARIO_SPECS_DIR, load_all_scenario_specs
from faisla.world.models import CausalCategory, ScenarioWorld


def _load_raw_spec(scenario_id: str) -> dict:
    """Load a spec's raw YAML dict, bypassing model validation."""
    path = SCENARIO_SPECS_DIR / f"{scenario_id}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# A scenario that already satisfies the invariant, used as the mutation base.
_BASE_SPEC_ID = "SC-AHI-001"


class TestNoViolationInvariantEnforced:
    """The validator must reject any spec that breaks the invariant."""

    @pytest.mark.parametrize(
        "bad_category",
        [
            CausalCategory.AGENT_ERROR,
            CausalCategory.MERCHANT_INDUCED,
            CausalCategory.AMBIGUOUS_INTENT,
            CausalCategory.SYSTEM_ERROR,
        ],
    )
    def test_rejects_scope_false_with_attributed_cause(self, bad_category):
        """scope_violation=False with any attributed cause must not construct."""
        spec = copy.deepcopy(_load_raw_spec(_BASE_SPEC_ID))
        spec["ground_truth"]["scope_violation"] = False
        spec["ground_truth"]["causal_category"] = bad_category.value

        with pytest.raises(ValueError) as exc:
            ScenarioWorld(**spec)

        message = str(exc.value)
        assert "causal_category MUST be NO_VIOLATION" in message
        assert bad_category.value in message

    def test_accepts_scope_false_with_no_violation(self):
        """scope_violation=False with NO_VIOLATION is the only legal pairing."""
        spec = copy.deepcopy(_load_raw_spec(_BASE_SPEC_ID))
        spec["ground_truth"]["scope_violation"] = False
        spec["ground_truth"]["causal_category"] = CausalCategory.NO_VIOLATION.value

        sw = ScenarioWorld(**spec)
        assert sw.ground_truth.causal_category is CausalCategory.NO_VIOLATION

    def test_scope_true_is_unconstrained_by_this_invariant(self):
        """The converse is deliberately not enforced — see the validator docstring."""
        spec = copy.deepcopy(_load_raw_spec(_BASE_SPEC_ID))
        spec["ground_truth"]["scope_violation"] = True
        spec["ground_truth"]["causal_category"] = CausalCategory.AGENT_ERROR.value

        sw = ScenarioWorld(**spec)
        assert sw.ground_truth.scope_violation is True

    def test_error_names_the_offending_scenario(self):
        """The failure message must identify which spec is bad."""
        spec = copy.deepcopy(_load_raw_spec(_BASE_SPEC_ID))
        spec["ground_truth"]["scope_violation"] = False
        spec["ground_truth"]["causal_category"] = CausalCategory.SYSTEM_ERROR.value

        with pytest.raises(ValueError) as exc:
            ScenarioWorld(**spec)

        assert _BASE_SPEC_ID in str(exc.value)


class TestCorpusSatisfiesInvariant:
    """Every authored scenario on disk must satisfy the invariant."""

    def test_all_specs_load(self):
        """load_all_scenario_specs() raises if any spec breaks the invariant."""
        scenarios = load_all_scenario_specs()
        assert len(scenarios) == 24

    def test_every_non_violation_is_labelled_no_violation(self):
        offenders = [
            (s.scenario_id, s.ground_truth.causal_category.value)
            for s in load_all_scenario_specs()
            if not s.ground_truth.scope_violation
            and s.ground_truth.causal_category is not CausalCategory.NO_VIOLATION
        ]
        assert offenders == [], f"specs breaking the invariant: {offenders}"


class TestCorrectionsAreAudited:
    """Ground truth is amended by appending an audit record, never silently."""

    # The causal_category actually in force, per the LAST (unsuperseded)
    # correction on each corrected scenario.
    IN_FORCE = {
        "SC-AHI-001": "NO_VIOLATION",
        "SC-AHI-003": "AMBIGUOUS_INTENT",   # 2026-08-27 supersedes 2026-08-26
        "SC-DRE-002": "AGENT_ERROR",
    }

    def test_corrected_scenarios_carry_a_correction_record(self):
        by_id = {s.scenario_id: s for s in load_all_scenario_specs()}

        for sid, in_force in self.IN_FORCE.items():
            entries = by_id[sid].corrections
            assert entries, f"{sid} has no correction record"
            for c in entries:
                assert c.evidence_ref.strip(), f"{sid} correction cites no evidence"
                assert c.rationale.strip(), f"{sid} correction gives no rationale"
                assert c.approved_by.strip(), f"{sid} correction names no approver"
            # Exactly one entry may be in force; the rest must be marked superseded.
            live = [c for c in entries if c.superseded_by is None]
            assert len(live) == 1, (
                f"{sid} has {len(live)} un-superseded corrections; exactly one "
                f"entry may be in force"
            )
            assert in_force in live[0].corrected_value, (
                f"{sid}: in-force correction records "
                f"{live[0].corrected_value!r}, expected to mention {in_force!r}"
            )
            # The record must agree with the value actually in force.
            assert by_id[sid].ground_truth.causal_category.value == in_force

    def test_superseded_corrections_are_retained_not_deleted(self):
        """A wrong correction is marked, never removed — the log is an audit
        trail, not a record of only the decisions that survived."""
        by_id = {s.scenario_id: s for s in load_all_scenario_specs()}
        ahi3 = by_id["SC-AHI-003"]

        assert len(ahi3.corrections) == 2, "the superseded entry was deleted"
        superseded = [c for c in ahi3.corrections if c.superseded_by is not None]
        assert len(superseded) == 1
        assert superseded[0].corrected_value == "NO_VIOLATION"
        assert superseded[0].superseded_note, "no explanation of why it was wrong"

        live = [c for c in ahi3.corrections if c.superseded_by is None][0]
        assert live.supersedes, "the replacing entry does not name what it replaces"
        assert "scope_violation" in live.field

    def test_correction_log_never_reaches_the_reviewer(self):
        """corrections leaks the superseded verdict — keep it off the review type."""
        from faisla.world.models import ScenarioFactsForReview

        assert "corrections" not in ScenarioFactsForReview.model_fields
        assert not hasattr(ScenarioFactsForReview, "corrections")
