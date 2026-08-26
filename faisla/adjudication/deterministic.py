"""
FAISLA — Deterministic Adjudicator

A pure, rule-versioned function from EvidencePacket to AdjudicationResult.

CALIBRATION STATUS — v0.2.0, HELD-OUT-INFORMED
-----------------------------------------------
v0.1.0 was calibrated on the six DEV scenarios only and frozen before the
held-out run; its results are the pilot's one unbiased held-out estimate.

v0.2.0 fixes two bugs that were DISCOVERED FROM held-out results, and is
therefore held-out-informed by construction. Its numbers measure whether the
fixes work, NOT generalisation. Reporting v0.2.0 as a held-out result without
that caveat would be the exact error the dev/held-out split exists to prevent.

No rule logic in this file may be edited after the freeze. If a genuine
implementation bug is found in review, the remedy is a NEW rule version with
the frozen version's results preserved alongside it — never an edit in place.
Adjusting any rule after seeing held-out results would make the held-out
split a second dev split and destroy the only unbiased estimate the pilot
has (§10).

DESIGN CONSTRAINTS
------------------
* Deterministic. No randomness, no clock, no I/O. Same packet in, same
  result out, always.
* Consumes EvidencePacket only. No access to the hidden-world record, the
  ground-truth verdict, reviewer labels, or the oracle.
* Never branches on scenario_id. The id is copied to the output for
  bookkeeping and is never read as a signal. `failure_class` is not on the
  packet at all, so it cannot be consulted even accidentally.
* Rules key on FIELDS, not on scenarios. A rule that only ever fires for one
  DEV scenario is a memorised answer, not a rule.

THE E0/E3 ASYMMETRY IS THE POINT
--------------------------------
E0 carries the cardholder's statement, so a budget figure is *readable* under
both conditions. What differs is whether it is *probative*: at E0 the
statement is an uncorroborated assertion (`claim.corroborated is False`) with
nothing in the record to authenticate it, so it cannot by itself establish
that authority was exceeded. At E3 the same instruction is a logged system
artefact bound to a mandate.

So E0 findings rest only on self-contained documentary contradictions — the
settled amount disagreeing with the merchant's own receipt — and E3 findings
may additionally rest on the delegated-authority record. This is the honest
reading of the anchor, not a handicap imposed on E0.
"""

from __future__ import annotations

import re
from decimal import Decimal

from faisla.adjudication.schemas import (
    AdjudicationResult,
    CausalCategory,
    RuleFiring,
    ScopeFinding,
    Sufficiency,
)
from faisla.evidence.models import EvidenceCondition, EvidencePacket

# v0.2.0 — two disclosed bug fixes over dev-calibration-0.1.0.
#
# EPISTEMIC STATUS, encoded in the version string on purpose: both bugs were
# identified FROM held-out results. The held-out split has therefore informed
# these rules, and v0.2.0's held-out numbers are NO LONGER an unbiased
# held-out estimate. Only dev-calibration-0.1.0's numbers are. Every result
# row carries this string so the distinction cannot be lost downstream.
#
# v0.1.0's source is archived verbatim at adjudication/frozen_v0_1_0.py and
# its results at results/adjudication_dev-calibration-0.1.0.jsonl. Neither is
# overwritten.
RULE_VERSION = "holdout-informed-bugfix-0.2.0"


