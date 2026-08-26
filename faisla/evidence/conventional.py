"""
FAISLA — E0 Conventional Evidence Renderer

Renders the evidence a card-network dispute process can see today.

Every field emitted here traces to a named field in the external anchor
documented in E0_ANCHOR.md. The construction rule is:

    E0 may contain a field only if that field has a named counterpart in the
    anchor's 26-field evidence list, or is a core attribute of the dispute
    record itself.

What is deliberately NOT rendered, and why
------------------------------------------
  mandate                       no counterpart — conventional evidence can
                                establish who paid, never the limits of what
                                they were authorised to pay for
  tool_call_log                 no counterpart
  instruction ambiguity flag    no counterpart
  catalog injection / cart      no counterpart — merchant misconduct has no
    manipulation flags          self-reported field; the merchant is the
                                party submitting evidence
  system_state_inconsistent     no counterpart

This renderer is where the honesty of the whole experiment sits. §13 treats
flips traceable to an artificially weak E0 as manufactured and returns KILL.
E0 is thin here because the anchor is thin — not because thinness was
convenient. The opposite failure, an E0 quietly made stronger than reality,
is guarded by the invariant on EvidencePacket.

This module must never import the oracle or the hidden-world record. It
receives the observable sub-records and nothing else.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from faisla.evidence.models import (
    ConventionalEvidencePacket,
    DisputeClaim,
    DisputeReasonCategory,
    MerchantEvidence,
    TransactionRecord,
)

CURRENCY = "INR"

# Provenance string for the E0 cardholder statement. The wording matters:
# it records that the statement is submitted, not established.
E0_CLAIM_PROVENANCE = (
    "Cardholder statement submitted with the dispute. Unverified: the "
    "conventional dispute record contains no artefact corroborating what "
    "the cardholder intended or instructed."
)


def derive_reason_category(
    *,
    amount_charged: Decimal,
    unit_price: Decimal,
    duplicate_or_retry: bool,
) -> DisputeReasonCategory:
    """Pick the dispute category from observable facts alone.

    In reality the cardholder picks this. Here it is derived deterministically
    so that no authorial judgment enters the baseline, using only facts a
    conventional processor can see: what was charged, what the line item cost,
    and whether the processor's own records show a retry.

    FRAUDULENT is never returned. Under the anchor's test for that category —
    did the legitimate cardholder or an authorised representative make the
    payment — an agent acting under a mandate is an authorised representative.
    That every scenario here is conventionally "authorised" is a finding, not
    a gap; see E0_ANCHOR.md.
    """
    if duplicate_or_retry and amount_charged > unit_price:
        return DisputeReasonCategory.DUPLICATE
    return DisputeReasonCategory.PRODUCT_UNACCEPTABLE


def _render_receipt(
    *, product: str, unit_price: Decimal, merchant: str, timestamp: datetime
) -> str:
    """Build the receipt text — the anchor's `receipt` field."""
    return (
        f"{merchant} — {product}\n"
        f"Line item: {unit_price} {CURRENCY}\n"
        f"Transaction time: {timestamp.isoformat()}"
    )


def _render_duplicate_explanation(
    *, amount_charged: Decimal, unit_price: Decimal
) -> str | None:
    """The anchor's `duplicate_charge_explanation`, when the totals disagree.

    Populated purely from the arithmetic of charged-vs-line-item. Note this
    is available at E0: the anchor has three dedicated duplicate fields, which
    is why duplicate detection is expected to resolve conventionally while
    liability attribution is not.
    """
    if amount_charged <= unit_price:
        return None
    multiple = amount_charged / unit_price
    if multiple == multiple.to_integral_value():
        return (
            f"Amount settled ({amount_charged} {CURRENCY}) is "
            f"{int(multiple)}x the line item price ({unit_price} {CURRENCY}); "
            f"consistent with the same order being processed "
            f"{int(multiple)} times."
        )
    return (
        f"Amount settled ({amount_charged} {CURRENCY}) exceeds the line item "
        f"price ({unit_price} {CURRENCY}) by "
        f"{amount_charged - unit_price} {CURRENCY}."
    )


def render_conventional(
    *,
    scenario_id: str,
    cardholder_statement: str,
    agent_action,
    merchant_behavior,
    execution_state,
    payment_outcome,
) -> ConventionalEvidencePacket:
    """Render the E0 packet.

    Parameters are the observable sub-records only. `cardholder_statement` is
    the cardholder's own account of what they wanted — the anchor's
    `customer_communication`. It is carried because omitting it would make E0
    unfairly thin: a real dispute does include the cardholder's claim. It is
    marked uncorroborated because a real dispute cannot authenticate it.
    """
    reason = derive_reason_category(
        amount_charged=payment_outcome.amount_charged,
        unit_price=agent_action.amount,
        duplicate_or_retry=execution_state.duplicate_or_retry,
    )

    claim = DisputeClaim(
        reason_category=reason,
        statement=cardholder_statement,
        corroborated=False,
        provenance=E0_CLAIM_PROVENANCE,
    )

    transaction = TransactionRecord(
        transaction_id=f"txn_{scenario_id}",
        amount=payment_outcome.amount_charged,
        currency=CURRENCY,
        merchant_descriptor=payment_outcome.merchant_charged,
        merchant_category=agent_action.category,
        created=payment_outcome.timestamp,
        status=payment_outcome.status,
    )

    merchant_evidence = MerchantEvidence(
        product_description=agent_action.product,
        receipt=_render_receipt(
            product=agent_action.product,
            unit_price=agent_action.amount,
            merchant=agent_action.merchant,
            timestamp=agent_action.timestamp,
        ),
        refund_policy=merchant_behavior.policy_snapshot,
        service_date=agent_action.timestamp,
        duplicate_charge_explanation=_render_duplicate_explanation(
            amount_charged=payment_outcome.amount_charged,
            unit_price=agent_action.amount,
        ),
    )

    # ConventionalEvidencePacket has no agent_context field to omit — the
    # absence is structural, not a choice made here.
    return ConventionalEvidencePacket(
        scenario_id=scenario_id,
        claim=claim,
        transaction=transaction,
        merchant_evidence=merchant_evidence,
    )
