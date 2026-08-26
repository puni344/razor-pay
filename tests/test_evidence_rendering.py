"""
FAISLA — Evidence Rendering Tests

Two things must hold for the E0/E3 comparison to mean anything:

1. **E0 must not be secretly strong.** Agent-aware content leaking into the
   baseline suppresses flips and reads as a sound negative result. §13 cannot
   detect this — `flips_are_manufactured` catches an E0 that is too weak, not
   one that is too strong. So it is enforced here, by scanning rendered E0
   values rather than trusting the renderer.

2. **E3 must be E0-plus, exactly.** If the shared fields drifted between
   conditions, a flip could be caused by the conventional part being rendered
   differently rather than by the added record.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.evidence.agent_aware import render_agent_aware
from faisla.evidence.conventional import derive_reason_category, render_conventional
from faisla.evidence.models import (
    AgentAwareEvidencePacket,
    ConventionalEvidencePacket,
    DisputeReasonCategory,
    EvidenceCondition,
)
from faisla.world.generator import load_all_scenario_specs


@pytest.fixture(scope="module")
def scenarios():
    return load_all_scenario_specs()


def _e0(s) -> ConventionalEvidencePacket:
    return render_conventional(
        scenario_id=s.scenario_id,
        cardholder_statement=s.user_intent,
        agent_action=s.agent_action,
        merchant_behavior=s.merchant_behavior,
        execution_state=s.execution_state,
        payment_outcome=s.payment_outcome,
    )


def _e3(s) -> AgentAwareEvidencePacket:
    return render_agent_aware(
        scenario_id=s.scenario_id,
        cardholder_statement=s.user_intent,
        mandate=s.mandate,
        user_intent=s.user_intent,
        ambiguous_instruction=s.ambiguous_instruction,
        agent_action=s.agent_action,
        merchant_behavior=s.merchant_behavior,
        execution_state=s.execution_state,
        payment_outcome=s.payment_outcome,
    )


class TestE0IsNotSecretlyStrong:
    """The baseline must contain no agent-aware content, checked by value."""

    def test_e0_never_carries_agent_context(self, scenarios):
        """Not 'is None' — the attribute must not exist on the instance at all."""
        for s in scenarios:
            packet = _e0(s)
            assert not hasattr(packet, "agent_context"), s.scenario_id
            assert "agent_context" not in packet.model_dump(), s.scenario_id

    def test_e0_serialization_contains_no_injection_payload(self, scenarios):
        for s in scenarios:
            payload = s.merchant_behavior.injection_payload
            if not payload:
                continue
            blob = _e0(s).model_dump_json()
            assert payload not in blob, (
                f"{s.scenario_id}: E0 leaked the injection payload"
            )

    def test_e0_serialization_contains_no_manipulation_or_inconsistency_detail(self, scenarios):
        for s in scenarios:
            blob = _e0(s).model_dump_json()
            for label, detail in (
                ("manipulation_detail", s.merchant_behavior.manipulation_detail),
                ("inconsistency_detail", s.execution_state.inconsistency_detail),
            ):
                if detail:
                    assert detail not in blob, f"{s.scenario_id}: E0 leaked {label}"

    def test_e0_serialization_contains_no_tool_call_log(self, scenarios):
        for s in scenarios:
            blob = _e0(s).model_dump_json()
            for call in s.agent_action.tool_call_log:
                assert call not in blob, (
                    f"{s.scenario_id}: E0 leaked tool call {call!r}"
                )

    def test_e0_type_has_no_agent_aware_field(self):
        """The E0 TYPE must lack every agent-aware field — not hold them as None."""
        fields = set(ConventionalEvidencePacket.model_fields)
        for forbidden in (
            "agent_context", "original_delegated_intent", "mandate_constraints",
            "agent_tool_action_trace", "merchant_content_presented",
            "execution_provenance_summary", "injection_payload",
            "manipulation_detail", "mandate", "tool_call_log", "user_intent",
            "logged_instruction", "allowed_categories",
        ):
            assert forbidden not in fields, (
                f"ConventionalEvidencePacket has a {forbidden!r} field"
            )
            assert not hasattr(ConventionalEvidencePacket, forbidden)

    def test_e0_claim_is_never_corroborated(self, scenarios):
        for s in scenarios:
            assert _e0(s).claim.corroborated is False, s.scenario_id


class TestE0CannotStructurallyHoldAgentFields:
    """An E0 packet cannot be CONSTRUCTED with E3-only fields.

    Not "is rejected by a validator" — the fields do not exist on the type,
    and extra keys are forbidden, so construction fails in the type system.
    """

    @pytest.mark.parametrize("field_name", [
        "agent_context",
        "original_delegated_intent",
        "mandate_constraints",
        "agent_tool_action_trace",
        "merchant_content_presented",
        "execution_provenance_summary",
        "injection_payload",
        "manipulation_detail",
    ])
    def test_construction_with_agent_aware_field_raises(self, scenarios, field_name):
        s = scenarios[0]
        base, full = _e0(s), _e3(s)
        kwargs = dict(
            scenario_id=s.scenario_id,
            claim=base.claim,
            transaction=base.transaction,
            merchant_evidence=base.merchant_evidence,
        )
        kwargs[field_name] = full.agent_context

        with pytest.raises(ValidationError) as exc:
            ConventionalEvidencePacket(**kwargs)
        assert "extra_forbidden" in str(exc.value) or field_name in str(exc.value)

    def test_agent_aware_field_is_not_silently_dropped(self, scenarios):
        """The dangerous failure would be pydantic ignoring the extra key."""
        s = scenarios[0]
        base, full = _e0(s), _e3(s)
        with pytest.raises(ValidationError):
            ConventionalEvidencePacket(
                scenario_id=s.scenario_id,
                claim=base.claim,
                transaction=base.transaction,
                merchant_evidence=base.merchant_evidence,
                agent_context=full.agent_context,
            )

    def test_e0_cannot_be_relabelled_as_e3(self, scenarios):
        """condition is pinned by Literal — an E0 type cannot claim to be E3."""
        s = scenarios[0]
        base = _e0(s)
        with pytest.raises(ValidationError):
            ConventionalEvidencePacket(
                scenario_id=s.scenario_id,
                condition=EvidenceCondition.E3,
                claim=base.claim,
                transaction=base.transaction,
                merchant_evidence=base.merchant_evidence,
            )

    def test_e3_requires_agent_context(self, scenarios):
        """E3 without the delegated-authority record is just E0 mislabelled."""
        s = scenarios[0]
        base = _e0(s)
        with pytest.raises(ValidationError):
            AgentAwareEvidencePacket(
                scenario_id=s.scenario_id,
                claim=base.claim,
                transaction=base.transaction,
                merchant_evidence=base.merchant_evidence,
            )


class TestRuntimeInvariantsRetained:
    """Defence-in-depth: the runtime validators still fire."""

    def test_e0_with_corroborated_claim_still_raises(self, scenarios):
        s = scenarios[0]
        base, full = _e0(s), _e3(s)
        with pytest.raises(ValueError, match="marked corroborated"):
            ConventionalEvidencePacket(
                scenario_id=s.scenario_id,
                claim=full.claim,          # corroborated=True
                transaction=base.transaction,
                merchant_evidence=base.merchant_evidence,
            )


class TestE3IsE0Plus:
    """The conventional part must be byte-identical across conditions."""

    def test_transaction_record_identical(self, scenarios):
        for s in scenarios:
            assert _e0(s).transaction == _e3(s).transaction, s.scenario_id

    def test_merchant_evidence_identical(self, scenarios):
        for s in scenarios:
            assert _e0(s).merchant_evidence == _e3(s).merchant_evidence, s.scenario_id

    def test_claim_differs_only_in_evidentiary_status(self, scenarios):
        for s in scenarios:
            e0, e3 = _e0(s).claim, _e3(s).claim
            assert e0.statement == e3.statement, s.scenario_id
            assert e0.reason_category == e3.reason_category, s.scenario_id
            assert e0.corroborated is False and e3.corroborated is True
            assert e0.provenance != e3.provenance

    def test_e3_carries_the_delegated_authority_record(self, scenarios):
        for s in scenarios:
            ctx = _e3(s).agent_context
            assert ctx is not None
            assert ctx.mandate.max_amount == s.mandate.max_amount
            assert ctx.tool_call_log == s.agent_action.tool_call_log
            assert ctx.logged_instruction == s.user_intent


class TestRendersWholeCorpus:
    def test_all_24_render_at_both_conditions(self, scenarios):
        assert len(scenarios) == 24
        for s in scenarios:
            assert _e0(s).condition is EvidenceCondition.E0
            assert _e3(s).condition is EvidenceCondition.E3

    def test_rendering_is_deterministic(self, scenarios):
        for s in scenarios:
            assert _e0(s).model_dump_json() == _e0(s).model_dump_json()
            assert _e3(s).model_dump_json() == _e3(s).model_dump_json()


class TestReasonCategoryDerivation:
    """Derived from observable facts only — never from the oracle's verdict."""

    def test_duplicate_when_retry_and_overcharge(self):
        from decimal import Decimal
        assert derive_reason_category(
            amount_charged=Decimal("2998"),
            unit_price=Decimal("1499"),
            duplicate_or_retry=True,
        ) is DisputeReasonCategory.DUPLICATE

    def test_not_duplicate_without_overcharge(self):
        from decimal import Decimal
        assert derive_reason_category(
            amount_charged=Decimal("1499"),
            unit_price=Decimal("1499"),
            duplicate_or_retry=True,
        ) is DisputeReasonCategory.PRODUCT_UNACCEPTABLE

    def test_fraudulent_is_never_derived(self, scenarios):
        """Under the anchor's own test, an agent under mandate is an
        authorised representative — so nothing here is conventionally fraud."""
        for s in scenarios:
            assert _e0(s).claim.reason_category is not DisputeReasonCategory.FRAUDULENT

    def test_duplicate_explanation_only_when_overcharged(self, scenarios):
        for s in scenarios:
            packet = _e0(s)
            explanation = packet.merchant_evidence.duplicate_charge_explanation
            overcharged = s.payment_outcome.amount_charged > s.agent_action.amount
            assert (explanation is not None) == overcharged, s.scenario_id
