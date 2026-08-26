"""Compute inter-rater agreement across all raters and report results.

Handles N reviewers. With two independent reviewers this computes three
pairwise comparisons:

    original_author vs reviewer A
    original_author vs reviewer B
    reviewer A      vs reviewer B

each per failure class and pooled, on both scope_violation and
causal_category, against the CORRECTED ground truth in data/scenario_specs/.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_ground_truth, get_all_scenario_ids, get_scenario, reset_cache
from faisla.labeling.agreement import (
    AUTHOR_ID,
    compute_all_pairwise,
    group_by_reviewer,
    load_reviews,
    per_class_agreement_dicts,
)

reset_cache()

scenario_ids = get_all_scenario_ids()
ground_truths = {}
failure_classes = {}
for sid in scenario_ids:
    ground_truths[sid] = get_ground_truth(sid)
    failure_classes[sid] = get_scenario(sid).failure_class

reviews = load_reviews()
grouped = group_by_reviewer(reviews)

print(f"Loaded {len(reviews)} review records from {len(grouped)} reviewer(s) "
      f"for {len(ground_truths)} scenarios")
for rid in sorted(grouped):
    print(f"  {rid}: {len(grouped[rid])} judgments")
print()

results = compute_all_pairwise(ground_truths, reviews, failure_classes)

ALL_CLASSES = sorted({fc.value for fc in failure_classes.values()})


def _pct(x):
    return f"{x:.1%}"


# ---------------------------------------------------------------- pooled table
print("=" * 78)
print("POOLED AGREEMENT (all 24 scenarios)")
print("=" * 78)
print(f"{'Comparison':<52} | {'Scope':>9} | {'Causal':>9}")
print("-" * 78)
for key, r in results.items():
    label = f"{r['rater_a']} vs {r['rater_b']}"
    if len(label) > 50:
        label = label[:49] + "…"
    print(f"{label:<52} | "
          f"{r['scope_matches']:>2}/{r['total_scenarios']:<2} {_pct(r['scope_violation_agreement']):>4} | "
          f"{r['causal_matches']:>2}/{r['total_scenarios']:<2} {_pct(r['causal_category_agreement']):>4}")
    if r["skipped_scenarios"]:
        print(f"{'':<52} |  skipped: {r['skipped_scenarios']}")
print()

# ------------------------------------------------------------- per-class table
for key, r in results.items():
    print("=" * 78)
    print(f"PER-CLASS: {r['rater_a']} vs {r['rater_b']}")
    print("=" * 78)
    print(f"{'Failure class':<40} | {'n':>2} | {'Scope':>11} | {'Causal':>11}")
    print("-" * 78)
    for fc in ALL_CLASSES:
        d = r["per_class"].get(fc)
        if d is None:
            print(f"{fc:<40} | {'-':>2} | {'n/a':>11} | {'n/a':>11}")
            continue
        print(f"{fc:<40} | {d['count']:>2} | "
              f"{d['scope_matches']}/{d['count']} {_pct(d['scope_agreement']):>6} | "
              f"{d['causal_matches']}/{d['count']} {_pct(d['causal_agreement']):>6}")
    print(f"{'POOLED':<40} | {r['total_scenarios']:>2} | "
          f"{r['scope_matches']}/{r['total_scenarios']} {_pct(r['scope_violation_agreement']):>6} | "
          f"{r['causal_matches']}/{r['total_scenarios']} {_pct(r['causal_category_agreement']):>6}")
    print()

# ------------------------------------------------------------- disagreements
for key, r in results.items():
    role_a = "author" if r["rater_a"] == AUTHOR_ID else "rater_a"
    role_b = "reviewer" if r["rater_a"] == AUTHOR_ID else "rater_b"
    bad = [d for d in r["details"] if not d["scope_match"] or not d["causal_match"]]
    print("=" * 78)
    print(f"DISAGREEMENTS: {r['rater_a']} vs {r['rater_b']}  ({len(bad)} of {r['total_scenarios']})")
    print("=" * 78)
    for d in bad:
        print(f"\n{d['scenario_id']} ({d['failure_class']}):")
        if not d["scope_match"]:
            print(f"  SCOPE:  {r['rater_a']}={d[f'{role_a}_scope_violation']}  "
                  f"{r['rater_b']}={d[f'{role_b}_scope_violation']}")
        if not d["causal_match"]:
            print(f"  CAUSAL: {r['rater_a']}={d[f'{role_a}_causal_category']}  "
                  f"{r['rater_b']}={d[f'{role_b}_causal_category']}")
        print(f"  {r['rater_b']} notes: {d[f'{role_b}_notes'][:150]}")
    print()

# ------------------------------------------------------------------- kill test
print("=" * 78)
print("KILL TEST INPUTS (per comparison)")
print("=" * 78)
print("evaluate_kill_test() takes ONE scope_agreement / causal_agreement pair.")
print("With two reviewers there are three candidates. Reporting all three;")
print("the choice of convention is flagged in the write-up, not made here.")
print()
for key, r in results.items():
    scope_pc, causal_pc = per_class_agreement_dicts(r)
    print(f"{r['rater_a']} vs {r['rater_b']}:")
    print(f"  scope_agreement  = {r['scope_violation_agreement']:.4f}")
    print(f"  causal_agreement = {r['causal_category_agreement']:.4f}")
    print(f"  per_class_scope  = { {k: round(v,4) for k,v in scope_pc.items()} }")
    print(f"  per_class_causal = { {k: round(v,4) for k,v in causal_pc.items()} }")
    print()

output_path = Path("results/agreement.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump({
        "ground_truth": "corrected (SC-AHI-001, SC-AHI-003, SC-DRE-002)",
        "reviewers": sorted(grouped),
        "comparisons": results,
    }, f, indent=2)
print(f"Saved to {output_path}")
