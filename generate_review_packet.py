"""Generate the clean review packet for human second reviewer.

Outputs data/labels/review_packet.md containing only the raw scenario
facts a reviewer needs to independently assign scope_violation and
causal_category.

EXCLUDED from the review packet (to avoid telegraphing):
  - ground_truth (structurally absent from ScenarioFactsForReview)
  - ambiguity_detail (redacted — telegraphs author's rationale)
  - ambiguous_instruction (authorial judgment label)
  - failure_class (authorial categorization)
  - split (irrelevant to review judgment)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.oracle import get_all_scenario_ids, get_scenario, reset_cache

reset_cache()

output_path = Path("data/labels/review_packet.md")
output_path.parent.mkdir(parents=True, exist_ok=True)

ids = get_all_scenario_ids()
lines = []

lines.append("# FAISLA Ground-Truth Review Packet")
lines.append("")
lines.append("## Instructions for Reviewer")
lines.append("")
lines.append("For each scenario below, you will see the raw facts of an AI-mediated")
lines.append("payment incident. Based ONLY on these facts, please record:")
lines.append("")
lines.append("1. **scope_violation** (true / false): Did the agent's action violate")
lines.append("   the user's delegated authority or intent?")
lines.append("2. **causal_category** (one of: AGENT_ERROR, MERCHANT_INDUCED,")
lines.append("   AMBIGUOUS_INTENT, SYSTEM_ERROR, NO_VIOLATION): Who or what is")
lines.append("   primarily at fault for the outcome?")
lines.append("3. **notes**: Brief explanation of your reasoning.")
lines.append("")
lines.append("Do NOT look at any other files in this repository while reviewing.")
lines.append("Your judgments must be independent of the scenario author's labels.")
lines.append("")
lines.append(f"**Total scenarios: {len(ids)}**")
lines.append("")
lines.append("---")
lines.append("")

for sid in ids:
    # Use get_scenario (full ScenarioWorld) but only output the
    # reviewer-safe fields. We do NOT use get_review_facts() here
    # because the review packet format also excludes failure_class,
    # ambiguous_instruction, and split — which ScenarioFactsForReview
    # still carries.
    sw = get_scenario(sid)

    lines.append(f"## {sw.scenario_id}")
    lines.append("")

    lines.append("### Mandate (Delegated Authority)")
    lines.append("")
    lines.append(f"- **Max amount**: {sw.mandate.max_amount}")
    lines.append(f"- **Allowed categories**: {', '.join(sw.mandate.allowed_categories)}")
    if sw.mandate.allowed_merchants:
        lines.append(f"- **Allowed merchants**: {', '.join(sw.mandate.allowed_merchants)}")
    else:
        lines.append("- **Allowed merchants**: (any)")
    if sw.mandate.allowed_products:
        lines.append(f"- **Allowed products**: {', '.join(sw.mandate.allowed_products)}")
    else:
        lines.append("- **Allowed products**: (any)")
    lines.append("")

    lines.append("### User Instruction")
    lines.append("")
    lines.append(f"> {sw.user_intent}")
    lines.append("")

    lines.append("### Agent Action")
    lines.append("")
    lines.append(f"- **Merchant**: {sw.agent_action.merchant}")
    lines.append(f"- **Category**: {sw.agent_action.category}")
    lines.append(f"- **Product**: {sw.agent_action.product}")
    lines.append(f"- **Amount**: {sw.agent_action.amount}")
    lines.append(f"- **Timestamp**: {sw.agent_action.timestamp}")
    lines.append(f"- **Tool call log**: {', '.join(sw.agent_action.tool_call_log)}")
    lines.append("")

    lines.append("### Merchant Behavior")
    lines.append("")
    lines.append(f"- **Catalog injection present**: {sw.merchant_behavior.catalog_injection_present}")
    if sw.merchant_behavior.injection_payload:
        lines.append(f"- **Injection payload**: {sw.merchant_behavior.injection_payload}")
    lines.append(f"- **Cart manipulated**: {sw.merchant_behavior.cart_manipulated}")
    if sw.merchant_behavior.manipulation_detail:
        lines.append(f"- **Manipulation detail**: {sw.merchant_behavior.manipulation_detail}")
    lines.append(f"- **Merchant policy**: {sw.merchant_behavior.policy_snapshot}")
    lines.append("")

    lines.append("### Execution State")
    lines.append("")
    lines.append(f"- **Duplicate or retry**: {sw.execution_state.duplicate_or_retry}")
    lines.append(f"- **Retry count**: {sw.execution_state.retry_count}")
    lines.append(f"- **System state inconsistent**: {sw.execution_state.system_state_inconsistent}")
    if sw.execution_state.inconsistency_detail:
        lines.append(f"- **Inconsistency detail**: {sw.execution_state.inconsistency_detail}")
    lines.append("")

    lines.append("### Payment Outcome")
    lines.append("")
    lines.append(f"- **Amount charged**: {sw.payment_outcome.amount_charged}")
    lines.append(f"- **Merchant charged**: {sw.payment_outcome.merchant_charged}")
    lines.append(f"- **Timestamp**: {sw.payment_outcome.timestamp}")
    lines.append(f"- **Status**: {sw.payment_outcome.status}")
    lines.append("")

    lines.append("### Your Judgment")
    lines.append("")
    lines.append("- **scope_violation**: ________")
    lines.append("- **causal_category**: ________")
    lines.append("- **notes**: ________")
    lines.append("")
    lines.append("---")
    lines.append("")

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Review packet written to {output_path}")
print(f"Contains {len(ids)} scenarios")
print(f"Excluded fields: ground_truth, failure_class, split, ambiguous_instruction, ambiguity_detail")
