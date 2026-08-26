# FAISLA — Architecture

FAISLA evaluates whether an adjudicator can correctly attribute fault in
AI-mediated payment incidents, using a hand-authored corpus of scenarios whose
true cause is known but hidden from everything downstream of the oracle.

The whole design exists to answer one question honestly: **does more evidence
actually help the adjudicator, or does the benchmark just leak the answer?**
Every constraint below is in service of not leaking.

---

## Layers and the one-directional data flow

```
data/scenario_specs/*.yaml     hand-authored latent facts + ground truth
          │
          ▼
   faisla/world/               generator.py  → load & validate specs
                               models.py     → ScenarioWorld, GroundTruth
                               oracle.py     → the ONLY read path
          │
          ├──────────────► get_ground_truth()  ──► faisla/evaluation/  (scoring only)
          │
          └──────────────► get_review_facts()  ──► §9.1 second-labeler review
                                                    (data/labels/)

   faisla/evidence/      builds EvidencePackets — NO import path to the oracle
   faisla/adjudication/  consumes EvidencePackets — NO import path to the oracle
```

`faisla/world/oracle.py` exposes exactly two read functions. Neither may be
imported anywhere under `adjudication/` or `evidence/`; this is enforced by
[tests/test_no_leakage.py](tests/test_no_leakage.py), which is deliberately
written before the adjudicator exists so the adjudicator cannot be built
against a leaky packet.

### Structural absence, not filtering

`ScenarioFactsForReview` does not carry `ground_truth`, `ambiguity_detail`, or
`corrections`. These are absent **at the type level** — the model names each
included field explicitly rather than serializing `ScenarioWorld` and stripping
fields afterwards. A field that does not exist on the type cannot be forgotten
in a filter.

`corrections` is excluded for the same reason as `ambiguity_detail`, and more
sharply: a correction record quotes both the superseded verdict and the
reviewer reasoning that replaced it, so it would hand the reviewer the answer
twice over.

---

## Ground-truth invariants

`GroundTruth` has two label fields, and they are not independent.

- `scope_violation: bool` — did the agent exceed the user's delegated authority?
- `causal_category: CausalCategory` — **who is at fault for the violation?**

### The NO_VIOLATION invariant (enforced)

> **If `ground_truth.scope_violation` is `False`, then
> `ground_truth.causal_category` MUST be `NO_VIOLATION`.**

`causal_category` attributes fault *for a violation*. Where there was no
violation, there is nothing to attribute, and any of the four attributing
values (`AGENT_ERROR`, `MERCHANT_INDUCED`, `AMBIGUOUS_INTENT`, `SYSTEM_ERROR`)
is a category error.

The failure mode this rule closes is specific and was observed in the corpus.
An author who has written a scenario where the agent stayed inside its mandate
but the user might still be unhappy — an underspecified gift instruction, a
"the usual" order with no order history — reaches for `AMBIGUOUS_INTENT` to
record *that the instruction was ambiguous*. But `causal_category` is not the
place that fact lives. Instruction ambiguity is already recorded twice:

- `ScenarioWorld.ambiguous_instruction` (and `ambiguity_detail`), and
- `failure_class = AMBIGUOUS_HUMAN_INSTRUCTION`.

Encoding it a third time in `causal_category` makes the field mean *"who is at
fault"* in some rows and *"what kind of scenario is this"* in others. A second
reviewer reading only the facts applies the first meaning, the author applied
the second, and the resulting disagreement is a measurement artefact of the
schema rather than a real disagreement about the incident. It conflates
**"this outcome may have disappointed the user"** with **"the agent exceeded
its authority"**, which is the single distinction the benchmark exists to
measure.

**Enforcement.** A `model_validator(mode="after")` on `ScenarioWorld`
([faisla/world/models.py](faisla/world/models.py)) raises on any spec that
breaks the rule. Because every load path — `load_scenario_spec`,
`load_all_scenario_specs`, `load_rendered_scenarios`, and therefore the oracle
itself — constructs `ScenarioWorld`, an offending spec cannot be loaded at all.
The rule is pinned by
[tests/test_ground_truth_invariants.py](tests/test_ground_truth_invariants.py),
which checks that the validator rejects each of the four attributing values,
accepts `NO_VIOLATION`, and that all 24 authored specs satisfy it.

### The converse is deliberately NOT enforced

`scope_violation = True` paired with `causal_category = NO_VIOLATION` is not
rejected. The corpus contains no such case, and the brief did not specify it as
an invariant; adding it would be the author inventing a rule after seeing the
data. If a future scenario needs that pairing, it should be argued on its
merits rather than blocked by a rule nobody agreed to.

---

## Correcting ground truth

Ground truth is never silently overwritten. Any post-authoring change to a
`GroundTruth` field appends a `GroundTruthCorrection` record to
`ScenarioWorld.corrections`, carrying:

| field | meaning |
|---|---|
| `date` | ISO-8601 date the correction was applied |
| `field` | dotted path, e.g. `ground_truth.causal_category` |
| `previous_value` | the superseded value, verbatim |
| `corrected_value` | the value now in force |
| `evidence_ref` | which independent-review record justified the change |
| `rationale` | why the reviewer's reading supersedes the author's |
| `approved_by` | who authorised the change |

