"""
FAISLA — Deterministic Adjudicator Tests

These pin the properties that make an adjudication result meaningful:
determinism, independence from the scenario identity, and the absence of any
path to the oracle. They deliberately do NOT assert that any scenario gets a
particular verdict — that would be scoring against ground truth, which is
exactly what the adjudicator is forbidden to see.

Only DEV scenarios are constructed anywhere in this file.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.adjudication.deterministic import (
    RULE_VERSION,
    adjudicate,
    extract_instruction_budget,
)
from faisla.adjudication.schemas import ScopeFinding, Sufficiency
from faisla.evidence.agent_aware import render_agent_aware
from faisla.evidence.conventional import render_conventional
from faisla.evidence.models import EvidenceCondition
from faisla.world.generator import load_all_scenario_specs


@pytest.fixture(scope="module")
def dev_scenarios():
    """DEV slice only. Held-out scenarios never enter these tests."""
    scenarios = [s for s in load_all_scenario_specs() if s.split == "dev"]
    assert len(scenarios) == 6
    assert all(s.split == "dev" for s in scenarios)
    return scenarios


def _e0(s):
    return render_conventional(
        scenario_id=s.scenario_id,
        cardholder_statement=s.user_intent,
        agent_action=s.agent_action,
        merchant_behavior=s.merchant_behavior,
        execution_state=s.execution_state,
        payment_outcome=s.payment_outcome,
    )


def _e3(s):
    return render_agent_aware(
        scenario_id=s.scenario_id,
        cardholder_statement=s.user_intent,
        mandate=s.mandate,
        user_intent=s.user_intent,
        ambiguous_instruction=s.ambiguous_instruction,
        agent_action=s.agent_action,
        merchant_behavior=s.merchant_behavior,
        execution_state=s.execution_state,
        payment_outcome=s.payment_outcome,
    )


class TestDeterminism:
    def test_repeated_adjudication_is_identical(self, dev_scenarios):
        for s in dev_scenarios:
            for packet in (_e0(s), _e3(s)):
                a, b = adjudicate(packet), adjudicate(packet)
                assert a.model_dump_json() == b.model_dump_json(), s.scenario_id

    def test_result_stamps_the_rule_version(self, dev_scenarios):
        for s in dev_scenarios:
            assert adjudicate(_e0(s)).rule_version == RULE_VERSION


class TestIgnoresScenarioIdentity:
    """The adjudicator must never read the answer off the id."""

    def test_renaming_the_scenario_changes_nothing_but_the_id(self, dev_scenarios):
        for s in dev_scenarios:
            for packet in (_e0(s), _e3(s)):
                renamed = packet.model_copy(update={"scenario_id": "SC-ZZZ-999"})
                original, other = adjudicate(packet), adjudicate(renamed)

                assert other.scenario_id == "SC-ZZZ-999"
                assert other.scope_finding == original.scope_finding
                assert other.causal_category == original.causal_category
                assert other.sufficiency == original.sufficiency
                assert (
                    [f.rule_id for f in other.rules_fired]
                    == [f.rule_id for f in original.rules_fired]
                )

    def test_packet_carries_no_failure_class(self, dev_scenarios):
        """failure_class must be unreachable, not merely unused."""
        for s in dev_scenarios:
            for packet in (_e0(s), _e3(s)):
                assert "failure_class" not in packet.model_dump()
                assert not hasattr(packet, "failure_class")


class TestConditionBehaviour:
    def test_e0_never_determines_a_cause(self, dev_scenarios):
        """The conventional record has no fault signal in it at all."""
        for s in dev_scenarios:
            r = adjudicate(_e0(s))
            assert r.causal_category is None, s.scenario_id
            assert r.sufficiency is Sufficiency.INSUFFICIENT, s.scenario_id

    def test_e3_determines_scope_for_every_dev_scenario(self, dev_scenarios):
        for s in dev_scenarios:
            r = adjudicate(_e3(s))
            assert r.scope_finding is not ScopeFinding.UNDETERMINED, s.scenario_id

    def test_condition_is_carried_through(self, dev_scenarios):
        for s in dev_scenarios:
            assert adjudicate(_e0(s)).condition is EvidenceCondition.E0
            assert adjudicate(_e3(s)).condition is EvidenceCondition.E3

    def test_sufficiency_requires_both_findings(self, dev_scenarios):
        for s in dev_scenarios:
            for packet in (_e0(s), _e3(s)):
                r = adjudicate(packet)
                both = (
                    r.scope_finding is not ScopeFinding.UNDETERMINED
                    and r.causal_category is not None
                )
                assert (r.sufficiency is Sufficiency.SUFFICIENT) == both

    def test_every_result_reports_at_least_one_rule(self, dev_scenarios):
        for s in dev_scenarios:
            for packet in (_e0(s), _e3(s)):
                r = adjudicate(packet)
                assert r.rules_fired
                assert all(f.rule_id and f.observation for f in r.rules_fired)


class TestBudgetExtraction:
    """Deterministic text rules — the most restrictive match wins."""

    @pytest.mark.parametrize("text,expected", [
        ("Buy the cheapest running shoes under 3000 rupees", Decimal("3000")),
        ("Order a cotton kurta from FabIndia, budget 2000 rupees max", Decimal("2000")),
        ("Buy a basic USB-C charging cable under 500 rupees", Decimal("500")),
        ("Order the Python Crash Course book from BookWorld", None),
        ("Get something nice for Mom's birthday", None),
    ])
    def test_extraction(self, text, expected):
        assert extract_instruction_budget(text) == expected

    def test_most_restrictive_match_wins(self):
        assert extract_instruction_budget(
            "under 2000 rupees, no more than 1500"
        ) == Decimal("1500")

    def test_extraction_is_case_insensitive(self):
        assert extract_instruction_budget("UNDER 750 RUPEES") == Decimal("750")


class TestNoOracleAccess:
    """Structural: adjudication must not reach the hidden world."""

    def test_adjudication_modules_do_not_reference_forbidden_types(self):
        adj_dir = _PROJECT_ROOT / "faisla" / "adjudication"
        for py_file in adj_dir.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            assert "from faisla.world.oracle" not in source, py_file.name
            assert "import faisla.world.oracle" not in source, py_file.name
            assert "ScenarioWorld" not in source, py_file.name
            assert "get_ground_truth" not in source, py_file.name

    def test_adjudicate_accepts_a_packet_alone(self, dev_scenarios):
        """One positional argument, no side channel."""
        import inspect
        sig = inspect.signature(adjudicate)
        assert list(sig.parameters) == ["packet"]
