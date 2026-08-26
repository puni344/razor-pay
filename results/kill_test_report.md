# FAISLA Day-1 Kill Test Report

<!-- GENERATED FILE — do not edit by hand.
     Regenerate with: python -m faisla.evaluation.report
     Every number below is computed from results/*.jsonl, results/agreement.json,
     and the corpus ground truth. -->

**PILOT — not a statistically powered claim.** n=18 held out,
3 per failure class. Every figure below is a pilot observation, not an
estimate with a usable confidence interval.

Generated 2026-08-26.

## Methodology Disclosure

> DUPLICATE_OR_RETRY_EXECUTION scenarios measure whether duplicate or retried payments can be detected and reconciled — a reconciliation construct — whereas the other five failure classes measure whether fault can be attributed to the agent, the merchant, the system, or ambiguous intent — a liability construct. These two constructs are not commensurable: resolution of a duplicate-detection scenario and resolution of a liability-attribution scenario test fundamentally different evidence capabilities, and their results must never be pooled into a single aggregate metric.

---

## 1. Primary finding — sufficiency and correctness diverge

**The adjudicator flipped to SUFFICIENT on 15/15
held-out non-duplicate scenarios while getting causal attribution right well
under half the time.**

| rule_version | flip rate (non-dup) | causal correctness (all 18) | causal (excl. prior-exposure, 14) |
|---|---|---|---|
| `dev-calibration-0.1.0` | **15/15 = 100.0%** | **7/18 = 38.9%** | **7/14 = 50.0%** |
| `holdout-informed-bugfix-0.2.0` | **15/15 = 100.0%** | 11/18 = 61.1% | 11/14 = 78.6% |

The finding is in the first column: **the two bug fixes raised correctness by
22.2 points and moved the flip rate by exactly zero.** The flip metric
could not distinguish a rule set that was wrong
11 times from one wrong
7 times. It scored both at
100%.

This is a finding about the *instrument*, not the adjudicator. Sufficiency asks
"did the evidence determine an answer?"; correctness asks "was the answer
right?" E3 supplies the delegated-authority record, so an answer becomes
derivable — the flip fires. Whether the rules derive the *correct* answer is an
independent question the flip metric never asks.

### Where the errors actually sit

Correctness is bottlenecked at **scope resolution**, not at causal
attribution. Under `holdout-informed-bugfix-0.2.0`, of the 18 held-out scenarios:

| Error pattern | count |
|---|---|
| wrong on **both** scope and cause | 6 |
| wrong on cause **only** | 1 |
| wrong on scope **only** | 0 |

No causal judgment ever rescues a failed scope judgment. Scope is derived from
mandate, budget, category and merchant comparisons — not from the
merchant/system booleans E3 carries — so the accuracy ceiling is set upstream
of the flags. Fixing scope rules is what moved correctness 22.2 points
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
| `scope_agreement` | 0.9167 |
| `causal_agreement` | **0.7917** |
| `flip_count` / `held_out_non_dup_count` | 15 / 15 |
| `reverse_flip_count` | 0 |
| `e0_resolves_all` | False (0/15 E0 SUFFICIENT) |
| `flips_are_manufactured` | **False** — resolved on the record |
| `flip_rationales_confirmed` | False (no human has read the flips) |

**The agreement gate fires first and decides it.** Causal agreement of
79.2% falls inside the 70–80% gray zone → **INCONCLUSIVE**. No flip data can change this.

---

## 3. Flip rate, and why this table is degenerate

| Failure class | n | flips | rate |
|---|---|---|---|
| `AGENT_INTERPRETATION_ERROR` | 3 | 3 | 100.0% |
| `AMBIGUOUS_HUMAN_INSTRUCTION` | 3 | 3 | 100.0% |
| `DUPLICATE_OR_RETRY_EXECUTION` | 3 | 2 | 66.7% |
| `MERCHANT_OR_CART_MANIPULATION` | 3 | 3 | 100.0% |
| `MERCHANT_PROMPT_OR_CATALOG_INJECTION` | 3 | 3 | 100.0% |
| `SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY` | 3 | 3 | 100.0% |
| **Pooled — all held-out** | 18 | 17 | 94.4% |
| **Pooled — non-duplicate (§13)** | 15 | 15 | 100.0% |

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
15 times, not 15 independent findings.** A metric
with zero variance carries almost no information; 100% should be read as "the
metric did not discriminate," not "the intervention worked perfectly."

**The E3 side is symmetric, and matters more because 100% reads as a
triumph.** E3's causal ladder is *total*: `E3-C0` absorbs every in-scope
scenario as `NO_VIOLATION`, `E3-C1`/`C2`/`C3` absorb every scenario carrying a
merchant- or system-side signal, and `E3-C5-residual-agent-attribution`
catches whatever remains by elimination. The only path that declines to answer
is `E3-C4`, which abstains on duplicates. The result is that
**17 of 18 held-out scenarios receive a
determinate cause, with only 1 abstention** — an answer
is near-guaranteed once scope resolves, because the ladder has no gap to fall
through. The E3 sufficiency rate is therefore largely a property of the rule
set's shape, not a measurement of evidence quality.

Both ends of the flip metric are therefore construction artefacts: E0 cannot
produce an answer (deductively, from the anchor's field list), and E3 almost
always can (by catch-all). The interesting quantity is what the answer is
worth, which is the correctness column in §1 — not this table.

### The one non-degenerate data point

**`DUPLICATE_OR_RETRY_EXECUTION` is the only row in the table carrying information**, and the
only one pre-registered and confirmed. E0_ANCHOR.md predicted, before any
adjudication ran, that duplicates would largely resolve at E0 because the
anchor has three dedicated duplicate fields. `E0-S1-settled-exceeds-receipt`
fired on all three held-out duplicate scenarios from receipt arithmetic alone.

---

## 4. Bug fixes — v0.2.0, before and after

Both bugs were discovered **from held-out results**. v0.2.0 is therefore
**held-out-informed and NOT an unbiased estimate.** Only `dev-calibration-0.1.0` is. v0.1.0's
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
| SC-MCM-002 | `MERCHANT_INDUCED` | NO_VIOLATION ✗ | MERCHANT_INDUCED ✓ |
| SC-MCM-004 | `MERCHANT_INDUCED` | NO_VIOLATION ✗ | MERCHANT_INDUCED ✓ |
| SC-MPI-003 | `MERCHANT_INDUCED` | NO_VIOLATION ✗ | MERCHANT_INDUCED ✓ |
| SC-MPI-004 | `MERCHANT_INDUCED` | NO_VIOLATION ✗ | MERCHANT_INDUCED ✓ |

Causal correctness 7/18 →
11/18; scope 8/18 →
12/18. **Flip rate unchanged at
15/15.**

### Still incorrect under v0.2.0

| Scenario | Truth | v0.2.0 |
|---|---|---|
| SC-AHI-002 | `AMBIGUOUS_INTENT` | NO_VIOLATION |
| SC-AHI-003 | `AMBIGUOUS_INTENT` | NO_VIOLATION |
| SC-AHI-004 | `AMBIGUOUS_INTENT` | NO_VIOLATION |
| SC-AIE-003 | `AGENT_ERROR` | NO_VIOLATION |
| SC-AIE-004 | `AGENT_ERROR` | NO_VIOLATION |
| SC-DRE-002 | `AGENT_ERROR` | *undetermined* |
| SC-SSI-004 | `NO_VIOLATION` | SYSTEM_ERROR |

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
| `results/adjudication_dev-calibration-0.1.0.jsonl` | v0.1.0 — the unbiased held-out estimate |
| `results/adjudication_holdout-informed-bugfix-0.2.0.jsonl` | v0.2.0 — held-out-informed |
| `faisla/adjudication/frozen_v0_1_0.py` | v0.1.0 source, byte-preserved |
| `reproduce_v0_1_0.py` | regenerates and verifies v0.1.0 |
| `results/agreement.json` | three-way §9.1 agreement |
| `E0_ANCHOR.md` | external anchor and pre-registered predictions |
| `CORPUS.md` | corrections, contested calls, known limitations |
