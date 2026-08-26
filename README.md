# FAISLA

**F**ault **A**ttribution **I**n **S**ystems of **L**LM **A**gency — a pilot benchmark for
whether AI-mediated payment disputes can be adjudicated from evidence.

---

Conventional payment-dispute evidence resolves **0% (0/15)** of held-out
non-duplicate agent-payment disputes; agent-aware evidence resolves **100%
(15/15)**. Read carefully, **neither of those numbers is the finding** — both
follow largely from how the two conditions are constructed. The finding is
what happens to *correctness*: of the disputes it resolves, the adjudicator
attributes fault correctly only **38.9%** of the time under the frozen rule
set, rising to **61.1%** after two disclosed bug fixes. **Evidence sufficiency
and evidence correctness are different measurements, and an instrument
reporting only the first would score this run a complete success.**

![Sufficiency and correctness diverge](results/divergence.png)

The two bug fixes moved causal correctness by 22.2 points and moved the flip
rate by exactly zero. A benchmark scoring sufficiency alone could not tell the
two rule sets apart.

### Why the 0% and the 100% are not the finding

**The 0% is deductive, not experimental.** It follows from the anchor's field
list: the card-network dispute record enumerated in
[E0_ANCHOR.md](E0_ANCHOR.md) contains no field expressing delegated authority,
so no fault-attribution signal exists to read. The adjudicator encodes this
directly — `_causal_e0()` returns "undetermined" unconditionally. Given the
anchor, 0% is a **structural fact about the conventional schema**, established
by reading the spec, not discovered by running an experiment. The experiment
confirms the implementation matches the anchor; it does not independently
establish the claim.

**The 100% is close to guaranteed by construction.** E3's causal ladder is
*total* — every in-scope scenario is absorbed as `NO_VIOLATION`, every scenario
carrying a merchant- or system-side signal is absorbed by the rule matching it,
and a residual catch-all takes whatever remains by elimination. Only the
duplicate rule declines to answer. **17 of 18 held-out scenarios receive a
determinate cause, with 1 abstention.** A 100% flip rate therefore measures
"an answer became derivable", not "the evidence was good". The kill-test report classifies this run's flip metric as
[**degenerate**](results/kill_test_report.md) for exactly this reason: every
non-duplicate flip traces to a single rule firing identically, with near-zero
variance.

**Correctness is the number that carries information, and it is not
flag-derived.** E3 does contain merchant- and system-side booleans, and where
one is set it is strongly predictive (a naive flag-reader scores 10/11 on
held-out scenarios with a flag). But those flags are set in only **11 of 18**
held-out scenarios, and they are not what limits accuracy. Errors are
bottlenecked upstream, at scope resolution — which is derived from mandate,
budget, category and merchant comparisons, not from any flag. Under v0.2.0,
**6 held-out scenarios are wrong on both scope and cause, 1 on cause alone,
and 0 on scope alone**: no causal judgment ever rescues a failed scope
judgment, and fixing scope is what moved correctness 22 points. That is the
result worth attention.

---

## Start here

