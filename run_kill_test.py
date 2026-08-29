"""Feed the §9.1 agreement figures into evaluate_kill_test().

evaluate_kill_test() consumes ONE scope_agreement / causal_agreement pair.
With two model reviewers there are three candidate comparisons and the
brief does not say which one §13 is meant to consume, so this script runs all
three rather than adopting a convention silently.

The flip parameters (E0/E3 sufficiency) belong to Step 5 and do not exist yet.
Rather than invent them, this script isolates the AGREEMENT GATE: it sets every
flip parameter to the value most favourable to CONTINUE, so any non-CONTINUE
verdict is attributable to agreement alone and is determinate today. Where a
comparison clears the agreement gate, the verdict is reported as pending Step 5
rather than guessed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_ground_truth, get_all_scenario_ids, get_scenario, reset_cache
from faisla.labeling.agreement import (
    compute_all_pairwise,
    load_reviews,
    per_class_agreement_dicts,
)
from faisla.evaluation.kill_test import evaluate_kill_test

reset_cache()

scenario_ids = get_all_scenario_ids()
ground_truths = {sid: get_ground_truth(sid) for sid in scenario_ids}
scenarios = {sid: get_scenario(sid) for sid in scenario_ids}
failure_classes = {sid: s.failure_class for sid, s in scenarios.items()}

HELD_OUT_NON_DUP = len([
    s for s in scenarios.values()
    if s.split == "holdout"
    and s.failure_class.value != "DUPLICATE_OR_RETRY_EXECUTION"
])

results = compute_all_pairwise(ground_truths, load_reviews(), failure_classes)

# Flip inputs set to the most CONTINUE-favourable values possible.
# Any non-CONTINUE verdict below is therefore forced by agreement alone.
FLIP_OPTIMAL = dict(
    held_out_non_dup_count=HELD_OUT_NON_DUP,
    flip_count=HELD_OUT_NON_DUP,      # 100% flip rate, well over the 20% floor
    reverse_flip_count=0,
    e0_resolves_all=False,
    flips_are_manufactured=False,
    flip_rationales_confirmed=True,
)

print(f"held_out_non_dup_count = {HELD_OUT_NON_DUP} (18 holdout - 3 holdout DRE)")
print("Flip parameters set to their CONTINUE-optimal values (Step 5 data absent).")
print("=> any non-CONTINUE verdict below is forced by agreement alone.\n")

print("=" * 84)
print(f"{'Comparison':<48} | {'Scope':>7} | {'Causal':>7} | Verdict")
print("=" * 84)

verdicts = {}
for key, r in results.items():
    scope_pc, causal_pc = per_class_agreement_dicts(r)
    verdict = evaluate_kill_test(
        scope_agreement=r["scope_violation_agreement"],
        causal_agreement=r["causal_category_agreement"],
        per_class_scope_agreement=scope_pc,
        per_class_causal_agreement=causal_pc,
        **FLIP_OPTIMAL,
    )
    verdicts[key] = verdict
    label = f"{r['rater_a']} vs {r['rater_b']}"
    if len(label) > 46:
        label = label[:45] + "…"
    note = "" if verdict != "CONTINUE" else "  (agreement gate cleared; pending Step 5)"
    print(f"{label:<48} | {r['scope_violation_agreement']:>6.1%} | "
          f"{r['causal_category_agreement']:>6.1%} | {verdict}{note}")

print("=" * 84)
print()

# Which gate fired, explicitly.
for key, r in results.items():
    scope = r["scope_violation_agreement"]
    causal = r["causal_category_agreement"]
    print(f"{r['rater_a']} vs {r['rater_b']}: {verdicts[key]}")
    if scope < 0.70 or causal < 0.70:
        print("  gate: agreement < 70% -> KILL/INCONCLUSIVE branch")
    elif (0.70 <= scope < 0.80) or (0.70 <= causal < 0.80):
        which = "scope" if 0.70 <= scope < 0.80 else "causal"
        val = scope if which == "scope" else causal
        print(f"  gate: {which} agreement {val:.1%} in the 70-80% gray zone -> INCONCLUSIVE")
        print("        determinate today; no Step 5 data can change it")
    else:
        print("  gate: both >= 80%, agreement gate cleared")
        print("        final verdict depends on Step 5 flip data (not yet collected)")
    print()

if len(set(verdicts.values())) > 1:
    print("!! The verdict is NOT invariant across the three comparisons.")
    print("!! Which comparison §13 consumes must be decided before this is quoted.")
else:
    print(f"All comparisons agree: {next(iter(verdicts.values()))}")
