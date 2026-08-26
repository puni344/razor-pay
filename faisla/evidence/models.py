"""
FAISLA — Evidence Packet Models

The EvidencePacket is what the adjudicator sees. It is the only input to
adjudicate(), and it must carry observable facts only — never the oracle's
verdict, never the author's rationale.

Two evidence conditions:

  E0  CONVENTIONAL   — what a card-network dispute process can see today.
                       Every field traces to a named field in the external
                       anchor; see E0_ANCHOR.md.
  E3  AGENT_AWARE    — E0 plus the delegated-authority record: the mandate,
                       the logged instruction, the agent's tool calls, and
                       the execution/merchant signals that no conventional
                       dispute schema has a field for.

The E0/E3 difference is deliberately NOT "E3 has more facts invented for it".
E3 adds exactly the record an agent-mediated payment system would actually
produce and a conventional one would not. If E0 were thin because the author
made it thin, §13 would treat every flip as manufactured and return KILL.

Structural constraint
---------------------
Nothing under faisla/evidence/ may import the oracle, the ground-truth
verdict type, or the full hidden-world record. Renderers receive the specific observable
sub-records they need and nothing else. Enforced by test_no_leakage.py.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class EvidenceCondition(str, Enum):
    """The two evidence conditions named by the brief.

    Only E0 and E3 exist. The gap in numbering is the brief's, not an
    omission here — inventing intermediate conditions would change what
    the flip metric measures.
    """
    E0 = "E0"
    E3 = "E3"


class DisputeReasonCategory(str, Enum):
    """Dispute reason categories, from the external anchor.

    These are the eight categories the anchor organises every network reason
    code into. Reproduced exactly; this project does not add to them.

    Note FRAUDULENT is never derived by the renderers. Under the anchor's own
    test — did the legitimate cardholder or an authorised representative make
    the payment — an agent acting under a mandate is an authorised
    representative, so no scenario in this corpus is conventionally
    fraudulent. See E0_ANCHOR.md.
    """
    CREDIT_NOT_PROCESSED = "credit_not_processed"
    DUPLICATE = "duplicate"
    FRAUDULENT = "fraudulent"
    GENERAL = "general"
    PRODUCT_NOT_RECEIVED = "product_not_received"
    PRODUCT_UNACCEPTABLE = "product_unacceptable"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    UNRECOGNIZED = "unrecognized"


class DisputeClaim(BaseModel):
    """The cardholder's stated reason for disputing.

    `statement` carries what the cardholder says they wanted. Under E0 this is
    an ASSERTION: `corroborated` is False, because a conventional dispute
    record has no way to authenticate it — the anchor's counterpart field is
    `customer_communication`, which is submitted, not verified.

    Under E3 the same content is corroborated by the logged instruction in
    AgentContext, and `corroborated` is True. The E0/E3 difference here is
    evidentiary status, not content. That distinction is the honest one and
    it is what makes a flip on this axis a real evidentiary flip rather than
    a manufactured one.
    """
    reason_category: DisputeReasonCategory
    statement: str
    corroborated: bool
    provenance: str


class TransactionRecord(BaseModel):
    """Core attributes of the disputed charge.

    Maps to the anchor's dispute-object attributes: amount, currency,
    statement descriptor, MCC, created, status.
    """
    transaction_id: str
    amount: Decimal
    currency: str
    merchant_descriptor: str
    merchant_category: str
    created: datetime
    status: str


class MerchantEvidence(BaseModel):
    """Evidence the merchant would submit in representment.

    Every field here has a named counterpart in the anchor's 26-field
    evidence hash. Fields with no counterpart do not belong in E0 and are
    not present on this model at any condition — merchant misconduct in
    particular has no self-reported field, because the merchant is the party
    submitting the evidence.
    """
    product_description: str                      # product_description
    receipt: str                                  # receipt
    refund_policy: str                            # refund_policy
    service_date: datetime                        # service_date
    duplicate_charge_explanation: str | None = None   # duplicate_charge_explanation


class MandateRecord(BaseModel):
    """The principal's delegated spending authority. E3 only.

    No counterpart exists anywhere in the anchor's evidence schema. This is
    the single most important structural difference between the conditions:
    conventional dispute evidence can establish WHO paid, but has no field in
    which to express the LIMITS of what they were authorised to pay for.
    """
    max_amount: Decimal
    allowed_categories: list[str]
    allowed_merchants: list[str] | None = None
    allowed_products: list[str] | None = None


class AgentContext(BaseModel):
    """The delegated-authority record. E3 only.

    Present in an agent-mediated payment system's own logs; absent from every
    conventional dispute schema. Carries observable execution facts only —
    what was instructed, what the agent did, what the merchant's systems did,
    and whether execution retried.

    Deliberately absent: any assessment of whether the outcome was correct.
    That is the adjudicator's job and the oracle's verdict, not evidence.
    """
    mandate: MandateRecord
    logged_instruction: str
    instruction_flagged_ambiguous: bool
    tool_call_log: list[str]

    duplicate_or_retry: bool
    retry_count: int
    system_state_inconsistent: bool
    inconsistency_detail: str | None = None

    catalog_injection_present: bool
    injection_payload: str | None = None
    cart_manipulated: bool
    manipulation_detail: str | None = None

    unit_price: Decimal

# ---------------------------------------------------------------------------
# Evidence packets — structural separation, not runtime filtering
# ---------------------------------------------------------------------------
#
# E0 and E3 are DIFFERENT TYPES. The conventional packet has no
# agent_context field, no mandate field, and no tool-trace field to set —
# not "set to None", but absent from the type, exactly as
# ScenarioFactsForReview has no ground_truth field.
#
# `extra="forbid"` closes the other half: an unknown key is a construction
# error rather than silently dropped. So every one of these is rejected at
# construction, by the type system rather than by a validator that has to
# remember to run:
#
#     agent_context, original_delegated_intent, mandate_constraints,
#     agent_tool_action_trace, merchant_content_presented,
#     execution_provenance_summary, injection_payload, manipulation_detail
#
# The runtime validators below are kept as defence-in-depth. They are no
# longer the primary guard.


class _EvidencePacketBase(BaseModel):
    """Fields common to both conditions.

    Held identical across E0 and E3 so that any adjudication difference is
    attributable to the added record, never to the shared part being
    rendered two different ways.
    """
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    claim: DisputeClaim
    transaction: TransactionRecord
    merchant_evidence: MerchantEvidence


class ConventionalEvidencePacket(_EvidencePacketBase):
    """E0 — what a card-network dispute process can see today.

    Structurally absent, by design and not by omission:

      - agent_context        the delegated-authority record
      - mandate              the limits of the authority granted
      - tool_call_log        what the agent actually did
      - injection payloads   merchant-side signals; the merchant is the
        and manipulation     party submitting evidence and does not
        details              self-report misconduct

    None of these has a named counterpart in the external anchor's 26-field
    evidence list (E0_ANCHOR.md), so none may appear here. A packet that
    carried them would be an E0 stronger than the real conventional
    framework — and §13 cannot detect that failure, because
    `flips_are_manufactured` catches an E0 that is too weak, never one that
    is too strong.
    """
    condition: Literal[EvidenceCondition.E0] = EvidenceCondition.E0

    @model_validator(mode="after")
    def _claim_cannot_be_corroborated(self) -> "ConventionalEvidencePacket":
        """Defence-in-depth: a conventional record cannot authenticate the
        cardholder's statement, so the claim may not be marked corroborated."""
        if self.claim.corroborated:
            raise ValueError(
                f"{self.scenario_id}: E0 claim is marked corroborated. A "
                f"conventional dispute record cannot authenticate the "
                f"cardholder's statement."
            )
        return self


class AgentAwareEvidencePacket(_EvidencePacketBase):
    """E3 — E0 plus the delegated-authority record.

    `agent_context` is required, not optional: an E3 packet without it is
    just an E0 wearing the wrong label, and would silently understate the
    flip metric.
    """
    condition: Literal[EvidenceCondition.E3] = EvidenceCondition.E3
    agent_context: AgentContext


# The adjudicator accepts this and nothing else. Both members carry only
# observable facts — no verdict, no rationale, no authorial commentary.
EvidencePacket = ConventionalEvidencePacket | AgentAwareEvidencePacket