The `rationale` in `GroundTruth` itself is rewritten at the same time, so the
verdict and its stated reasoning never contradict each other. The correction
log is provenance, not verdict: it lives on `ScenarioWorld`, not inside
`GroundTruth`, so it does not travel with the verdict into scoring.

Applied corrections and their justifications are listed in
[CORPUS.md](CORPUS.md).

---

## Second-labeler review (§9.1)

An independent reviewer sees `ScenarioFactsForReview` only — via
[data/labels/review_packet.md](data/labels/review_packet.md), whose body is
checked for leaked authorial labels by [check_packet.py](check_packet.py) —
and records `scope_violation`, `causal_category`, and free-text notes as
`GroundTruthReview` rows in `data/labels/*.jsonl`.

[faisla/labeling/agreement.py](faisla/labeling/agreement.py) computes plain
percent agreement on both fields, overall and per failure class. That number
gates everything: if the author and an independent reader cannot agree on what
happened, no adjudicator result computed against this oracle means anything.

### More than one reviewer

§9.1 says "the second reviewer", singular, but the module supports N reviewers
and `compute_all_pairwise()` computes every pair. With two reviewers that is
three figures, and the third is not a variant of the first two:

| Comparison | Answers |
|---|---|
| author vs reviewer A | is the author's label defensible? |
| author vs reviewer B | likewise, independently |
| reviewer A vs reviewer B | **is the task well-posed at all?** |

Author-vs-reviewer confounds *"the author was wrong"* with *"the scenario is
undecidable"*. Only reviewer-vs-reviewer separates them: reviewers who agree
with each other but not the author indicate an author problem; reviewers who
disagree with each other indicate a schema problem.

`compute_agreement()` raises on a multi-reviewer file unless given an explicit
`reviewer_id`. It must never pick one silently — the earlier implementation
indexed rows by `scenario_id` alone, so a two-reviewer file collapsed to
whichever reviewer's rows came last in the file and reported a clean-looking
result for that reviewer under the label of the whole review.

### Which comparison gates the kill test (decided 2026-08-26)

`evaluate_kill_test()` takes exactly one `scope_agreement`/`causal_agreement`
pair, and the verdict is **not** invariant across the three candidates. The
convention is therefore fixed by decision rather than left to the caller:

> **§13 is fed the author-vs-reviewer-B comparison** — the **lower** of the two
> author-vs-reviewer results. Not author-vs-reviewer-A, and not
> reviewer-A-vs-reviewer-B.

Two independent reasons:

1. **The gate is inherently an author-vs-external question.** The agreement
   gate validates the specific document `metrics.py` will score correctness
   against — the authored ground truth. Whether that document is trustworthy
   is a question about the author's labels versus an outside reader, so a
   reviewer-vs-reviewer figure cannot gate it however informative it is.
2. **The lower of the two valid comparisons is used**, to avoid selecting the
   more favourable result after having seen both. Both author-vs-reviewer
   comparisons are equally valid a priori; picking the higher one after the
   fact would be choosing the number that flatters the corpus.

**reviewer-A-vs-reviewer-B remains a required diagnostic.** It is reported alongside
every verdict, per class, and exists specifically to separate *author error*
from *genuine indeterminacy*:

- reviewers agree with each other, disagree with the author → **author error**
- reviewers disagree with each other → **the scenario is indeterminate**

It does not gate CONTINUE. A class where the reviewers disagree with each
other cannot be repaired by relabelling the author's call, and reading that
signal off an author-vs-reviewer number is not possible.

### Day 1 proceeds on a considered INCONCLUSIVE

**Day 1 passes the gate to Step 5 on `INCONCLUSIVE`, not on `CONTINUE`.** This
is a recorded decision, not an oversight, and the distinction matters when
reading any Day-1 result: the corpus was not certified sound, it was certified
*understood*.

The verdict is final for Day 1 at author-vs-reviewer-B causal **79.2%**. What
justifies proceeding is the composition of the shortfall, not its size:

- **zero unresolved corpus bugs** — the three schema defects found have been
  corrected, and the NO_VIOLATION invariant now makes that class of defect
  unrepresentable;
