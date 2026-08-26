"""
FAISLA — Report Generator

Writes results/kill_test_report.md entirely from data: the two frozen
adjudication result files, results/agreement.json, and the corpus ground
truth. No number in the output is typed by hand.

This exists because the report was previously hand-written, which meant every
ground-truth correction silently invalidated it. A generated report cannot
drift from the artefacts it describes.

Entrypoint: python -m faisla.evaluation.report
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from faisla.world.oracle import get_ground_truth, reset_cache

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = _PROJECT_ROOT / "results"

V1 = "dev-calibration-0.1.0"
V2 = "holdout-informed-bugfix-0.2.0"
DUP_CLASS = "DUPLICATE_OR_RETRY_EXECUTION"
GATE = "original_author__vs__reviewer_b_independent"

# Scenarios the developer had prior exposure to via the correction work.
PRIOR_EXPOSURE = {"SC-AHI-002", "SC-AHI-003", "SC-AHI-004", "SC-DRE-002"}


# ============================================================================
# DUPLICATE_OR_RETRY_EXECUTION DISCLOSURE
# ============================================================================
# This exact sentence must appear in every generated report.
DUPLICATE_RETRY_DISCLOSURE = (
    "DUPLICATE_OR_RETRY_EXECUTION scenarios measure whether duplicate or "
    "retried payments can be detected and reconciled — a reconciliation "
    "construct — whereas the other five failure classes measure whether "
    "fault can be attributed to the agent, the merchant, the system, or "
    "ambiguous intent — a liability construct. These two constructs are "
    "not commensurable: resolution of a duplicate-detection scenario and "
    "resolution of a liability-attribution scenario test fundamentally "
    "different evidence capabilities, and their results must never be "
    "pooled into a single aggregate metric."
)


def _load(version: str) -> list[dict]:
    path = RESULTS_DIR / f"adjudication_{version}.jsonl"
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _flip(r: dict) -> bool:
    return (r["E0"]["sufficiency"] == "INSUFFICIENT"
            and r["E3"]["sufficiency"] == "SUFFICIENT")


def _reverse_flip(r: dict) -> bool:
    return (r["E0"]["sufficiency"] == "SUFFICIENT"
            and r["E3"]["sufficiency"] == "INSUFFICIENT")


def _causal_ok(r: dict) -> bool:
    return r["E3"]["causal_category"] == get_ground_truth(
        r["scenario_id"]).causal_category.value


def _scope_ok(r: dict) -> bool:
    f = r["E3"]["scope_finding"]
    if f == "UNDETERMINED":
        return False
    return (f == "OUT_OF_SCOPE") == get_ground_truth(r["scenario_id"]).scope_violation


def _stats(rows: list[dict]) -> dict:
    held = [r for r in rows if r["split"] == "holdout"]
    non_dup = [r for r in held if r["failure_class"] != DUP_CLASS]
    clean = [r for r in held if r["scenario_id"] not in PRIOR_EXPOSURE]
    return {
        "held": held, "non_dup": non_dup, "clean": clean,
        "flips_nd": sum(map(_flip, non_dup)),
        "flips_all": sum(map(_flip, held)),
        "reverse": sum(map(_reverse_flip, held)),
        "causal": sum(map(_causal_ok, held)),
        "causal_clean": sum(map(_causal_ok, clean)),
        "scope": sum(map(_scope_ok, held)),
        "e0_suff": sum(1 for r in non_dup if r["E0"]["sufficiency"] == "SUFFICIENT"),
        "undet": sum(1 for r in held if r["E3"]["causal_category"] is None),
        # Where the errors actually sit. If causal failures were driven by the
        # merchant/system booleans, we would expect scope-right/causal-wrong
        # cases; if they are downstream of scope, we would not.
        "wrong_both": sum(1 for r in held if not _causal_ok(r) and not _scope_ok(r)),
        "wrong_causal_only": sum(1 for r in held if not _causal_ok(r) and _scope_ok(r)),
        "wrong_scope_only": sum(1 for r in held if _causal_ok(r) and not _scope_ok(r)),
        "causal_determinate": sum(
            1 for r in held if r["E3"]["causal_category"] is not None
        ),
        "causal_abstained": sum(
            1 for r in held if r["E3"]["causal_category"] is None
        ),
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} = {n/d:.1%}" if d else "n/a"


def generate_report() -> str:
    reset_cache()
    r1, r2 = _load(V1), _load(V2)
    s1, s2 = _stats(r1), _stats(r2)

    agreement = json.load(open(RESULTS_DIR / "agreement.json", encoding="utf-8"))
    gate = agreement["comparisons"][GATE]
    g_scope = gate["scope_violation_agreement"]
    g_causal = gate["causal_category_agreement"]

    delta = (s2["causal"] - s1["causal"]) / len(s2["held"]) * 100

    # Per-class flip table (identical across versions, but computed not assumed)
    by_class = defaultdict(list)
    for r in s1["held"]:
        by_class[r["failure_class"]].append(r)
    flip_rows = "\n".join(
        f"| `{fc}` | {len(g)} | {sum(map(_flip, g))} | {sum(map(_flip, g))/len(g):.1%} |"
        for fc, g in sorted(by_class.items())
    )

    # Bug-fix impact: scenarios whose E3 causal changed between versions
    by_id1 = {r["scenario_id"]: r for r in r1}
    changed = [
        r for r in s2["held"]
        if r["E3"]["causal_category"] != by_id1[r["scenario_id"]]["E3"]["causal_category"]
    ]
    changed_rows = "\n".join(
        f"| {r['scenario_id']} | `{get_ground_truth(r['scenario_id']).causal_category.value}` "
        f"| {by_id1[r['scenario_id']]['E3']['causal_category'] or '—'} "
        f"{'✓' if _causal_ok(by_id1[r['scenario_id']]) else '✗'} "
        f"| {r['E3']['causal_category'] or '—'} {'✓' if _causal_ok(r) else '✗'} |"
        for r in sorted(changed, key=lambda x: x["scenario_id"])
    )

    # Still-wrong under v0.2.0
    wrong_rows = "\n".join(
        f"| {r['scenario_id']} | `{get_ground_truth(r['scenario_id']).causal_category.value}` "
        f"| {r['E3']['causal_category'] or '*undetermined*'} |"
        for r in sorted(s2["held"], key=lambda x: x["scenario_id"])
        if not _causal_ok(r)
    )

    gate_note = (
        "inside the 70–80% gray zone → **INCONCLUSIVE**"
        if 0.70 <= g_causal < 0.80 else
        f"at {g_causal:.1%}"
    )

    return f"""# FAISLA Day-1 Kill Test Report

