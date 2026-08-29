"""
FAISLA — Inter-rater Agreement Computation

Computes plain percent agreement on both scope_violation and causal_category,
across all scenarios, overall and per failure class.

This is the number that determines whether the oracle is trustworthy at all.

Two or more model reviewers
---------------------------------
§9.1 is written for "the second reviewer", singular. This module supports
N reviewers and computes every pairwise comparison, because with two
reviewers there are three distinct agreement figures:

    original vs reviewer A     — is the author's label defensible?
    original vs reviewer B     — likewise, independently
    reviewer A vs reviewer B   — is the *task* well-posed at all?

The third is not a variant of the first two. Author-vs-reviewer agreement
confounds "the author was wrong" with "the scenario is undecidable"; only
reviewer-vs-reviewer separates them. A corpus where both reviewers agree
with each other but not with the author has an author problem. One where
the reviewers disagree with each other has a schema problem.

Duplicate scenario_ids from a single reviewer, or a multi-reviewer file
passed where one reviewer is expected, raise rather than silently
collapsing to whichever row happened to land last.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from faisla.labeling.schema import GroundTruthReview
from faisla.world.models import CausalCategory, FailureClass, GroundTruth


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REVIEW_PATH = _PROJECT_ROOT / "data" / "labels" / "ground_truth_review.jsonl"
AGREEMENT_OUTPUT_PATH = _PROJECT_ROOT / "results" / "agreement.json"

# A (scope_violation, causal_category, notes) triple keyed by scenario_id.
LabelSet = dict[str, tuple[bool, CausalCategory, str]]

AUTHOR_ID = "original_author"


def load_reviews(path: Path = REVIEW_PATH) -> list[GroundTruthReview]:
    """Load reviewer labels from JSONL. May contain multiple reviewers."""
    reviews = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                reviews.append(GroundTruthReview.model_validate_json(line))
    return reviews


def group_by_reviewer(
    reviews: list[GroundTruthReview],
) -> dict[str, list[GroundTruthReview]]:
    """Partition reviews by reviewer_id, preserving order within each group."""
    grouped: dict[str, list[GroundTruthReview]] = defaultdict(list)
    for r in reviews:
        grouped[r.reviewer_id].append(r)
    return dict(grouped)


def _labels_from_reviews(reviews: list[GroundTruthReview]) -> LabelSet:
    """Index one reviewer's rows by scenario_id, rejecting duplicates.

    A duplicate scenario_id means the reviewer labelled the same scenario
    twice; silently keeping the last row would quietly discard a judgment.
    """
    labels: LabelSet = {}
    for r in reviews:
        if r.scenario_id in labels:
            raise ValueError(
                f"Reviewer {r.reviewer_id!r} has duplicate rows for "
                f"{r.scenario_id}. Refusing to guess which one counts."
            )
        labels[r.scenario_id] = (r.scope_violation, r.causal_category, r.notes)
    return labels


def _labels_from_ground_truths(ground_truths: dict[str, GroundTruth]) -> LabelSet:
    """Adapt the author's GroundTruth records into the common label shape."""
    return {
        sid: (gt.scope_violation, gt.causal_category, gt.rationale)
        for sid, gt in ground_truths.items()
    }


def compute_pair_agreement(
    labels_a: LabelSet,
    labels_b: LabelSet,
    failure_classes: dict[str, FailureClass] | None = None,
    *,
    rater_a: str = AUTHOR_ID,
    rater_b: str = "reviewer",
    role_a: str = "author",
    role_b: str = "reviewer",
) -> dict:
    """Plain percent agreement between any two raters over shared scenarios.

    Symmetric: no rater is privileged as "correct". Only scenarios both
    raters labelled are scored; the rest are reported as `skipped`.

    `role_a`/`role_b` name the per-scenario detail keys, so an
    author-vs-reviewer call emits `author_*`/`reviewer_*` exactly as before.
    """
    scope_matches = 0
    causal_matches = 0
    total = 0
    details = []

    class_scope_matches: dict[str, int] = defaultdict(int)
    class_causal_matches: dict[str, int] = defaultdict(int)
    class_counts: dict[str, int] = defaultdict(int)

    shared = sorted(set(labels_a) & set(labels_b))
    skipped = sorted(set(labels_a) ^ set(labels_b))

    for sid in shared:
        a_scope, a_causal, a_notes = labels_a[sid]
        b_scope, b_causal, b_notes = labels_b[sid]
        total += 1

        scope_match = a_scope == b_scope
        causal_match = a_causal == b_causal

        if scope_match:
            scope_matches += 1
        if causal_match:
            causal_matches += 1

        fc_key = (
            failure_classes[sid].value
            if failure_classes and sid in failure_classes
            else "UNKNOWN"
        )
        class_counts[fc_key] += 1
        if scope_match:
            class_scope_matches[fc_key] += 1
        if causal_match:
            class_causal_matches[fc_key] += 1

        details.append({
            "scenario_id": sid,
            "failure_class": fc_key,
            f"{role_a}_scope_violation": a_scope,
            f"{role_b}_scope_violation": b_scope,
            "scope_match": scope_match,
            f"{role_a}_causal_category": a_causal.value,
            f"{role_b}_causal_category": b_causal.value,
            "causal_match": causal_match,
            f"{role_a}_notes": a_notes,
            f"{role_b}_notes": b_notes,
        })

    per_class = {}
    for fc_key in sorted(class_counts):
        count = class_counts[fc_key]
        per_class[fc_key] = {
            "count": count,
            "scope_agreement": class_scope_matches[fc_key] / count if count else 0.0,
            "causal_agreement": class_causal_matches[fc_key] / count if count else 0.0,
            "scope_matches": class_scope_matches[fc_key],
            "causal_matches": class_causal_matches[fc_key],
        }

    return {
        "rater_a": rater_a,
        "rater_b": rater_b,
        "total_scenarios": total,
        "skipped_scenarios": skipped,
        "scope_violation_agreement": scope_matches / total if total else 0.0,
        "causal_category_agreement": causal_matches / total if total else 0.0,
        "scope_matches": scope_matches,
        "causal_matches": causal_matches,
        "per_class": per_class,
        "details": details,
    }


