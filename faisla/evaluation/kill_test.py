"""
FAISLA — Kill Test Logic (§13)

Pure function returning CONTINUE, KILL, or INCONCLUSIVE,
computed only from HELD-OUT data plus §9.1 ground-truth-review agreement.

Thresholds are fixed by the brief. Do not adjust them after seeing results.
"""

from __future__ import annotations

from typing import Literal


def evaluate_kill_test(
    *,
    scope_agreement: float,
    causal_agreement: float,
    per_class_scope_agreement: dict[str, float],
    per_class_causal_agreement: dict[str, float],
    held_out_non_dup_count: int,
    flip_count: int,
    reverse_flip_count: int,
    e0_resolves_all: bool,
    flips_are_manufactured: bool,
    flip_rationales_confirmed: bool,
) -> Literal["CONTINUE", "KILL", "INCONCLUSIVE"]:
    """Evaluate the kill/continue/inconclusive verdict.

    Parameters
    ----------
    scope_agreement : float
        Overall §9.1 agreement on scope_violation (0-1).
    causal_agreement : float
        Overall §9.1 agreement on causal_category (0-1).
    per_class_scope_agreement : dict[str, float]
        Per-failure-class scope_violation agreement.
    per_class_causal_agreement : dict[str, float]
        Per-failure-class causal_category agreement.
    held_out_non_dup_count : int
        Number of held-out scenarios excluding DUPLICATE_OR_RETRY_EXECUTION.
    flip_count : int
        Number of held-out non-duplicate scenarios flipping from
        INSUFFICIENT (E0) to SUFFICIENT (E3).
    reverse_flip_count : int
        Scenarios SUFFICIENT under E0 but INSUFFICIENT under E3.
    e0_resolves_all : bool
        True if E0 already resolves nearly all held-out non-duplicate scenarios.
    flips_are_manufactured : bool
        True if flips are traceable only to E0 being artificially weak.
    flip_rationales_confirmed : bool
        True if a human has read all flips and confirmed each has a
        traceable, non-manufactured reason in sufficiency_rationale.
    """

    # --- KILL conditions (any one triggers KILL) ---

    # Check if agreement shortfall is concentrated in AMBIGUOUS_HUMAN_INSTRUCTION
    # If so, route to INCONCLUSIVE rather than KILL per §10 update
    ahi_key = "AMBIGUOUS_HUMAN_INSTRUCTION"
    agreement_below_70 = scope_agreement < 0.70 or causal_agreement < 0.70

    if agreement_below_70:
        # Check if shortfall is concentrated in AHI and all others are >= 80%
        non_ahi_classes = {
            k: v for k, v in per_class_scope_agreement.items() if k != ahi_key
        }
        non_ahi_causal = {
            k: v for k, v in per_class_causal_agreement.items() if k != ahi_key
        }
        all_non_ahi_scope_ok = all(v >= 0.80 for v in non_ahi_classes.values()) if non_ahi_classes else False
        all_non_ahi_causal_ok = all(v >= 0.80 for v in non_ahi_causal.values()) if non_ahi_causal else False

        if all_non_ahi_scope_ok and all_non_ahi_causal_ok:
            # Shortfall is concentrated in AHI — route to INCONCLUSIVE, not KILL
            return "INCONCLUSIVE"
        else:
            return "KILL"

    if e0_resolves_all:
        return "KILL"

    if flip_count == 0:
        return "KILL"

    if flips_are_manufactured:
        return "KILL"

    # --- INCONCLUSIVE conditions ---

    # Agreement between 70-80%
    agreement_in_gray_zone = (
        (0.70 <= scope_agreement < 0.80)
        or (0.70 <= causal_agreement < 0.80)
    )

    if agreement_in_gray_zone:
        # Check if shortfall is concentrated in AHI
        non_ahi_scope = {
            k: v for k, v in per_class_scope_agreement.items() if k != ahi_key
        }
        non_ahi_causal = {
            k: v for k, v in per_class_causal_agreement.items() if k != ahi_key
        }
        all_non_ahi_scope_ok = all(v >= 0.80 for v in non_ahi_scope.values()) if non_ahi_scope else False
        all_non_ahi_causal_ok = all(v >= 0.80 for v in non_ahi_causal.values()) if non_ahi_causal else False

        if all_non_ahi_scope_ok and all_non_ahi_causal_ok:
            # Shortfall concentrated in AHI — INCONCLUSIVE rather than KILL
            return "INCONCLUSIVE"
        else:
            return "INCONCLUSIVE"

    # Flip rate near 20% boundary with mixed rationales
    if held_out_non_dup_count > 0:
        flip_rate = flip_count / held_out_non_dup_count
        if 0.15 <= flip_rate <= 0.25 and not flip_rationales_confirmed:
            return "INCONCLUSIVE"

    # --- CONTINUE requires ALL of ---

    if scope_agreement < 0.80 or causal_agreement < 0.80:
        return "INCONCLUSIVE"

    if held_out_non_dup_count > 0:
        flip_rate = flip_count / held_out_non_dup_count
        if flip_rate < 0.20:
            return "INCONCLUSIVE"

    if not flip_rationales_confirmed:
        return "INCONCLUSIVE"

    if reverse_flip_count > 0:
        # Not an automatic KILL, but needs investigation
        # If reverse flips exist, downgrade to INCONCLUSIVE
        return "INCONCLUSIVE"

    return "CONTINUE"
