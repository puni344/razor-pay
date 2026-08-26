"""
FAISLA — Labeling Schemas

Data models for the second-labeler ground-truth review (§9.1, mandatory)
and the optional evidence-based human baseline (§9.2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from faisla.world.models import CausalCategory


# We import CausalCategory from world.models (the enum definition),
# but NOT GroundTruth or ScenarioWorld — those are forbidden in this layer.


class GroundTruthReview(BaseModel):
    """§9.1 — Second reviewer's independent assessment of ground truth.

    Produced by reviewing ScenarioFactsForReview (no access to ground_truth).
    """
    scenario_id: str
    reviewer_id: str
    scope_violation: bool
    causal_category: CausalCategory
    notes: str


class HumanLabel(BaseModel):
    """§9.2 — Evidence-based human baseline (optional).

    Produced by reviewing E0/E3 EvidencePackets only (blind to hidden world).
    """
    scenario_id: str
    evidence_condition: str  # "E0" or "E3" — not importing EvidenceCondition to keep labeling independent
    labeler_id: str
    in_scope: bool
    causal_category: CausalCategory
    sufficiency: Literal["SUFFICIENT", "INSUFFICIENT"]
    notes: str
