"""
FAISLA — Multi-Reviewer Agreement Tests

The bug these exist to prevent: compute_agreement() used to index reviews as
{r.scenario_id: r for r in reviews}, discarding reviewer_id entirely. Handed a
48-row two-reviewer file it silently kept whichever reviewer's rows came last
and reported a clean, plausible, wrong 24-scenario result. No error, no warning.

Silent collapse is the failure mode worth pinning down, so most of these tests
assert that ambiguous input RAISES rather than resolves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.labeling.agreement import (
    AUTHOR_ID,
    compute_agreement,
    compute_all_pairwise,
    compute_pair_agreement,
    group_by_reviewer,
    load_reviews,
    per_class_agreement_dicts,
)
from faisla.labeling.schema import GroundTruthReview
from faisla.world.models import CausalCategory, FailureClass, GroundTruth
from faisla.world.oracle import (
    get_all_scenario_ids,
    get_ground_truth,
    get_scenario,
    reset_cache,
)


def _review(sid, reviewer, scope, causal, notes="n"):
    return GroundTruthReview(
        scenario_id=sid,
        reviewer_id=reviewer,
        scope_violation=scope,
        causal_category=causal,
        notes=notes,
    )


def _gt(scope, causal):
    return GroundTruth(scope_violation=scope, causal_category=causal, rationale="r")


@pytest.fixture
def corpus():
    reset_cache()
    ids = get_all_scenario_ids()
    return (
        {sid: get_ground_truth(sid) for sid in ids},
        {sid: get_scenario(sid).failure_class for sid in ids},
    )


class TestNoSilentCollapse:
    """Two reviewers must never be silently reduced to one."""

    def test_compute_agreement_raises_on_multiple_reviewers(self, corpus):
        ground_truths, failure_classes = corpus
        reviews = load_reviews()
        assert len(group_by_reviewer(reviews)) == 2, "fixture expects 2 reviewers"

        with pytest.raises(ValueError) as exc:
            compute_agreement(ground_truths, reviews, failure_classes)

        message = str(exc.value)
        assert "2 reviewers" in message
        assert "reviewer_id" in message

    def test_compute_agreement_accepts_explicit_reviewer_id(self, corpus):
        ground_truths, failure_classes = corpus
        reviews = load_reviews()

        result = compute_agreement(
            ground_truths, reviews, failure_classes,
            reviewer_id="reviewer_a_independent",
        )
        assert result["rater_b"] == "reviewer_a_independent"
        assert result["total_scenarios"] == 24

    def test_unknown_reviewer_id_raises(self, corpus):
        ground_truths, failure_classes = corpus
        with pytest.raises(KeyError):
            compute_agreement(
                ground_truths, load_reviews(), failure_classes,
                reviewer_id="reviewer_nobody",
            )

    def test_single_reviewer_still_works_without_reviewer_id(self, corpus):
        """Back-compat: a genuine one-reviewer file needs no extra argument."""
        ground_truths, failure_classes = corpus
        only_reviewer_a = [
            r for r in load_reviews()
            if r.reviewer_id == "reviewer_a_independent"
        ]
        result = compute_agreement(ground_truths, only_reviewer_a, failure_classes)
        assert result["rater_b"] == "reviewer_a_independent"
        assert result["total_scenarios"] == 24

    def test_duplicate_rows_from_one_reviewer_raise(self, corpus):
        ground_truths, failure_classes = corpus
        dupes = [
            _review("SC-AHI-001", "r1", True, CausalCategory.AGENT_ERROR),
            _review("SC-AHI-001", "r1", False, CausalCategory.NO_VIOLATION),
        ]
        with pytest.raises(ValueError, match="duplicate rows"):
            compute_agreement(ground_truths, dupes, failure_classes)


class TestPairwiseCoverage:
    """All three comparisons, computed symmetrically."""

    def test_two_reviewers_yield_three_comparisons(self, corpus):
        ground_truths, failure_classes = corpus
        results = compute_all_pairwise(ground_truths, load_reviews(), failure_classes)

        assert set(results) == {
            f"{AUTHOR_ID}__vs__reviewer_a_independent",
            f"{AUTHOR_ID}__vs__reviewer_b_independent",
            "reviewer_a_independent__vs__reviewer_b_independent",
        }

    def test_every_comparison_covers_all_24_scenarios(self, corpus):
        ground_truths, failure_classes = corpus
        for r in compute_all_pairwise(ground_truths, load_reviews(), failure_classes).values():
            assert r["total_scenarios"] == 24
            assert r["skipped_scenarios"] == []
            assert sum(c["count"] for c in r["per_class"].values()) == 24

    def test_reviewer_vs_reviewer_is_independent_of_ground_truth(self, corpus):
        """Perturbing the author's labels must not move reviewer-vs-reviewer."""
        ground_truths, failure_classes = corpus
        reviews = load_reviews()
        key = "reviewer_a_independent__vs__reviewer_b_independent"

        before = compute_all_pairwise(ground_truths, reviews, failure_classes)[key]

        flipped = {
            sid: _gt(not gt.scope_violation, CausalCategory.MERCHANT_INDUCED)
            for sid, gt in ground_truths.items()
        }
        after = compute_all_pairwise(flipped, reviews, failure_classes)[key]

        assert before["scope_violation_agreement"] == after["scope_violation_agreement"]
        assert before["causal_category_agreement"] == after["causal_category_agreement"]

    def test_pair_agreement_is_symmetric(self):
        a = {"S1": (True, CausalCategory.AGENT_ERROR, "x"),
             "S2": (False, CausalCategory.NO_VIOLATION, "x")}
        b = {"S1": (True, CausalCategory.SYSTEM_ERROR, "y"),
             "S2": (False, CausalCategory.NO_VIOLATION, "y")}

        ab = compute_pair_agreement(a, b)
        ba = compute_pair_agreement(b, a)

        assert ab["scope_violation_agreement"] == ba["scope_violation_agreement"] == 1.0
        assert ab["causal_category_agreement"] == ba["causal_category_agreement"] == 0.5

    def test_non_overlapping_scenarios_are_skipped_not_scored(self):
        a = {"S1": (True, CausalCategory.AGENT_ERROR, ""),
             "S2": (True, CausalCategory.AGENT_ERROR, "")}
        b = {"S1": (True, CausalCategory.AGENT_ERROR, ""),
             "S3": (True, CausalCategory.AGENT_ERROR, "")}

        r = compute_pair_agreement(a, b)
        assert r["total_scenarios"] == 1
        assert r["skipped_scenarios"] == ["S2", "S3"]


class TestLegacyDetailKeys:
    """compute_agreement.py reads author_*/reviewer_* keys — keep them."""

    def test_author_vs_reviewer_detail_keys_unchanged(self, corpus):
        ground_truths, failure_classes = corpus
        result = compute_agreement(
            ground_truths, load_reviews(), failure_classes,
            reviewer_id="reviewer_b_independent",
        )
        d = result["details"][0]
        for key in (
            "author_scope_violation", "reviewer_scope_violation",
            "author_causal_category", "reviewer_causal_category",
            "scope_match", "causal_match", "scenario_id", "failure_class",
        ):
            assert key in d, f"missing legacy detail key {key}"


class TestKillTestInputShape:
    """per_class_agreement_dicts must produce what evaluate_kill_test consumes."""

    def test_extracts_plain_float_dicts_over_all_classes(self, corpus):
        ground_truths, failure_classes = corpus
        results = compute_all_pairwise(ground_truths, load_reviews(), failure_classes)
        expected = {fc.value for fc in FailureClass}

        for r in results.values():
            scope_pc, causal_pc = per_class_agreement_dicts(r)
            assert set(scope_pc) == set(causal_pc) == expected
            assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scope_pc.values())
            assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in causal_pc.values())
