"""
FAISLA — Hidden World Data Models

All Pydantic models for the hidden-world oracle layer.
No business logic in this file — pure data definitions.

Key architectural constraint: GroundTruth is the single most sensitive field
in this entire codebase. It must never be passed, serialized, or logged anywhere
the second reviewer or the adjudicator can see it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator


class FailureClass(str, Enum):
    """Exactly six fixed failure classes for AI-mediated payment incidents."""
    AGENT_INTERPRETATION_ERROR = "AGENT_INTERPRETATION_ERROR"
    MERCHANT_PROMPT_OR_CATALOG_INJECTION = "MERCHANT_PROMPT_OR_CATALOG_INJECTION"
    MERCHANT_OR_CART_MANIPULATION = "MERCHANT_OR_CART_MANIPULATION"
    DUPLICATE_OR_RETRY_EXECUTION = "DUPLICATE_OR_RETRY_EXECUTION"
    AMBIGUOUS_HUMAN_INSTRUCTION = "AMBIGUOUS_HUMAN_INSTRUCTION"
    SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY = "SYSTEM_STATE_OR_EVIDENCE_INCONSISTENCY"


class CausalCategory(str, Enum):
    """Who is actually at fault — deliberately NOT a 1:1 mapping to FailureClass."""
    AGENT_ERROR = "AGENT_ERROR"
    MERCHANT_INDUCED = "MERCHANT_INDUCED"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    NO_VIOLATION = "NO_VIOLATION"


class Mandate(BaseModel):
    """The user's delegated spending authority to the agent."""
    max_amount: Decimal
    allowed_categories: list[str]
    allowed_merchants: list[str] | None = None
    allowed_products: list[str] | None = None


class AgentAction(BaseModel):
    """What the agent actually did."""
    merchant: str
    category: str
    product: str
    amount: Decimal
    timestamp: datetime
    tool_call_log: list[str]


class MerchantBehavior(BaseModel):
    """How the merchant's system behaved during the transaction."""
    catalog_injection_present: bool
    injection_payload: str | None = None
    cart_manipulated: bool
    manipulation_detail: str | None = None
    policy_snapshot: str


class ExecutionState(BaseModel):
    """Runtime execution context — retries, duplicates, system inconsistencies."""
    duplicate_or_retry: bool
    retry_count: int
    system_state_inconsistent: bool
    inconsistency_detail: str | None = None


class PaymentOutcome(BaseModel):
    """The actual payment that was processed."""
    amount_charged: Decimal
    merchant_charged: str
    timestamp: datetime
    status: str


class GroundTruth(BaseModel):
    """
    The oracle's verdict on what actually happened.

    CRITICAL: This is the single most sensitive field in the codebase.
    It must never be passed to the adjudicator, the evidence renderers,
    or the second reviewer. Only evaluation/ may access it, for scoring.
    """
    scope_violation: bool
    causal_category: CausalCategory
    rationale: str


class GroundTruthCorrection(BaseModel):
    """An audited, after-the-fact amendment to a scenario's GroundTruth.

    Ground truth is never silently overwritten. Every post-authoring change
    to a GroundTruth field appends one of these records to
    ScenarioWorld.corrections, preserving the superseded value and naming
    the independent-review evidence that justified the change.

    Deliberately NOT part of GroundTruth itself: the correction log is
    provenance, not oracle verdict, and must not travel with the verdict
    into scoring. It is also structurally absent from
    ScenarioFactsForReview, so it can never reach a second reviewer.
    """
    date: str                 # ISO-8601 date the correction was applied
    field: str                # dotted path, e.g. "ground_truth.causal_category"
    previous_value: str       # the superseded value, verbatim
    corrected_value: str      # the value now in force
    evidence_ref: str         # which independent-review record justified it
    rationale: str            # why the reviewer's reading supersedes the author's
    approved_by: str          # who authorised the change

    # A correction can itself be wrong. When that happens the earlier entry is
    # NOT deleted — it is marked, and a later entry supersedes it. These fields
    # make that chain first-class rather than prose buried in `rationale`, so a
    # reader of the model (not just the YAML) can see which entry is in force.
    supersedes: str | None = None        # names the entry this one replaces
    superseded_by: str | None = None     # set on the entry that was replaced
    superseded_note: str | None = None   # why the superseded entry was wrong


class ScenarioWorld(BaseModel):
    """
    Complete hidden-world record for a single scenario.

    Contains everything: latent facts AND ground truth.
    Only world/ and evaluation/ code should handle this type.
    """
    scenario_id: str
    seed: int
    failure_class: FailureClass
    split: Literal["dev", "holdout"]
    mandate: Mandate
    user_intent: str
    agent_action: AgentAction
    merchant_behavior: MerchantBehavior
    execution_state: ExecutionState
    ambiguous_instruction: bool
    ambiguity_detail: str | None = None
    payment_outcome: PaymentOutcome
    ground_truth: GroundTruth
    corrections: list[GroundTruthCorrection] = []

    @model_validator(mode="after")
    def _check_no_violation_invariant(self) -> "ScenarioWorld":
        """Corpus invariant: no scope violation implies no one is at fault.

        If ground_truth.scope_violation is False, the agent stayed inside the
        user's delegated authority, so there is no violation to attribute to
        anyone — causal_category MUST be NO_VIOLATION. Attributing a cause
        (AGENT_ERROR, MERCHANT_INDUCED, AMBIGUOUS_INTENT, SYSTEM_ERROR) to a
        transaction that violated nothing conflates "this outcome may have
        disappointed the user" with "the agent's authority was exceeded", and
        that conflation is exactly what the second-labeler review surfaced as
        the dominant source of author/reviewer disagreement.

        See ARCHITECTURE.md, "Ground-truth invariants".

        The converse is NOT enforced here: scope_violation True with
        causal_category NO_VIOLATION is not rejected by this validator,
        because the corpus contains no such case and the brief did not
        specify it as an invariant.
        """
        gt = self.ground_truth
        if not gt.scope_violation and gt.causal_category is not CausalCategory.NO_VIOLATION:
            raise ValueError(
                f"{self.scenario_id}: ground_truth.scope_violation is False but "
                f"causal_category is {gt.causal_category.value}. When no scope "
                f"violation occurred, causal_category MUST be NO_VIOLATION."
            )
        return self


class ScenarioFactsForReview(BaseModel):
    """
    Scenario facts for the second reviewer in §9.1.

    Structurally absent fields (by design, not by omission):
      - ground_truth: the oracle's verdict — must never reach the reviewer
      - ambiguity_detail: the author's rationale for why the instruction is
        ambiguous — telegraphs the intended answer, so redacted from the
        review view. Remains on ScenarioWorld for internal documentation.
      - corrections: the ground-truth correction log — quotes the superseded
        verdict and the reviewer evidence that replaced it, so it leaks the
        answer twice over. Remains on ScenarioWorld for audit.

    Constructed by explicitly naming each included field — never by
    serializing ScenarioWorld and stripping fields after the fact.
    """
    scenario_id: str
    failure_class: FailureClass
    split: Literal["dev", "holdout"]
    mandate: Mandate
    user_intent: str
    agent_action: AgentAction
    merchant_behavior: MerchantBehavior
    execution_state: ExecutionState
    ambiguous_instruction: bool
    # deliberately no ambiguity_detail — redacted to avoid telegraphing
    # deliberately no ground_truth — structurally absent from the type
    payment_outcome: PaymentOutcome
