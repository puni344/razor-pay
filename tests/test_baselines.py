"""
FAISLA — Trivial baseline guard tests

The README publishes the flag-reader and constant-scope baselines next to the
adjudicator's own numbers, and the comparison is unflattering: on the held-out
split both trivial baselines BEAT the adjudicator. That is the point — it is
evidence about how the corpus was authored, not about rule engines — but a
published number that nothing pins will drift.

These tests pin three things:

  1. the flags the baseline reads are mutually exclusive, so the one-flag ->
     one-category mapping encodes no hidden precedence decision;
  2. instruction_flagged_ambiguous is True on exactly the four AHI scenarios,
     which is the specific claim the README makes about it;
  3. the published baseline and adjudicator figures, exactly.

If (3) fails after a deliberate corpus change, update it and cascade the
README — do not delete the assertion.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from baselines import FLAG_TO_CAUSE, flag_reader, load_e3, main
from faisla.world.oracle import reset_cache


class TestBaselineIsHonestlyConstructed:
    def test_flags_are_mutually_exclusive(self):
        """No scenario sets two of them, so no precedence rule is smuggled in."""
        e3 = load_e3()
        for sid, row in e3.items():
            ctx = row.get("agent_context", {})
            on = [f for f, _ in FLAG_TO_CAUSE if ctx.get(f)]
            assert len(on) <= 1, f"{sid} sets {on}; the mapping would need a precedence rule"

    def test_instruction_flagged_ambiguous_is_exactly_the_ahi_scenarios(self):
        """The README states this precisely; pin it."""
        e3 = load_e3()
        flagged = sorted(
            s for s, r in e3.items()
            if r.get("agent_context", {}).get("instruction_flagged_ambiguous")
        )
        assert flagged == ["SC-AHI-001", "SC-AHI-002", "SC-AHI-003", "SC-AHI-004"]
        assert len(e3) - len(flagged) == 20

    def test_the_reader_really_is_trivial(self):
        """Four lookups and a constant — no mandate, no amount, no ladder."""
        assert flag_reader({"cart_manipulated": True}) == "MERCHANT_INDUCED"
        assert flag_reader({"catalog_injection_present": True}) == "MERCHANT_INDUCED"
        assert flag_reader({"system_state_inconsistent": True}) == "SYSTEM_ERROR"
        assert flag_reader({"instruction_flagged_ambiguous": True}) == "AMBIGUOUS_INTENT"
        assert flag_reader({}) == "AGENT_ERROR"


class TestPublishedBaselineFigures:
    """The exact numbers the README prints."""

    def test_holdout_figures(self):
        reset_cache()
        r = main()["holdout"]
        assert r["n"] == 18
        assert r["baseline_causal"] == 17
        assert r["baseline_scope"] == 17
        assert r["adjudicator_causal"] == 11
        assert r["adjudicator_scope"] == 12

    def test_dev_figures(self):
        reset_cache()
        r = main()["dev"]
        assert r["n"] == 6
        assert r["baseline_causal"] == 3
        assert r["baseline_scope"] == 5
        assert r["adjudicator_causal"] == 4
        assert r["adjudicator_scope"] == 6

    def test_the_adjudicator_loses_on_holdout(self):
        """The uncomfortable fact the README is built around.

        Asserted explicitly so that if a future change makes the adjudicator
        beat the floor, this test fails and forces the README to be rewritten
        rather than left overstating the problem.
        """
        reset_cache()
        r = main()["holdout"]
        assert r["adjudicator_causal"] < r["baseline_causal"]
        assert r["adjudicator_scope"] < r["baseline_scope"]