def compute_agreement(
    ground_truths: dict[str, GroundTruth],
    reviews: list[GroundTruthReview],
    failure_classes: dict[str, FailureClass] | None = None,
    *,
    reviewer_id: str | None = None,
) -> dict:
    """Agreement between the original author and ONE reviewer.

    If `reviews` contains more than one reviewer_id, this raises unless
    `reviewer_id` names which one to score. It does not pick for you:
    the previous behaviour indexed reviews by scenario_id alone, so a
    two-reviewer file silently collapsed to whichever reviewer's rows came
    last in the file and reported a clean-looking 24-scenario result for it.

    For multiple reviewers use `compute_all_pairwise`.
    """
    grouped = group_by_reviewer(reviews)

    if reviewer_id is not None:
        if reviewer_id not in grouped:
            raise KeyError(
                f"No reviews from {reviewer_id!r}. Present: {sorted(grouped)}"
            )
        selected = grouped[reviewer_id]
    elif len(grouped) == 1:
        reviewer_id, selected = next(iter(grouped.items()))
    else:
        raise ValueError(
            f"Reviews contain {len(grouped)} reviewers ({sorted(grouped)}). "
            f"Pass reviewer_id=... to score one, or use compute_all_pairwise() "
            f"to score every pair. Refusing to silently collapse them."
        )

    return compute_pair_agreement(
        _labels_from_ground_truths(ground_truths),
        _labels_from_reviews(selected),
        failure_classes,
        rater_a=AUTHOR_ID,
        rater_b=reviewer_id,
        role_a="author",
        role_b="reviewer",
    )


def compute_all_pairwise(
    ground_truths: dict[str, GroundTruth],
    reviews: list[GroundTruthReview],
    failure_classes: dict[str, FailureClass] | None = None,
) -> dict[str, dict]:
    """Every pairwise comparison: author vs each reviewer, and reviewer vs reviewer.

    Keys are "<rater_a>__vs__<rater_b>", author-involving pairs first, then
    reviewer-vs-reviewer pairs in sorted reviewer order.
    """
    grouped = group_by_reviewer(reviews)
    reviewer_ids = sorted(grouped)
    author_labels = _labels_from_ground_truths(ground_truths)
    reviewer_labels = {rid: _labels_from_reviews(grouped[rid]) for rid in reviewer_ids}

    results: dict[str, dict] = {}

    for rid in reviewer_ids:
        results[f"{AUTHOR_ID}__vs__{rid}"] = compute_pair_agreement(
            author_labels,
            reviewer_labels[rid],
            failure_classes,
            rater_a=AUTHOR_ID,
            rater_b=rid,
            role_a="author",
            role_b="reviewer",
        )

    for i, rid_a in enumerate(reviewer_ids):
        for rid_b in reviewer_ids[i + 1:]:
            results[f"{rid_a}__vs__{rid_b}"] = compute_pair_agreement(
                reviewer_labels[rid_a],
                reviewer_labels[rid_b],
                failure_classes,
                rater_a=rid_a,
                rater_b=rid_b,
                role_a="rater_a",
                role_b="rater_b",
            )

    return results


def per_class_agreement_dicts(result: dict) -> tuple[dict[str, float], dict[str, float]]:
    """Extract the two per-class float dicts that evaluate_kill_test() consumes."""
    scope = {k: v["scope_agreement"] for k, v in result["per_class"].items()}
    causal = {k: v["causal_agreement"] for k, v in result["per_class"].items()}
    return scope, causal


def save_agreement(agreement: dict, output_path: Path = AGREEMENT_OUTPUT_PATH) -> None:
    """Save agreement results to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(agreement, f, indent=2)