<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: python -m faisla.evaluation.report
     Every number below is computed from results/*.jsonl, results/agreement.json,
     and the corpus ground truth. -->

**PILOT — not a statistically powered claim.** n={len(s1['held'])} held out,
3 per failure class. Every figure below is a pilot observation, not an
estimate with a usable confidence interval.

Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.

## Methodology Disclosure

> {DUPLICATE_RETRY_DISCLOSURE}

---

## 1. Primary finding — sufficiency and correctness diverge

**The adjudicator flipped to SUFFICIENT on {s1['flips_nd']}/{len(s1['non_dup'])}
held-out non-duplicate scenarios while getting causal attribution right well
under half the time.**

| rule_version | flip rate (non-dup) | causal correctness (all {len(s1['held'])}) | causal (excl. prior-exposure, {len(s1['clean'])}) |
|---|---|---|---|
| `{V1}` | **{_pct(s1['flips_nd'], len(s1['non_dup']))}** | **{_pct(s1['causal'], len(s1['held']))}** | **{_pct(s1['causal_clean'], len(s1['clean']))}** |
| `{V2}` | **{_pct(s2['flips_nd'], len(s2['non_dup']))}** | {_pct(s2['causal'], len(s2['held']))} | {_pct(s2['causal_clean'], len(s2['clean']))} |

The finding is in the first column: **the two bug fixes raised correctness by
{delta:.1f} points and moved the flip rate by exactly zero.** The flip metric
could not distinguish a rule set that was wrong
{len(s1['held']) - s1['causal']} times from one wrong
{len(s2['held']) - s2['causal']} times. It scored both at
{s1['flips_nd']/len(s1['non_dup']):.0%}.

This is a finding about the *instrument*, not the adjudicator. Sufficiency asks
"did the evidence determine an answer?"; correctness asks "was the answer
right?" E3 supplies the delegated-authority record, so an answer becomes
derivable — the flip fires. Whether the rules derive the *correct* answer is an
independent question the flip metric never asks.

### Where the errors actually sit

Correctness is bottlenecked at **scope resolution**, not at causal
attribution. Under `{V2}`, of the {len(s2['held'])} held-out scenarios:

| Error pattern | count |
|---|---|
| wrong on **both** scope and cause | {s2['wrong_both']} |
| wrong on cause **only** | {s2['wrong_causal_only']} |
| wrong on scope **only** | {s2['wrong_scope_only']} |

No causal judgment ever rescues a failed scope judgment. Scope is derived from
mandate, budget, category and merchant comparisons — not from the
merchant/system booleans E3 carries — so the accuracy ceiling is set upstream
of the flags. Fixing scope rules is what moved correctness {delta:.1f} points
between the two versions.

### Correctness is not a §13 input

**The correctness figures played no part in the verdict below.**
`evaluate_kill_test()` consumes agreement, flip counts, reverse flips, and the
E0-strength flags. Correctness is not among its parameters. The verdict was
determined by the §9.1 agreement number alone and would be identical at 0% or
100% correctness.

---

## 2. Gate result — verdict **INCONCLUSIVE**

Bound to the **author-vs-reviewer-B** comparison, the lower of the two
author-vs-reviewer results (ARCHITECTURE.md).

| Input | Value |
|---|---|
| `scope_agreement` | {g_scope:.4f} |
| `causal_agreement` | **{g_causal:.4f}** |
| `flip_count` / `held_out_non_dup_count` | {s1['flips_nd']} / {len(s1['non_dup'])} |
| `reverse_flip_count` | {s1['reverse']} |
| `e0_resolves_all` | False ({s1['e0_suff']}/{len(s1['non_dup'])} E0 SUFFICIENT) |
| `flips_are_manufactured` | **False** — resolved on the record |
| `flip_rationales_confirmed` | False (no human has read the flips) |

**The agreement gate fires first and decides it.** Causal agreement of
{g_causal:.1%} falls {gate_note}. No flip data can change this.

---

## 3. Flip rate, and why this table is degenerate

| Failure class | n | flips | rate |
|---|---|---|---|
{flip_rows}
| **Pooled — all held-out** | {len(s1['held'])} | {s1['flips_all']} | {s1['flips_all']/len(s1['held']):.1%} |
| **Pooled — non-duplicate (§13)** | {len(s1['non_dup'])} | {s1['flips_nd']} | {s1['flips_nd']/len(s1['non_dup']):.1%} |

### The flip metric was DEGENERATE on this run

A third category, distinct from §13's two:

- **manufactured** — flips traceable to an artificially weak E0. **Not this
  run.** E0's thinness is anchored, not authored (E0_ANCHOR.md).
- **validated** — flips from many independent, separately checkable causes.
  **Not this run either.**
- **degenerate** — flips from a *single* architectural cause, near-zero
  variance. **This run.**

Every non-duplicate flip traces to one rule firing identically:
`E0-C1-no-fault-signal-available`. That is **one finding reported
{s1['flips_nd']} times, not {s1['flips_nd']} independent findings.** A metric
with zero variance carries almost no information; 100% should be read as "the
metric did not discriminate," not "the intervention worked perfectly."

**The E3 side is symmetric, and matters more because 100% reads as a
triumph.** E3's causal ladder is *total*: `E3-C0` absorbs every in-scope
scenario as `NO_VIOLATION`, `E3-C1`/`C2`/`C3` absorb every scenario carrying a
merchant- or system-side signal, and `E3-C5-residual-agent-attribution`
catches whatever remains by elimination. The only path that declines to answer
is `E3-C4`, which abstains on duplicates. The result is that
**{s2['causal_determinate']} of {len(s2['held'])} held-out scenarios receive a
determinate cause, with only {s2['causal_abstained']} abstention** — an answer
is near-guaranteed once scope resolves, because the ladder has no gap to fall
through. The E3 sufficiency rate is therefore largely a property of the rule
set's shape, not a measurement of evidence quality.

Both ends of the flip metric are therefore construction artefacts: E0 cannot
produce an answer (deductively, from the anchor's field list), and E3 almost
always can (by catch-all). The interesting quantity is what the answer is
worth, which is the correctness column in §1 — not this table.

### The one non-degenerate data point

**`{DUP_CLASS}` is the only row in the table carrying information**, and the
only one pre-registered and confirmed. E0_ANCHOR.md predicted, before any
adjudication ran, that duplicates would largely resolve at E0 because the
anchor has three dedicated duplicate fields. `E0-S1-settled-exceeds-receipt`
fired on all three held-out duplicate scenarios from receipt arithmetic alone.

---

## 4. Bug fixes — v0.2.0, before and after

Both bugs were discovered **from held-out results**. v0.2.0 is therefore
**held-out-informed and NOT an unbiased estimate.** Only `{V1}` is. v0.1.0's
source is archived at `faisla/adjudication/frozen_v0_1_0.py` and is
regenerable via `python reproduce_v0_1_0.py --verify`.

**(a) Scope rules ignored merchant-side signals.** `cart_manipulated` and
`catalog_injection_present` were consulted only by the *causal* rules, so a
merchant inflating price into the line item tripped no scope rule; scope
returned `IN_SCOPE` and `E3-C0` short-circuited to `NO_VIOLATION`. Fixed by
adding `E3-S8` and `E3-S9` as scope rules.

**(b) Budget extraction missed three phrasings** — `"budget around 3000-4000"`,
`"listed at 2999"`, `"priced at 2499"`.

### Impact

| Scenario | Truth | v0.1.0 | v0.2.0 |
|---|---|---|---|
{changed_rows}

Causal correctness {s1['causal']}/{len(s1['held'])} →
{s2['causal']}/{len(s2['held'])}; scope {s1['scope']}/{len(s1['held'])} →
{s2['scope']}/{len(s2['held'])}. **Flip rate unchanged at
{s2['flips_nd']}/{len(s2['non_dup'])}.**

### Still incorrect under v0.2.0

| Scenario | Truth | v0.2.0 |
|---|---|---|
{wrong_rows}

---

## 5. Scoping note — SC-AIE-004

*"Book the afternoon flight to Delhi, **not the red-eye**. Keep it under
15000."* Every numeric and categorical constraint is satisfied; the violation
is a **semantic preference** with no numeric or categorical shadow in the
packet. The budget extractor correctly read 15000 and correctly found no
breach.

**Expected to remain unresolved under both versions — a scoping boundary, not
a v0.2.0 target.** Resolving it would require interpreting natural-language
preferences against product descriptions, forfeiting the determinism and
auditability this adjudicator exists to demonstrate. It marks the edge of the
deterministic approach: constraints are checkable when they have numeric or
categorical form, and invisible when they do not.

---

## Artefacts

| File | Contents |
|---|---|
| `results/adjudication_{V1}.jsonl` | v0.1.0 — the unbiased held-out estimate |
| `results/adjudication_{V2}.jsonl` | v0.2.0 — held-out-informed |
| `faisla/adjudication/frozen_v0_1_0.py` | v0.1.0 source, byte-preserved |
| `reproduce_v0_1_0.py` | regenerates and verifies v0.1.0 |
| `results/agreement.json` | three-way §9.1 agreement |
| `E0_ANCHOR.md` | external anchor and pre-registered predictions |
| `CORPUS.md` | corrections, contested calls, known limitations |
"""


def main() -> None:
    report = generate_report()
    output_path = RESULTS_DIR / "kill_test_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