# ---------------------------------------------------------------------------
# Instruction budget extraction
# ---------------------------------------------------------------------------
# Deterministic patterns over the instruction text. The most restrictive match
# wins, so adding a pattern can only ever tighten the extracted budget.
#
# NOTE (design judgment, not a mechanical comparison): natural-language budget
# extraction is a judgment about which phrasings to cover. The patterns below
# were written against the DEV instructions and will silently fail to extract
# a budget phrased another way. A missed budget yields UNDETERMINED rather
# than a wrong finding, so the failure mode is conservative — but it is a
# judgment and is reported as one.
_BUDGET_PATTERNS = (
    r"under\s+(?:rs\.?\s*)?(\d+)",
    r"below\s+(?:rs\.?\s*)?(\d+)",
    r"budget\s+(?:of\s+)?(?:rs\.?\s*)?(\d+)",
    r"(?:rs\.?\s*)?(\d+)\s*(?:rupees?)?\s*max(?:imum)?",
    r"max(?:imum)?\s+(?:of\s+)?(?:rs\.?\s*)?(\d+)",
    r"no\s+more\s+than\s+(?:rs\.?\s*)?(\d+)",
    r"up\s+to\s+(?:rs\.?\s*)?(\d+)",
    # --- v0.2.0 fix (b): the three phrasings that caused held-out misses ---
    # "around/about/approximately X-Y" — the UPPER bound is the cap. The
    # lower bound is deliberately not captured: "budget around 3000-4000"
    # states a ceiling of 4000, and treating 3000 as the cap would invent a
    # stricter limit than the instruction gave.
    r"(?:around|about|approximately|budget(?:\s+of)?)\s+"
    r"(?:rs\.?\s*)?\d+\s*(?:-|–|to)\s*(?:rs\.?\s*)?(\d+)",
    # "listed at X" / "priced at X" — a price the principal named.
    r"(?:listed|priced)\s+at\s+(?:rs\.?\s*)?(\d+)",
    # "saw it at X" / "saw it listed at X"
    r"saw\s+it\s+(?:listed\s+)?at\s+(?:rs\.?\s*)?(\d+)",
)


def extract_instruction_budget(text: str) -> Decimal | None:
    """Extract the tightest explicit spending cap stated in an instruction.

    Returns None when no pattern matches — which is a determinate "no budget
    was stated", not an error.
    """
    found = []
    lowered = text.lower()
    for pattern in _BUDGET_PATTERNS:
        for match in re.finditer(pattern, lowered):
            found.append(Decimal(match.group(1)))
    return min(found) if found else None


# ---------------------------------------------------------------------------
# Scope rules
# ---------------------------------------------------------------------------

def _scope_e0(packet) -> tuple[ScopeFinding, list[RuleFiring]]:
    """Scope under conventional evidence.

    Only ONE class of scope finding is available: a self-contained
    documentary contradiction between the settled amount and the merchant's
    own receipt. Everything else about authority is unrepresented in the
    conventional record.
    """
    fired: list[RuleFiring] = []

    explanation = packet.merchant_evidence.duplicate_charge_explanation
    if explanation is not None:
        fired.append(RuleFiring(
            rule_id="E0-S1-settled-exceeds-receipt",
            observation=(
                f"transaction.amount={packet.transaction.amount} exceeds the "
                f"line item on the merchant's own receipt; "
                f"duplicate_charge_explanation is populated. The contradiction "
                f"is internal to the merchant's evidence and needs no "
                f"corroboration of the cardholder's account."
            ),
        ))
        return ScopeFinding.OUT_OF_SCOPE, fired

    fired.append(RuleFiring(
        rule_id="E0-S2-no-authority-record",
        observation=(
            f"claim.corroborated={packet.claim.corroborated}; the conventional "
            f"record contains no mandate, no logged instruction and no "
            f"execution trace, so nothing establishes what authority was "
            f"granted. The cardholder's statement is an assertion only."
        ),
    ))
    return ScopeFinding.UNDETERMINED, fired


