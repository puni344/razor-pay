# E0 External Anchor

**Status: RESOLVED — 2026-08-26. Blocking gate (§15 step 4) cleared.**

E0 is the baseline evidence condition: what a conventional payment-dispute
process can see today. Everything in the experiment depends on E0 being an
*honest* reconstruction of that, because §13 treats a weak E0 as
disqualifying:

> `flips_are_manufactured` — *"True if flips are traceable only to E0 being
> artificially weak."* → **KILL**

If E0 is thin because the author made it thin, every E0→E3 flip is an artefact
and the result is worthless. So E0 must be anchored to an **external,
citable, enumerable** specification that nobody in this project controls.

---

## The anchor

E0 is anchored to the **card-network dispute-evidence record**, as concretely
specified by the Stripe Dispute API — a published, versioned, publicly
documented schema that enumerates exactly what evidence a conventional card
dispute accepts.

| Anchor | Role |
|---|---|
| [Stripe Dispute object](https://docs.stripe.com/api/disputes/object) — the `evidence` hash | **Primary.** 26 named evidence fields; the exhaustive field list E0 may draw from |
| [Stripe dispute reason categories](https://docs.stripe.com/disputes/categories) | The 8 categories a dispute can be filed under, and the defence guidance per category |
| Visa Compelling Evidence 3.0 | What "proof of legitimacy" means conventionally: prior undisputed transactions matching on IP address or device ID |
| RBI, *Limiting Liability of Customers in Unauthorised Electronic Banking Transactions*, DBR.No.Leg.BC.78/09.07.005/2017-18 (6 July 2017) | The conventional **fault-attribution** taxonomy and the burden-of-proof rule |

Stripe is chosen as the primary anchor for a specific reason: it is the most
precisely enumerated public statement of the field set. It is a faithful
implementation of the Visa/Mastercard representment requirements, not an
independent invention, and unlike the network rulebooks it is fetchable and
citable field-by-field. The RBI circular anchors the *attribution* question
that `causal_category` asks; Stripe anchors the *evidence* question that E0
asks.

### The 26 conventional evidence fields

```
access_activity_log          customer_signature            shipping_address
billing_address              duplicate_charge_documentation shipping_carrier
cancellation_policy          duplicate_charge_explanation   shipping_date
cancellation_policy_disclosure duplicate_charge_id          shipping_documentation
cancellation_rebuttal        product_description            shipping_tracking_number
customer_communication       receipt                        uncategorized_file
customer_email_address       refund_policy                  uncategorized_text
customer_name                refund_policy_disclosure
customer_purchase_ip         refund_refusal_explanation
                             service_date / service_documentation
```

---

## Why this makes E0's thinness external, not authored

This is the finding that clears the gate. **Not one of the 26 fields can
express delegated authority.** There is no field for a spending mandate, no
field for the instruction a principal gave an agent, no field for what an
agent did on the principal's behalf, and no field for the agent's reasoning.

That absence is not an oversight in Stripe's schema. It is structural in the
conventional framework, and it shows up most sharply in how the framework
handles authorization. Stripe's guidance for overturning a `fraudulent`
dispute is to demonstrate:

> *"That the legitimate cardholder — or an authorized representative (such as
> an employee or family member) — did in fact make the payment."*

Authorization is a **binary identity question**: was the person who paid
entitled to use the instrument? An AI agent purchasing under a mandate is
precisely an "authorized representative" — so under the conventional test
every scenario in this corpus is *authorized*, and the dispute fails at E0.
But the question this benchmark asks is not *who* paid; it is **whether the
authorized representative stayed inside the scope of the authority it was
given.** The conventional schema has no field in which that question can even
be posed, let alone answered.

Visa CE3.0 sharpens the same point from the other direction. Its test for
legitimacy is two prior undisputed transactions matching on IP address or
device fingerprint — *identity continuity*. An agent that reliably overspends
its mandate from the same device passes CE3.0 every time.

**Therefore E0 is weak on scope-of-authority questions for reasons entirely
outside this project's control**, and an E0→E3 flip driven by delegated-
authority evidence is a real finding about the conventional framework, not an
artefact of how E0 was written. That is what the gate required.

The corresponding risk is now the *opposite* one — an E0 accidentally made
**stronger** than reality by leaking agent-aware content into it. §15 step 4 is
therefore discharged with a construction rule, below, and a test that enforces
it.

---

## Construction rule for E0

> **E0 may contain a field only if that field has a named counterpart in the
> anchor's 26-field evidence list, or is a core attribute of the dispute
> record itself (amount, currency, merchant descriptor, timestamp, status,
> reason category).**

Mapping actually used, with each E0 field's anchor named:

| E0 field | Anchor field | Source in scenario |
|---|---|---|
| `transaction.amount` | dispute `amount` | `payment_outcome.amount_charged` |
| `transaction.currency` | dispute `currency` | fixed INR |
| `transaction.merchant_descriptor` | statement descriptor | `payment_outcome.merchant_charged` |
| `transaction.merchant_category` | MCC | `agent_action.category` |
| `transaction.created` / `status` | dispute `created` / charge status | `payment_outcome` |
| `claim.reason_category` | dispute `reason` | derived — rules below |
| `claim.claim_statement` | `customer_communication` | `user_intent`, **marked unverified** |
| `merchant_evidence.product_description` | `product_description` | `agent_action.product` |
| `merchant_evidence.receipt` | `receipt` | `agent_action` amount/merchant/timestamp |
| `merchant_evidence.refund_policy` | `refund_policy` | `merchant_behavior.policy_snapshot` |
| `merchant_evidence.service_date` | `service_date` | `agent_action.timestamp` |
| `merchant_evidence.duplicate_charge_explanation` | `duplicate_charge_explanation` | charged vs. unit price |

Excluded from E0 with reasons: `mandate` (no anchor counterpart),
`tool_call_log` (none), `ambiguous_instruction` (none),
`catalog_injection_present` / `cart_manipulated` (none — merchant misconduct
has no self-reported field; the merchant is the party submitting evidence),
`execution_state.system_state_inconsistent` (none).

### The claim statement is an assertion, not evidence

The one subtle case. A conventional dispute *does* carry the cardholder's own
account of what they wanted — that is `customer_communication`, and omitting
it would make E0 unfairly thin. So E0 carries the cardholder's statement.

The difference from E3 is **evidentiary status, not content**:

- **E0** — the statement is an *unverified assertion*. Nothing in the record
  corroborates that the cardholder ever said it. It is rendered with
  `verified: False` and an explicit provenance note.
- **E3** — the same instruction appears as a *system record*: logged,
  timestamped, bound to a mandate, and cross-checkable against the agent's
  tool calls.

This distinction is the honest one and it is how real disputes work: a
cardholder's claim is a claim, and the conventional framework has no way to
authenticate it. A flip driven by *"the assertion turned out to be
corroborated by the execution log"* is a genuine evidentiary flip.

### Reason-category derivation

The cardholder picks the category in reality; here it is derived
deterministically from observable facts only, never from ground truth:

| Condition (observable) | Category |
|---|---|
| `amount_charged` > `agent_action.amount` and `duplicate_or_retry` | `duplicate` |
| `agent_action.amount` > mandate-free expectation set by the claim | `product_unacceptable` |
| otherwise | `product_unacceptable` (goods not as intended) |

`fraudulent` is deliberately **never** derived: under the anchor's own test the
cardholder authorized an agent that made the payment, so no scenario here is
conventionally fraudulent. Recording that is part of the finding.

**On the concentration of reason codes.** All 20 non-duplicate scenarios map to
`product_unacceptable`, and that concentration is a property of the externally
anchored reason-code taxonomy's granularity, not the result of any collapsing
or remapping performed by `conventional.py` — the renderer applies the anchor's
eight categories as published, and the anchor simply has no finer-grained
category for "the authorised representative bought the wrong thing", so every
scope-of-authority failure in this corpus lands in the same bucket. This is
itself part of the E0 finding rather than a defect in the rendering: a taxonomy
that cannot distinguish an agent overspending its mandate from a merchant
shipping a disappointing product is a taxonomy with no vocabulary for delegated
authority. The distribution is reported as it falls; neither the scenario
labels nor the mapping have been adjusted to produce a more even spread.

---

## Consequences for the kill test

Two predictions follow from the anchor, recorded **now, before rendering**, so
they cannot be fitted afterwards:

1. **`DUPLICATE_OR_RETRY_EXECUTION` should largely resolve at E0.** The anchor
   has three dedicated duplicate fields (`duplicate_charge_id`,
   `duplicate_charge_documentation`, `duplicate_charge_explanation`) and an
   entire reason category. Conventional evidence handles duplicate detection
   well because it is a reconciliation question about two records, not an
   attribution question about intent.
2. **The other five classes should not resolve at E0**, because each turns on
   scope of delegated authority, for which the anchor has no field.

Prediction 1 independently corroborates the disclosure already hard-coded in
[faisla/evaluation/report.py](faisla/evaluation/report.py): duplicate detection
is a *reconciliation* construct and the other five are a *liability* construct,
and the two must never be pooled. That disclosure was written before this
anchor was researched; the anchor's field list turns out to explain exactly
why the constructs come apart. This is also why §13 computes flip rate over
held-out **non-duplicate** scenarios only — `held_out_non_dup_count` = 15.

If prediction 2 fails — if E0 resolves the liability classes too — that is
`e0_resolves_all` and the correct verdict is KILL.

---

## Sources

- [Stripe — The Dispute object (`evidence` hash, `reason` enum)](https://docs.stripe.com/api/disputes/object)
- [Stripe — Dispute reason code categories and defence guidelines](https://docs.stripe.com/disputes/categories)
- [Visa Compelling Evidence 3.0 — requirements overview](https://www.checkout.com/blog/visa-compelling-evidence-3-0)
- [RBI — Harmonisation of Turn Around Time and customer compensation for failed transactions (DPSS.CO.PD.No.629/02.01.2014/2019-20)](https://www.rbi.org.in/commonman/English/scripts/Notification.aspx?Id=3074)
- [RBI — Limiting Liability of Customers in Unauthorised Electronic Banking Transactions (summary)](https://ssrana.in/articles/rbi-issues-circular-limiting-liability-of-customers-in-unauthorized-electronic-banking-transactions/)

The RBI primary PDFs at `rbidocs.rbi.org.in` are behind a CAPTCHA and could not
be fetched directly; the circular number, date, and the three-way attribution
structure (bank deficiency / third-party breach / customer negligence, with
burden of proof on the bank) are corroborated across multiple secondary
sources, cited above.
