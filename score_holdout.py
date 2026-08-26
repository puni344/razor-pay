"""Score the frozen held-out run. Read-only: never re-adjudicates."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_ground_truth, reset_cache
from faisla.adjudication.deterministic import RULE_VERSION

RESULTS = Path(f"results/adjudication_{RULE_VERSION}.jsonl")
rows = [json.loads(l) for l in open(RESULTS, encoding="utf-8") if l.strip()]

# Scenarios the developer had prior exposure to via the Step 1-4 correction work.
PRIOR_EXPOSURE = {"SC-AHI-002", "SC-AHI-003", "SC-AHI-004", "SC-DRE-002"}
DUP_CLASS = "DUPLICATE_OR_RETRY_EXECUTION"

reset_cache()
held = [r for r in rows if r["split"] == "holdout"]

# ---------------------------------------------------------------- rule coverage
fired = Counter()
for r in rows:                       # all 24, dev + holdout
    for cond in ("E0", "E3"):
        for f in r[cond]["rules_fired"]:
            fired[f["rule_id"]] += 1

ALL_RULES = [
    "E0-S1-settled-exceeds-receipt", "E0-S2-no-authority-record",
    "E0-C1-no-fault-signal-available",
    "E3-S1-instruction-budget-exceeded", "E3-S2-category-outside-mandate",
    "E3-S3-merchant-outside-mandate", "E3-S4-mandate-ceiling-exceeded",
    "E3-S5-settled-exceeds-line-item",
    "E3-S6-settlement-not-matched-by-fulfilment",
    "E3-S7-within-delegated-authority", "E3-C0-no-violation-to-attribute",
    "E3-C1-cart-manipulated", "E3-C2-catalog-injection-present",
    "E3-C3-system-state-inconsistent",
    "E3-C4-duplicate-attribution-undetermined",
    "E3-C5-residual-agent-attribution",
]

print("=" * 84)
print("RULE COVERAGE — ALL 24 SCENARIOS (dev + held-out combined)")
print("=" * 84)
for rule in ALL_RULES:
    n = fired[rule]
    tag = "  ** NEVER FIRED ON ANY SCENARIO — UNEXERCISED **" if n == 0 else ""
    print(f"  {rule:<46} n={n}{tag}")
never = [r for r in ALL_RULES if fired[r] == 0]
print(f"\nUnexercised rules: {never if never else 'none'}")
print()


def flip(r):
    return (r["E0"]["sufficiency"] == "INSUFFICIENT"
            and r["E3"]["sufficiency"] == "SUFFICIENT")


def reverse_flip(r):
    return (r["E0"]["sufficiency"] == "SUFFICIENT"
            and r["E3"]["sufficiency"] == "INSUFFICIENT")


# ------------------------------------------------------------------ flip rates
print("=" * 84)
print("HELD-OUT FLIP RATE  (E0 INSUFFICIENT -> E3 SUFFICIENT)")
print("=" * 84)
by_class = defaultdict(list)
for r in held:
    by_class[r["failure_class"]].append(r)

print(f"{'Failure class':<40} | {'n':>2} | {'flips':>5} | {'rate':>7}")
print("-" * 84)
for fc in sorted(by_class):
    grp = by_class[fc]
    f = sum(flip(r) for r in grp)
    print(f"{fc:<40} | {len(grp):>2} | {f:>5} | {f/len(grp):>6.1%}")

all_f = sum(flip(r) for r in held)
nondup = [r for r in held if r["failure_class"] != DUP_CLASS]
nondup_f = sum(flip(r) for r in nondup)
rev = sum(reverse_flip(r) for r in held)
e0_suff = sum(r["E0"]["sufficiency"] == "SUFFICIENT" for r in nondup)

print("-" * 84)
print(f"{'POOLED — all held-out':<40} | {len(held):>2} | {all_f:>5} | {all_f/len(held):>6.1%}")
print(f"{'POOLED — held-out non-duplicate (§13)':<40} | {len(nondup):>2} | "
      f"{nondup_f:>5} | {nondup_f/len(nondup):>6.1%}")
print()
print(f"reverse flips (E0 SUFF -> E3 INSUFF): {rev}")
print(f"E0 SUFFICIENT among held-out non-dup: {e0_suff}/{len(nondup)}")
print()


# --------------------------------------------------------------- correctness
def causal_correct(r):
    gt = get_ground_truth(r["scenario_id"])
    return r["E3"]["causal_category"] == gt.causal_category.value


def scope_correct(r):
    gt = get_ground_truth(r["scenario_id"])
    finding = r["E3"]["scope_finding"]
    if finding == "UNDETERMINED":
        return False
    return (finding == "OUT_OF_SCOPE") == gt.scope_violation


def report_correctness(label, subset):
    n = len(subset)
    cc = sum(causal_correct(r) for r in subset)
    sc = sum(scope_correct(r) for r in subset)
    und = sum(r["E3"]["causal_category"] is None for r in subset)
    wrong = n - cc - und
    print(f"{label:<46} | n={n:>2} | causal {cc:>2}/{n} = {cc/n:>6.1%} "
          f"| scope {sc:>2}/{n} = {sc/n:>6.1%} | undet {und} | wrong {wrong}")


print("=" * 84)
print("HELD-OUT CORRECTNESS AT E3 — BOTH SPLITS, SIDE BY SIDE")
print("=" * 84)
clean = [r for r in held if r["scenario_id"] not in PRIOR_EXPOSURE]
report_correctness("ALL held-out", held)
report_correctness("EXCLUDING prior-exposure scenarios", clean)
print()
print(f"Excluded: {sorted(PRIOR_EXPOSURE)}")
print()

print("=" * 84)
print("PER-SCENARIO (held-out)")
print("=" * 84)
print(f"{'scenario':<12} | {'E0':<12} | {'E3 scope':<13} | {'E3 causal':<17} "
      f"| {'truth':<17} | ok | flip | prior")
print("-" * 84)
for r in sorted(held, key=lambda x: x["scenario_id"]):
    gt = get_ground_truth(r["scenario_id"])
    c = r["E3"]["causal_category"] or "—"
    print(f"{r['scenario_id']:<12} | {r['E0']['sufficiency'][:12]:<12} | "
          f"{r['E3']['scope_finding']:<13} | {c:<17} | "
          f"{gt.causal_category.value:<17} | "
          f"{'Y' if causal_correct(r) else 'n':<2} | "
          f"{'Y' if flip(r) else '.':<4} | "
          f"{'*' if r['scenario_id'] in PRIOR_EXPOSURE else ''}")

json.dump({
    "rule_version": RULE_VERSION,
    "held_out_n": len(held),
    "flips_all": all_f,
    "flips_non_dup": nondup_f,
    "held_out_non_dup_count": len(nondup),
    "reverse_flips": rev,
    "unexercised_rules": never,
}, open("results/holdout_summary.json", "w"), indent=2)
