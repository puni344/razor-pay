"""DEV-slice calibration audit for the deterministic adjudicator.

Runs the adjudicator over the six DEV scenarios at E0 and E3 and prints the
audit. Contains a hard guard: if any non-DEV scenario reaches the adjudicator
this script aborts rather than printing a result.

No ground truth is loaded, compared, or printed anywhere in this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.generator import load_all_scenario_specs
from faisla.evidence.conventional import render_conventional
from faisla.evidence.agent_aware import render_agent_aware
from faisla.adjudication.deterministic import RULE_VERSION, adjudicate
from faisla.adjudication.schemas import Sufficiency

DEV_ONLY = True


def dev_scenarios():
    scenarios = [s for s in load_all_scenario_specs() if s.split == "dev"]
    # Hard guard — abort rather than silently touching held-out data.
    for s in scenarios:
        if s.split != "dev":
            raise SystemExit(f"HOLDOUT GUARD TRIPPED: {s.scenario_id}")
    return scenarios


def main():
    scenarios = dev_scenarios()
    print(f"rule_version = {RULE_VERSION}  (NOT FROZEN — dev calibration)")
    print(f"DEV slice: {[s.scenario_id for s in scenarios]}")
    print(f"held-out scenarios reaching the adjudicator: 0\n")

    flips = 0
    for s in scenarios:
        e0 = render_conventional(
            scenario_id=s.scenario_id,
            cardholder_statement=s.user_intent,
            agent_action=s.agent_action,
            merchant_behavior=s.merchant_behavior,
            execution_state=s.execution_state,
            payment_outcome=s.payment_outcome,
        )
        e3 = render_agent_aware(
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
        r0, r3 = adjudicate(e0), adjudicate(e3)

        print("=" * 78)
        print(f"{s.scenario_id}")
        for label, r in (("E0", r0), ("E3", r3)):
            causal = r.causal_category.value if r.causal_category else "—"
            print(f"  {label}: scope={r.scope_finding.value:<13} "
                  f"causal={causal:<17} {r.sufficiency.value}")
            for f in r.rules_fired:
                print(f"       [{f.rule_id}]")
                print(f"         {f.observation}")
        if (r0.sufficiency is Sufficiency.INSUFFICIENT
                and r3.sufficiency is Sufficiency.SUFFICIENT):
            flips += 1
            print("  => FLIP  INSUFFICIENT(E0) -> SUFFICIENT(E3)")
        else:
            print("  => no flip")
        print()

    print("=" * 78)
    print(f"DEV flips: {flips}/{len(scenarios)}")
    print("NOTE: dev-slice figure only. Not a kill-test input.")


if __name__ == "__main__":
    main()
