"""
FAISLA — Kill Test Unit Tests (§17)

Feed hand-built metric fixtures for all three outcomes
(CONTINUE / KILL / INCONCLUSIVE) and assert evaluate_kill_test()
returns the right verdict for each.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faisla.evaluation.kill_test import evaluate_kill_test


# All six failure class keys for per-class agreement dicts
ALL_CLASSES = [
    "AGENT_INTERPRETATION_ERROR",
    "AMBIGUOUS_HUMAN_INSTRUCTION",
    "DUPLICATE_OR_RETRY_EXECUTION",
    "MERCHANT_OR_CART_MANIPULATION",
    "MERCHANT_PROMPT_OR_CATALOG_INJECTION",
    "SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY",
]


def _make_per_class(value: float, override: dict[str, float] | None = None) -> dict[str, float]:
    """Helper: make per-class agreement dict with uniform value, optional overrides."""
    d = {k: value for k in ALL_CLASSES}
    if override:
        d.update(override)
    return d


class TestKillTestContinue:
    def test_continue_all_conditions_met(self):
        """CONTINUE when all thresholds are met."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.85,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.85),
            held_out_non_dup_count=12,
            flip_count=4,  # 4/12 = 33% > 20%
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "CONTINUE"


class TestKillTestKill:
    def test_kill_agreement_below_70_spread_across_classes(self):
        """KILL when agreement < 70% and spread across multiple classes."""
        result = evaluate_kill_test(
            scope_agreement=0.60,
            causal_agreement=0.55,
            per_class_scope_agreement=_make_per_class(0.60),
            per_class_causal_agreement=_make_per_class(0.55),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "KILL"

    def test_kill_e0_resolves_all(self):
        """KILL when E0 already resolves all held-out scenarios."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.90,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.90),
            held_out_non_dup_count=12,
            flip_count=0,
            reverse_flip_count=0,
            e0_resolves_all=True,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "KILL"

    def test_kill_zero_flips(self):
        """KILL when no flips at all."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.90,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.90),
            held_out_non_dup_count=12,
            flip_count=0,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "KILL"

    def test_kill_manufactured_flips(self):
        """KILL when flips exist but are manufactured."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.90,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.90),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=True,
            flip_rationales_confirmed=True,
        )
        assert result == "KILL"


class TestKillTestInconclusive:
    def test_inconclusive_agreement_gray_zone(self):
        """INCONCLUSIVE when agreement in 70-80% range."""
        result = evaluate_kill_test(
            scope_agreement=0.75,
            causal_agreement=0.75,
            per_class_scope_agreement=_make_per_class(0.75),
            per_class_causal_agreement=_make_per_class(0.75),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "INCONCLUSIVE"

    def test_inconclusive_flip_rate_near_boundary(self):
        """INCONCLUSIVE when flip rate near 20% with unconfirmed rationales."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.90,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.90),
            held_out_non_dup_count=12,
            flip_count=2,  # 2/12 = 16.7%, near boundary
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=False,
        )
        assert result == "INCONCLUSIVE"

    def test_inconclusive_reverse_flips_exist(self):
        """INCONCLUSIVE when reverse flips exist (even if other conditions met)."""
        result = evaluate_kill_test(
            scope_agreement=0.90,
            causal_agreement=0.90,
            per_class_scope_agreement=_make_per_class(0.90),
            per_class_causal_agreement=_make_per_class(0.90),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=1,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "INCONCLUSIVE"


class TestKillTestAHIConcentration:
    """Test the per-class agreement routing for AHI-concentrated shortfalls."""

    def test_below_70_ahi_concentrated_returns_inconclusive(self):
        """When pooled agreement < 70% but shortfall is concentrated in AHI
        and every other class has >= 80%, return INCONCLUSIVE, not KILL."""
        result = evaluate_kill_test(
            scope_agreement=0.65,  # below 70%
            causal_agreement=0.65,
            per_class_scope_agreement=_make_per_class(
                1.0,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.0}
            ),
            per_class_causal_agreement=_make_per_class(
                1.0,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.0}
            ),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "INCONCLUSIVE"

    def test_below_70_multiple_classes_low_returns_kill(self):
        """When pooled agreement < 70% and multiple classes are low,
        return KILL (not routed to INCONCLUSIVE)."""
        result = evaluate_kill_test(
            scope_agreement=0.60,
            causal_agreement=0.60,
            per_class_scope_agreement=_make_per_class(
                0.60,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.0}
            ),
            per_class_causal_agreement=_make_per_class(
                0.60,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.0}
            ),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "KILL"

    def test_gray_zone_ahi_concentrated_returns_inconclusive(self):
        """When pooled agreement 70-80% and shortfall concentrated in AHI,
        return INCONCLUSIVE."""
        result = evaluate_kill_test(
            scope_agreement=0.75,
            causal_agreement=0.75,
            per_class_scope_agreement=_make_per_class(
                1.0,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.25}
            ),
            per_class_causal_agreement=_make_per_class(
                1.0,
                override={"AMBIGUOUS_HUMAN_INSTRUCTION": 0.25}
            ),
            held_out_non_dup_count=12,
            flip_count=4,
            reverse_flip_count=0,
            e0_resolves_all=False,
            flips_are_manufactured=False,
            flip_rationales_confirmed=True,
        )
        assert result == "INCONCLUSIVE"