def _scope_e3(packet) -> tuple[ScopeFinding, list[RuleFiring]]:
    """Scope under agent-aware evidence.

    Each rule compares two recorded values. Any one breach is sufficient;
    all breaches found are reported, so a result shows every way in which
    authority was exceeded rather than only the first.
    """
    ctx = packet.agent_context
    mandate = ctx.mandate
    charged = packet.transaction.amount
    fired: list[RuleFiring] = []

    budget = extract_instruction_budget(ctx.logged_instruction)
    if budget is not None and charged > budget:
        fired.append(RuleFiring(
            rule_id="E3-S1-instruction-budget-exceeded",
            observation=(
                f"logged_instruction states a cap of {budget}; "
                f"transaction.amount={charged} exceeds it. The instruction is "
                f"a logged system artefact, not an uncorroborated claim."
            ),
        ))

    if packet.transaction.merchant_category not in mandate.allowed_categories:
        fired.append(RuleFiring(
            rule_id="E3-S2-category-outside-mandate",
            observation=(
                f"transaction.merchant_category="
                f"{packet.transaction.merchant_category!r} is not in "
                f"mandate.allowed_categories={mandate.allowed_categories!r}."
            ),
        ))

    if mandate.allowed_merchants is not None:
        if packet.transaction.merchant_descriptor not in mandate.allowed_merchants:
            fired.append(RuleFiring(
                rule_id="E3-S3-merchant-outside-mandate",
                observation=(
                    f"transaction.merchant_descriptor="
                    f"{packet.transaction.merchant_descriptor!r} is not in "
                    f"mandate.allowed_merchants={mandate.allowed_merchants!r}."
                ),
            ))

    if charged > mandate.max_amount:
        fired.append(RuleFiring(
            rule_id="E3-S4-mandate-ceiling-exceeded",
            observation=(
                f"transaction.amount={charged} exceeds "
                f"mandate.max_amount={mandate.max_amount}."
            ),
        ))

    if charged > ctx.unit_price:
        fired.append(RuleFiring(
            rule_id="E3-S5-settled-exceeds-line-item",
            observation=(
                f"transaction.amount={charged} exceeds "
                f"agent_context.unit_price={ctx.unit_price}; more was settled "
                f"than the selected item costs."
            ),
        ))

    # --- v0.2.0 fix (a) ---
    # Merchant-side interference is a scope question, not only a causal one.
    # In v0.1.0 these signals were consulted ONLY by the causal rules, so a
    # merchant that inflated the price into the line item itself
    # (charged == unit_price) tripped no scope rule; scope returned IN_SCOPE
    # and E3-C0 short-circuited to NO_VIOLATION before C1/C2 could ever run.
    # What the principal authorised was the item as presented, not the item
    # as silently altered.
    if ctx.cart_manipulated:
        fired.append(RuleFiring(
            rule_id="E3-S8-cart-manipulated",
            observation=(
                f"agent_context.cart_manipulated=True; cart contents changed "
                f"on the merchant's side after the agent's selection, so what "
                f"settled is not what was authorised — independently of "
                f"whether transaction.amount matches unit_price."
            ),
        ))

    if ctx.catalog_injection_present:
        fired.append(RuleFiring(
            rule_id="E3-S9-catalog-injection-present",
            observation=(
                f"agent_context.catalog_injection_present=True; "
                f"merchant-controlled catalog content carried instructions "
                f"directed at the agent, so the selection was not made "
                f"solely under the principal's authority."
            ),
        ))

    if ctx.system_state_inconsistent:
        fired.append(RuleFiring(
            rule_id="E3-S6-settlement-not-matched-by-fulfilment",
            observation=(
                f"agent_context.system_state_inconsistent=True; the settled "
                f"charge is not corroborated by a consistent fulfilment "
                f"record."
            ),
        ))

    if fired:
        return ScopeFinding.OUT_OF_SCOPE, fired

    fired.append(RuleFiring(
        rule_id="E3-S7-within-delegated-authority",
        observation=(
            f"transaction.amount={charged} is within "
            f"mandate.max_amount={mandate.max_amount} and equal to "
            f"unit_price={ctx.unit_price}; category "
            f"{packet.transaction.merchant_category!r} is permitted; "
            f"merchant constraint "
            f"{'satisfied' if mandate.allowed_merchants else 'unrestricted'}; "
            f"no instruction budget exceeded; no execution inconsistency."
        ),
    ))
    return ScopeFinding.IN_SCOPE, fired


# ---------------------------------------------------------------------------
# Causal rules
# ---------------------------------------------------------------------------

def _causal_e0(packet) -> tuple[CausalCategory | None, list[RuleFiring]]:
    """Cause under conventional evidence.

    Always undetermined. Attribution needs a fault signal, and the
    conventional record has no field carrying one: merchant misconduct is
    not self-reported by the merchant submitting the evidence, and there is
    no execution trace or system-state record at all. The absence is the
    anchor's, not this project's — see E0_ANCHOR.md.
    """
    return None, [RuleFiring(
        rule_id="E0-C1-no-fault-signal-available",
        observation=(
            "The conventional record carries no injection flag, no cart "
            "manipulation record, no execution state and no system-state "
            "field. No attribution is derivable from it."
        ),
    )]


