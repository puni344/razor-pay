"""
FAISLA — E3 Agent-Aware Evidence Renderer

Renders E0 plus the delegated-authority record: the artefacts an
agent-mediated payment system produces in the ordinary course of operating,
and which no conventional dispute schema has a field for.

What E3 adds over E0
--------------------
  mandate                     the limits of the delegated authority
  logged_instruction          the instruction as a SYSTEM RECORD rather than
                              a cardholder assertion
  instruction_flagged_ambiguous  whether the system itself flagged the
                              instruction as underspecified
  tool_call_log               what the agent actually did, in order
  duplicate/retry state       the execution layer's own account
  injection / manipulation    merchant-side signals observable to the agent
    flags                     platform but not self-reported by the merchant
  unit_price                  line item vs. settled amount

Every one of these is an observable operational fact. None is an assessment
of whether the outcome was right — that is the adjudicator's job and the
oracle's verdict, and neither belongs in evidence.

The claim is re-rendered as corroborated
----------------------------------------
E0 and E3 carry the same cardholder statement. The difference is evidentiary
status: at E0 it is an assertion nothing can authenticate; at E3 the logged
instruction and the tool-call log corroborate or contradict it.

That is the crux of whether flips are manufactured. A flip driven by "the
assertion turned out to be corroborated by the execution log" is a genuine
evidentiary flip about what agent-aware infrastructure makes provable. A flip
driven by "E0 was written thin on purpose" would not be, and §13 would be
right to call it manufactured. See E0_ANCHOR.md.

This module must never import the oracle or the hidden-world record.
"""

from __future__ import annotations

from faisla.evidence.conventional import render_conventional
from faisla.evidence.models import (
    AgentAwareEvidencePacket,
    AgentContext,
    DisputeClaim,
    MandateRecord,
)

# Provenance for the E3 cardholder statement. Contrast the E0 wording: the
# statement is the same, what changed is that the system holds a record of it.
E3_CLAIM_PROVENANCE = (
    "Cardholder statement submitted with the dispute, corroborated against "
    "the agent platform's logged instruction and tool-call record for the "
    "same session. The instruction is a system artefact, not only a claim."
)


def render_agent_aware(
    *,
    scenario_id: str,
    cardholder_statement: str,
    mandate,
    user_intent: str,
    ambiguous_instruction: bool,
    agent_action,
    merchant_behavior,
    execution_state,
    payment_outcome,
) -> AgentAwareEvidencePacket:
    """Render the E3 packet.

    Built by rendering E0 first and extending it, so that E3 is E0-plus by
    construction: the conventional fields cannot silently drift between the
    two conditions, and any difference in adjudication is attributable to the
    added record rather than to the shared part being rendered differently.
    """
    base = render_conventional(
        scenario_id=scenario_id,
        cardholder_statement=cardholder_statement,
        agent_action=agent_action,
        merchant_behavior=merchant_behavior,
        execution_state=execution_state,
        payment_outcome=payment_outcome,
    )

    claim = DisputeClaim(
        reason_category=base.claim.reason_category,
        statement=base.claim.statement,
        corroborated=True,
        provenance=E3_CLAIM_PROVENANCE,
    )

    agent_context = AgentContext(
        mandate=MandateRecord(
            max_amount=mandate.max_amount,
            allowed_categories=list(mandate.allowed_categories),
            allowed_merchants=(
                list(mandate.allowed_merchants)
                if mandate.allowed_merchants is not None
                else None
            ),
            allowed_products=(
                list(mandate.allowed_products)
                if mandate.allowed_products is not None
                else None
            ),
        ),
        logged_instruction=user_intent,
        instruction_flagged_ambiguous=ambiguous_instruction,
        tool_call_log=list(agent_action.tool_call_log),
        duplicate_or_retry=execution_state.duplicate_or_retry,
        retry_count=execution_state.retry_count,
        system_state_inconsistent=execution_state.system_state_inconsistent,
        inconsistency_detail=execution_state.inconsistency_detail,
        catalog_injection_present=merchant_behavior.catalog_injection_present,
        injection_payload=merchant_behavior.injection_payload,
        cart_manipulated=merchant_behavior.cart_manipulated,
        manipulation_detail=merchant_behavior.manipulation_detail,
        unit_price=agent_action.amount,
    )

    return AgentAwareEvidencePacket(
        scenario_id=scenario_id,
        claim=claim,
        transaction=base.transaction,
        merchant_evidence=base.merchant_evidence,
        agent_context=agent_context,
    )