| | |
|---|---|
| **[Exhibit — SC-MPI-001](https://puni344.github.io/razor-pay/faisla_demo.html)** | The single clearest case, with an animated evidence reveal. A merchant embeds a fake `"SYSTEM INSTRUCTION"` in its catalog, the agent obeys, and 2499 is spent against an "under 500 rupees" instruction. At E0 the charge looks unremarkable and the injection is invisible; at E3 it is right there in the tool-call log. |
| **[Interactive console](https://puni344.github.io/razor-pay/faisla_console.html?scenario=SC-MPI-003)** | All 24 scenarios browsable: the E0 and E3 packets a reviewer would actually see, both rule versions' verdicts, and the hidden ground truth on toggle. Opens on SC-MPI-003 — switch the version toggle from v0.1.0 to v0.2.0 and watch `NO_VIOLATION` become `MERCHANT_INDUCED`. |
| **[Kill-test report](results/kill_test_report.md)** | The full Day-1 result: verdict **INCONCLUSIVE**, why the flip metric was degenerate on this run, both bug fixes with before/after impact, and the scenarios still wrong. |

---

## What broke

Real incidents from this build, all documented in
[CORPUS.md](CORPUS.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

- **Two ground-truth labels contradicted themselves, and a validator caught it
  independently.** SC-AHI-001 and SC-AHI-003 were labelled `AMBIGUOUS_INTENT`
  while also recording `scope_violation: false` — assigning fault for a
  violation that the same record said never happened. SC-AHI-003's rationale
  stated *"No mandate was violated"* and then assigned fault in the next
  sentence. A schema invariant written separately (`scope_violation` false ⟹
  `causal_category` must be `NO_VIOLATION`) rejected **exactly those two
  specs** when first switched on, reproducing the independent reviewer's
  finding from the data alone.

- **The agreement calculation silently discarded half the review data.**
  `compute_agreement()` indexed reviewer rows by `scenario_id` alone. Handed a
  48-row two-reviewer file it kept whichever reviewer's rows landed last and
  reported a clean, plausible, **wrong** 24-scenario result — no error, no
  warning. The failure mode was a confident number, which is worse than a
  crash. It now raises unless told which reviewer to score.

- **The leakage controls hid a fact the reviewers needed.** SC-AHI-004 turns
  on a Standard tier sitting between the Basic the user had and the Premium
  the agent bought. That fact lives only in `ambiguity_detail` — correctly
  redacted from the reviewer's view, because it telegraphs the answer. The
  strings "Standard" and "1000" appear **zero times** in what reviewers saw.
  The redaction was right; the corpus design was wrong.

- **A correction with 2-of-2 reviewer agreement was rejected.** Both
  reviewers independently called SC-AHI-004 `NO_VIOLATION` against the
  author's `AMBIGUOUS_INTENT`. Neither did so on the merits: one wrote that
  the facts *"can't be confirmed either way"*, the other asserted the agent
  *"upgraded to the next tier"*, which is factually false. Two reviewers
  converging while neither holds the deciding fact is agreement, not
  evidence. The label stands unchanged.

---

## Reproduce

Verify rather than trust. From a clean checkout:

```bash
pip install -r requirements.txt

python validate_scenarios.py                      # 24 specs pass schema + invariants
python render_evidence.py                         # E0/E3 packets -> data/evidence/
python compute_agreement.py                       # 3-way reviewer agreement
# exits 1 on a fresh clone by design - results already exist, see note below
python run_holdout.py                             # frozen adjudication run
python score_holdout.py                           # flip rate + correctness
python -m faisla.evaluation.plot_divergence       # results/divergence.png
python -m faisla.evaluation.console_export        # results/console_export.json
python -m pytest tests/ -q                        # 97 tests
```

`run_holdout.py` **refuses to overwrite** an existing results file for a given
`rule_version`. That is deliberate: the held-out run is a single frozen
evaluation, and re-running it against edited rules is the one thing that would
invalidate the result. To re-run, bump `RULE_VERSION`.

### Verifying v0.1.0 specifically

`run_holdout.py` runs whichever adjudicator is *live*, which is now v0.2.0. To
regenerate the pilot's one unbiased estimate, run the archived v0.1.0 rules
directly:

```bash
python reproduce_v0_1_0.py --verify   # regenerate in memory, diff vs committed
python reproduce_v0_1_0.py            # regenerate the file itself
```

`--verify` writes nothing and exits 0 only if the regenerated bytes match
`results/adjudication_dev-calibration-0.1.0.jsonl` exactly. It aborts if
`frozen_v0_1_0.py` has been modified. Pinned by
[tests/test_v0_1_0_reproducible.py](tests/test_v0_1_0_reproducible.py).

Both rule versions are preserved and independently reproducible —
`dev-calibration-0.1.0` (calibrated on the 6 dev scenarios, frozen before the
held-out run, the pilot's one unbiased estimate) and
`holdout-informed-bugfix-0.2.0` (two fixes found *from* held-out results, and
therefore **not** an unbiased estimate). v0.1.0's source is archived verbatim
at [`faisla/adjudication/frozen_v0_1_0.py`](faisla/adjudication/frozen_v0_1_0.py).

**Pilot, not a powered claim:** 24 scenarios, 6 dev / 18 held out, 3 per
failure class. Every figure above is a pilot observation.