- **five legitimate contested cases**, each documented in
  [CORPUS.md](CORPUS.md#contested--lower-confidence-ground-truth-calls):
  - three **expected-indeterminate** `AMBIGUOUS_HUMAN_INSTRUCTION` scenarios,
    where the disagreement is about whether an agent that fails to ask for
    clarification has erred — a real open question, not a labelling slip;
  - two **deliberately-hard boundary cases** (SC-MPI-001, SC-DRE-001), authored
    as off-diagonal `failure_class`/`causal_category` pairs precisely because
    they discriminate between adjudicators.

An `INCONCLUSIVE` whose every component is identified and accounted for
supports different follow-on work than an `INCONCLUSIVE` of unknown origin.
The first is a measurement with known error terms; the second is noise.

**This bucket is closed.** Any *new* disagreement — a scenario outside the five
above, or a new scenario added later — is a **fresh signal and must be
investigated on its own terms**. It must not be absorbed into "the known
contested set" by analogy. The known set is enumerated, and the enumeration is
what makes proceeding defensible; an unenumerated addition destroys exactly
that property. If the contested set grows, the gate is re-argued, not
re-labelled.

**Verdict bound under this convention: `INCONCLUSIVE`** — author-vs-reviewer-B
causal agreement is 79.2%, inside the 70–80% gray zone. The §13 escape hatch
that would route an AHI-concentrated shortfall elsewhere does not apply,
because it requires every non-AHI class at ≥80% and both
`MERCHANT_PROMPT_OR_CATALOG_INJECTION` and
`SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY` sit at 75% against reviewer B. Figures in
[CORPUS.md](CORPUS.md#agreement-against-corrected-ground-truth).

`faisla/labeling/` imports `CausalCategory` from `world.models` — the enum
definition only — and never `GroundTruth` or `ScenarioWorld`.

---

## Evidence layer — E0 and E3

Two evidence conditions, rendered by `faisla/evidence/`:

| | E0 — conventional | E3 — agent-aware |
|---|---|---|
| What it models | what a card-network dispute process can see today | E0 plus the delegated-authority record |
| Anchored to | the external anchor in [E0_ANCHOR.md](E0_ANCHOR.md) | the artefacts an agent platform produces anyway |
| Carries | transaction record, merchant representment evidence, cardholder claim | + mandate, logged instruction, tool-call log, execution state, merchant-side signals |
| Cardholder claim | present but **uncorroborated** | same statement, **corroborated** by the logged instruction |

### The E0 anchor is a blocking gate (§15 step 4)

§13 returns KILL when `flips_are_manufactured` — *"flips traceable only to E0
being artificially weak"*. So E0 may not be authored to taste. It is anchored
to the card-network dispute-evidence record as specified by the Stripe Dispute
API, whose `evidence` hash enumerates 26 named fields, corroborated against
Visa CE3.0 and the RBI liability circular. The construction rule is:

> E0 may contain a field only if that field has a named counterpart in the
> anchor's evidence list, or is a core attribute of the dispute record itself.

The finding that clears the gate: **not one of the 26 fields can express
delegated authority.** The conventional framework treats authorisation as a
binary identity question — did the cardholder or an authorised representative
make the payment — and an agent under a mandate is an authorised
representative. There is no field in which *scope* of authority can be posed.
E0 is therefore weak on exactly this benchmark's question for reasons outside
this project's control, which is what makes an E0→E3 flip a real finding.
Full derivation and per-field mapping in [E0_ANCHOR.md](E0_ANCHOR.md).

### The load-bearing risk is an E0 that is too STRONG

With thinness externally justified, the remaining danger inverts. §13 can
detect an E0 that is too weak; **nothing in the kill test can detect an E0
that is too strong.** Agent-aware content leaking into the baseline would
suppress flips and read as a clean negative result.

So it is enforced rather than trusted, in two places:

- a `model_validator` on `EvidencePacket` rejects an E0 packet carrying
  `agent_context`, and rejects an E0 claim marked `corroborated`;
- [tests/test_evidence_rendering.py](tests/test_evidence_rendering.py) scans
  **rendered E0 values** — not just the schema — for injection payloads,
  manipulation and inconsistency details, and tool-call names.

E3 is built by rendering E0 and extending it, so the conventional fields are
byte-identical across conditions by construction. Any adjudication difference
is attributable to the added record, never to the shared part being rendered
two different ways. Tests pin that equality.

### Assertion versus record

E0 and E3 carry the same cardholder statement. Omitting it from E0 would make
the baseline unfairly thin — a real dispute does include the cardholder's
claim (`customer_communication`). What differs is evidentiary status: at E0 it
is an assertion nothing can authenticate; at E3 the instruction is a logged,
timestamped system artefact bound to a mandate and cross-checkable against the
tool-call log. A flip driven by *"the assertion turned out to be corroborated"*
is a genuine evidentiary flip, and this is the honest rendering of how disputes
actually work.

---

## Kill test (§13)

[faisla/evaluation/kill_test.py](faisla/evaluation/kill_test.py) is a pure
function returning `CONTINUE` / `KILL` / `INCONCLUSIVE` from held-out data plus
the §9.1 agreement figures. Its thresholds are fixed by the brief and **must
not be adjusted after seeing results**.

Summarised:

- agreement below 70% on either field → `KILL`, unless the shortfall is
  concentrated in `AMBIGUOUS_HUMAN_INSTRUCTION` with every other class at
  ≥80%, in which case → `INCONCLUSIVE`
- `e0_resolves_all`, zero flips, or manufactured flips → `KILL`
- agreement in the 70–80% gray zone → `INCONCLUSIVE`
- `CONTINUE` requires ≥80% on both fields, flip rate ≥20%, confirmed flip
  rationales, and zero reverse flips

Note the interaction with the invariant above: because agreement is the gate,
a schema ambiguity that manufactures author/reviewer disagreement can push a
sound benchmark toward `KILL` for the wrong reason. That is why the invariant
is enforced in the model rather than left to authorial discipline.
