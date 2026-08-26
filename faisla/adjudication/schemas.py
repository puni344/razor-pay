"""
FAISLA — Adjudication Schemas

Output types for the deterministic adjudicator.

The adjudicator consumes an EvidencePacket and nothing else. It has no import
path to the oracle, the hidden-world record, the ground-truth verdict, or the
reviewer labels — enforced by test_no_leakage.py.

Three findings are reported separately and must not be collapsed:

  scope_finding     did the agent stay inside the delegated authority?
  causal_category   if it did not, who is at fault?
  sufficiency       did the evidence actually determine both of the above?

Keeping sufficiency separate is the point of the experiment. An adjudicator
that guesses a plausible causal_category from insufficient evidence looks
identical, on an accuracy metric, to one that reasons from evidence that is
genuinely there. The E0/E3 comparison only means something if "I could not
tell" is a first-class outcome rather than a wrong answer.

CausalCategory is imported from world.models — the enum DEFINITION only, so
that adjudication and scoring speak the same vocabulary. GroundTruth and the
hidden-world record are not imported and must never be. This mirrors what
faisla/labeling/schema.py does for the same reason.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from faisla.evidence.models import EvidenceCondition
from faisla.world.models import CausalCategory


class ScopeFinding(str, Enum):
    """Whether the agent stayed within its delegated authority.

    UNDETERMINED is not a hedge — it is the correct answer when the evidence
    contains no artefact bearing on scope. Under E0 that is the expected
    outcome for most scenarios, because the conventional dispute record has
    no field for delegated authority at all (see E0_ANCHOR.md).
    """
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNDETERMINED = "UNDETERMINED"


class Sufficiency(str, Enum):
    """Whether the packet determined both scope and cause.

    SUFFICIENT requires scope_finding != UNDETERMINED AND causal_category is
    not None. A packet that establishes a violation occurred but not who
    caused it is INSUFFICIENT: half an answer to a liability question is not
    a resolution of it.
    """
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class RuleFiring(BaseModel):
    """One rule that fired, and the observation that triggered it.

    `observation` must state the mechanically observed fact — the field
    compared and the values seen — not a conclusion. This is what makes a
    result auditable: a reader can check the rule fired for the reason it
    claims, rather than trusting the verdict.
    """
    rule_id: str
    observation: str


class AdjudicationResult(BaseModel):
    """The adjudicator's finding for one packet under one condition.

    `rule_version` is stamped on every result so that findings can never be
    compared across rule sets by accident.
    """
    scenario_id: str
    condition: EvidenceCondition
    rule_version: str

    scope_finding: ScopeFinding
    causal_category: CausalCategory | None
    sufficiency: Sufficiency
    sufficiency_rationale: str

    rules_fired: list[RuleFiring]
