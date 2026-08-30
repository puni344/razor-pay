"""Trivial baselines — what do you get without an adjudicator at all?

An accuracy figure means nothing without the floor it is standing on. This
script computes the two cheapest baselines available on this corpus and prints
them next to the adjudicator's own committed numbers, so the comparison is
made from artefacts rather than asserted in prose.

  CAUSAL   a flag-reader: map one E3 boolean to one causal category, fall back
           to AGENT_ERROR. No mandate comparison, no ladder, no rules.
  SCOPE    a constant: always predict OUT_OF_SCOPE. Reads nothing at all.

Everything is recomputed from committed artefacts — data/scenario_specs/ for
ground truth and results/adjudication_*.jsonl for the adjudicator. No figure
is hardcoded, including the adjudicator's own.

WHAT A HIGH BASELINE MEANS HERE. It is a statement about the corpus, not about
rule engines. The E3 flags were authored in the same pass as the labels they
sit beside, so they encode the answer nearly perfectly. That is the same defect
as the degenerate flip metric, one level up: a metric with no variance cannot
discriminate. Read these numbers as the floor any method must clear on THIS
corpus before its own score carries information.

    python baselines.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_all_scenario_ids, get_ground_truth, get_scenario, reset_cache

_ROOT = Path(__file__).resolve().parent
E3_PATH = _ROOT / "data" / "evidence" / "E3.jsonl"
V2_PATH = _ROOT / "results" / "adjudication_holdout-informed-bugfix-0.2.0.jsonl"

# One flag -> one category. Verified mutually exclusive on this corpus (see
# check below), so no precedence rule is needed and none is smuggled in.
FLAG_TO_CAUSE = [
    ("catalog_injection_present", "MERCHANT_INDUCED"),
    ("cart_manipulated", "MERCHANT_INDUCED"),
    ("system_state_inconsistent", "SYSTEM_ERROR"),
    ("instruction_flagged_ambiguous", "AMBIGUOUS_INTENT"),
]
FALLBACK = "AGENT_ERROR"


def load_e3() -> dict[str, dict]:
    rows = {}
    for line in E3_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            rows[d["scenario_id"]] = d
    return rows


def flag_reader(agent_context: dict) -> str:
    """The entire 'model'. Four lookups and a constant."""
    for flag, cause in FLAG_TO_CAUSE:
        if agent_context.get(flag):
            return cause
    return FALLBACK


def pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n / d:>6.1%}" if d else f"{n}/{d} =    n/a"


def main() -> None:
    reset_cache()
    e3 = load_e3()

    splits: dict[str, list[str]] = {"holdout": [], "dev": []}
    for sid in get_all_scenario_ids():
        splits[get_scenario(sid).split].append(sid)
    for v in splits.values():
        v.sort()

    # ---- sanity: the flags must be mutually exclusive, or the mapping above
    # ---- silently encodes a precedence decision that was never argued.
    overlaps = []
    for sid, row in e3.items():
        ctx = row.get("agent_context", {})
        on = [f for f, _ in FLAG_TO_CAUSE if ctx.get(f)]
        if len(on) > 1:
            overlaps.append((sid, on))

    print("=" * 78)
    print("TRIVIAL BASELINES — computed from committed artefacts")
    print("=" * 78)
    print(f"  ground truth : data/scenario_specs/ (via the oracle)")
    print(f"  E3 flags     : {E3_PATH.relative_to(_ROOT)}")
    print(f"  adjudicator  : {V2_PATH.relative_to(_ROOT)}")
    print()
    print(f"  flag mutual-exclusivity check: "
          f"{'FAILED — ' + str(overlaps) if overlaps else 'PASS (no scenario sets >1 flag)'}")
    print()

    # ---------------------------------------------------------- flag coverage
    amb = sorted(s for s, r in e3.items()
                 if r.get("agent_context", {}).get("instruction_flagged_ambiguous"))
    print(f"  instruction_flagged_ambiguous is True on {len(amb)}/{len(e3)}: {amb}")
    print(f"    ...and False on the other {len(e3) - len(amb)}")
    print()

    # -------------------------------------------------------------- baselines
    adj = {}
    for line in V2_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            adj[d["scenario_id"]] = d

    print("=" * 78)
    print(f"{'':<22} | {'CAUSAL':<20} | {'SCOPE':<20}")
    print("-" * 78)

    results = {}
    for split in ("holdout", "dev"):
        ids = splits[split]
        n = len(ids)

        flag_c = sum(
            flag_reader(e3[s].get("agent_context", {}))
            == get_ground_truth(s).causal_category.value
            for s in ids
        )
        const_s = sum(get_ground_truth(s).scope_violation for s in ids)

        adj_c = sum(
            adj[s]["E3"]["causal_category"] == get_ground_truth(s).causal_category.value
            for s in ids
        )
        adj_s = 0
        for s in ids:
            f = adj[s]["E3"]["scope_finding"]
            if f != "UNDETERMINED" and (f == "OUT_OF_SCOPE") == get_ground_truth(s).scope_violation:
                adj_s += 1

        results[split] = {
            "n": n,
            "baseline_causal": flag_c, "baseline_scope": const_s,
            "adjudicator_causal": adj_c, "adjudicator_scope": adj_s,
        }

        print(f"{split.upper() + f' (n={n})':<22} |")
        print(f"{'  flag-reader / always-OOS':<22} | {pct(flag_c, n):<20} | {pct(const_s, n):<20}")
        print(f"{'  adjudicator v0.2.0':<22} | {pct(adj_c, n):<20} | {pct(adj_s, n):<20}")
        print(f"{'  margin':<22} | {adj_c - flag_c:+d}{'':<17} | {adj_s - const_s:+d}")
        print("-" * 78)

    print()
    print("Reading: a positive margin is the adjudicator beating the trivial floor.")
    print("A negative margin means the rules are worse than reading one boolean,")
    print("which is a finding about the corpus's flags, not a defence of the rules.")

    return results


if __name__ == "__main__":
    main()
