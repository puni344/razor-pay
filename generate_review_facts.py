"""Generate ScenarioFactsForReview for all scenarios and output for human review.

This script outputs the review facts in a human-readable format so the
second reviewer can independently assign scope_violation and causal_category.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_review_facts, get_all_scenario_ids, reset_cache
from faisla.world.generator import load_all_scenario_specs

# Force loading from specs
reset_cache()

scenario_ids = get_all_scenario_ids()
print(f"Generating review facts for {len(scenario_ids)} scenarios\n")

for sid in scenario_ids:
    facts = get_review_facts(sid)
    print(f"{'='*80}")
    print(f"SCENARIO: {facts.scenario_id}")
    print(f"Failure Class: {facts.failure_class.value}")
    print(f"Split: {facts.split}")
    print(f"\nMANDATE:")
    print(f"  Max amount: {facts.mandate.max_amount}")
    print(f"  Allowed categories: {facts.mandate.allowed_categories}")
    print(f"  Allowed merchants: {facts.mandate.allowed_merchants}")
    print(f"  Allowed products: {facts.mandate.allowed_products}")
    print(f"\nUSER INTENT: {facts.user_intent}")
    print(f"\nAGENT ACTION:")
    print(f"  Merchant: {facts.agent_action.merchant}")
    print(f"  Category: {facts.agent_action.category}")
    print(f"  Product: {facts.agent_action.product}")
    print(f"  Amount: {facts.agent_action.amount}")
    print(f"  Tool call log: {facts.agent_action.tool_call_log}")
    print(f"\nMERCHANT BEHAVIOR:")
    print(f"  Injection present: {facts.merchant_behavior.catalog_injection_present}")
    if facts.merchant_behavior.injection_payload:
        print(f"  Injection payload: {facts.merchant_behavior.injection_payload}")
    print(f"  Cart manipulated: {facts.merchant_behavior.cart_manipulated}")
    if facts.merchant_behavior.manipulation_detail:
        print(f"  Manipulation detail: {facts.merchant_behavior.manipulation_detail}")
    print(f"  Policy: {facts.merchant_behavior.policy_snapshot}")
    print(f"\nEXECUTION STATE:")
    print(f"  Duplicate/retry: {facts.execution_state.duplicate_or_retry}")
    print(f"  Retry count: {facts.execution_state.retry_count}")
    print(f"  System inconsistent: {facts.execution_state.system_state_inconsistent}")
    if facts.execution_state.inconsistency_detail:
        print(f"  Inconsistency detail: {facts.execution_state.inconsistency_detail}")
    print(f"\nAMBIGUOUS INSTRUCTION: {facts.ambiguous_instruction}")
    if facts.ambiguity_detail:
        print(f"  Detail: {facts.ambiguity_detail}")
    print(f"\nPAYMENT OUTCOME:")
    print(f"  Amount charged: {facts.payment_outcome.amount_charged}")
    print(f"  Merchant charged: {facts.payment_outcome.merchant_charged}")
    print(f"  Status: {facts.payment_outcome.status}")
    print()
