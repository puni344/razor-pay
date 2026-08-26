"""
FAISLA — World Oracle

Exposes exactly two functions:
  - get_ground_truth(scenario_id) -> GroundTruth
  - get_review_facts(scenario_id) -> ScenarioFactsForReview

get_ground_truth is used ONLY by evaluation/ for scoring.
get_review_facts is used ONLY by the second-labeler workflow (§9.1).

CRITICAL: Neither function may be imported anywhere under adjudication/
or evidence/. This is enforced by test_no_leakage.py.

get_review_facts constructs ScenarioFactsForReview directly from the
authored fields — never by taking a ScenarioWorld instance and stripping
ground_truth off it at the call site.
"""

from __future__ import annotations

from pathlib import Path

from faisla.world.generator import load_all_scenario_specs, load_rendered_scenarios
from faisla.world.models import (
    GroundTruth,
    ScenarioFactsForReview,
    ScenarioWorld,
)


# Module-level cache
_scenarios_cache: dict[str, ScenarioWorld] | None = None


def _load_scenarios() -> dict[str, ScenarioWorld]:
    """Load scenarios lazily and cache them."""
    global _scenarios_cache
    if _scenarios_cache is None:
        try:
            scenarios = load_rendered_scenarios()
        except FileNotFoundError:
            scenarios = load_all_scenario_specs()
        _scenarios_cache = {s.scenario_id: s for s in scenarios}
    return _scenarios_cache


def reset_cache() -> None:
    """Clear the cached scenarios. Used in testing."""
    global _scenarios_cache
    _scenarios_cache = None


def get_ground_truth(scenario_id: str) -> GroundTruth:
    """Return the ground truth for a scenario.

    Used ONLY by evaluation/ for scoring. Must never be imported by
    adjudication/ or evidence/.
    """
    scenarios = _load_scenarios()
    if scenario_id not in scenarios:
        raise KeyError(f"Scenario {scenario_id} not found")
    return scenarios[scenario_id].ground_truth


def get_review_facts(scenario_id: str) -> ScenarioFactsForReview:
    """Return scenario facts for the second reviewer, without ground truth.

    Constructs ScenarioFactsForReview directly from the scenario fields.
    NEVER takes a ScenarioWorld and strips ground_truth off it — the type
    itself cannot carry ground_truth.
    """
    scenarios = _load_scenarios()
    if scenario_id not in scenarios:
        raise KeyError(f"Scenario {scenario_id} not found")

    sw = scenarios[scenario_id]

    # Construct ScenarioFactsForReview from individual fields.
    # This is deliberately NOT sw.dict(exclude={...}) — we explicitly name
    # each field so the type itself enforces what the reviewer can see.
    # ambiguity_detail is deliberately NOT passed — redacted to avoid
    # telegraphing the author's intended answer to the reviewer.
    return ScenarioFactsForReview(
        scenario_id=sw.scenario_id,
        failure_class=sw.failure_class,
        split=sw.split,
        mandate=sw.mandate,
        user_intent=sw.user_intent,
        agent_action=sw.agent_action,
        merchant_behavior=sw.merchant_behavior,
        execution_state=sw.execution_state,
        ambiguous_instruction=sw.ambiguous_instruction,
        # no ambiguity_detail — redacted from review view
        payment_outcome=sw.payment_outcome,
    )


def get_all_scenario_ids() -> list[str]:
    """Return all scenario IDs in sorted order."""
    return sorted(_load_scenarios().keys())


def get_scenario(scenario_id: str) -> ScenarioWorld:
    """Return the full ScenarioWorld. Only for use in evaluation/."""
    scenarios = _load_scenarios()
    if scenario_id not in scenarios:
        raise KeyError(f"Scenario {scenario_id} not found")
    return scenarios[scenario_id]