def _causal_e3(
    packet, scope: ScopeFinding
) -> tuple[CausalCategory | None, list[RuleFiring]]:
    """Cause under agent-aware evidence.

    Precedence runs from the most specific observable fault signal to the
    least. Merchant-side signals precede system-side, which precede the
    residual attribution to the agent, because each is a positive record of
    a specific actor intervening, whereas AGENT_ERROR is what remains when
    no other actor's fingerprint is present.
    """
    ctx = packet.agent_context

    if scope is ScopeFinding.IN_SCOPE:
        return CausalCategory.NO_VIOLATION, [RuleFiring(
            rule_id="E3-C0-no-violation-to-attribute",
            observation=(
                "Scope finding is IN_SCOPE; there is no violation whose cause "
                "could be assigned."
            ),
        )]

    if ctx.cart_manipulated:
        return CausalCategory.MERCHANT_INDUCED, [RuleFiring(
            rule_id="E3-C1-cart-manipulated",
            observation=(
                f"agent_context.cart_manipulated=True. The cart contents "
                f"changed on the merchant's side after the agent's selection."
            ),
        )]

    if ctx.catalog_injection_present:
        return CausalCategory.MERCHANT_INDUCED, [RuleFiring(
            rule_id="E3-C2-catalog-injection-present",
            observation=(
                f"agent_context.catalog_injection_present=True. Merchant-"
                f"controlled catalog content carried instructions directed at "
                f"the agent."
            ),
        )]

    if ctx.system_state_inconsistent:
        return CausalCategory.SYSTEM_ERROR, [RuleFiring(
            rule_id="E3-C3-system-state-inconsistent",
            observation=(
                f"agent_context.system_state_inconsistent=True with no "
                f"merchant-side signal present."
            ),
        )]

    if ctx.duplicate_or_retry and packet.transaction.amount > ctx.unit_price:
        return None, [RuleFiring(
            rule_id="E3-C4-duplicate-attribution-undetermined",
            observation=(
                f"agent_context.duplicate_or_retry=True, retry_count="
                f"{ctx.retry_count}, system_state_inconsistent=False. The "
                f"record shows BOTH a system-side anomaly (the execution layer "
                f"reported a retry condition) AND an agent-side decision (the "
                f"agent re-submitted rather than waiting or escalating). "
                f"Nothing in the packet ranks one above the other, so the "
                f"attribution is undetermined rather than assumed."
            ),
        )]

    return CausalCategory.AGENT_ERROR, [RuleFiring(
        rule_id="E3-C5-residual-agent-attribution",
        observation=(
            f"Authority was exceeded with no merchant-side signal "
            f"(cart_manipulated=False, catalog_injection_present=False), no "
            f"system-state inconsistency, and no duplicate execution. The "
            f"remaining actor is the agent."
        ),
    )]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def adjudicate(packet: EvidencePacket) -> AdjudicationResult:
    """Adjudicate one evidence packet. Pure and deterministic.

    The only input is the packet. `packet.scenario_id` is copied to the
    output for bookkeeping and is never branched on.
    """
    if packet.condition is EvidenceCondition.E0:
        scope, scope_rules = _scope_e0(packet)
        causal, causal_rules = _causal_e0(packet)
    else:
        scope, scope_rules = _scope_e3(packet)
        causal, causal_rules = _causal_e3(packet, scope)

    determined = scope is not ScopeFinding.UNDETERMINED and causal is not None
    sufficiency = Sufficiency.SUFFICIENT if determined else Sufficiency.INSUFFICIENT

    if determined:
        rationale = (
            f"Scope resolved to {scope.value} and cause to {causal.value}, "
            f"each from a recorded field comparison."
        )
    elif scope is ScopeFinding.UNDETERMINED and causal is None:
        rationale = (
            "Neither scope nor cause is derivable: the packet contains no "
            "record of the authority granted and no fault signal."
        )
    elif causal is None:
        rationale = (
            f"Scope resolved to {scope.value}, but the packet does not "
            f"determine who is at fault, so the liability question is "
            f"unresolved."
        )
    else:
        rationale = (
            f"Cause would be {causal.value}, but scope is undetermined."
        )

    return AdjudicationResult(
        scenario_id=packet.scenario_id,
        condition=packet.condition,
        rule_version=RULE_VERSION,
        scope_finding=scope,
        causal_category=causal,
        sufficiency=sufficiency,
        sufficiency_rationale=rationale,
        rules_fired=scope_rules + causal_rules,
    )
