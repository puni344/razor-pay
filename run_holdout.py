"""HELD-OUT EVALUATION — single frozen run at rule_version dev-calibration-0.1.0.

Adjudicates every scenario once at E0 and E3 and writes the raw results to
results/adjudication_<rule_version>.jsonl.

Refuses to overwrite an existing results file for the same rule_version. A
rule change requires a new version string and a new file; the frozen version's
results are preserved.

Ground truth is read ONLY here, after adjudication, for scoring. The
adjudicator never sees it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.generator import load_all_scenario_specs
from faisla.evidence.conventional import render_conventional
from faisla.evidence.agent_aware import render_agent_aware
from faisla.adjudication.deterministic import RULE_VERSION, adjudicate

OUT = Path(f"results/adjudication_{RULE_VERSION}.jsonl")


def main():
    if OUT.exists():
        raise SystemExit(
            f"REFUSING TO OVERWRITE {OUT}. Results for {RULE_VERSION} already "
            f"exist. Bump RULE_VERSION to run again."
        )

    scenarios = load_all_scenario_specs()
    rows = []
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
        rows.append({
            "scenario_id": s.scenario_id,
            "split": s.split,
            "failure_class": s.failure_class.value,
            "E0": json.loads(adjudicate(e0).model_dump_json()),
            "E3": json.loads(adjudicate(e3).model_dump_json()),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"rule_version = {RULE_VERSION} (FROZEN)")
    print(f"adjudicated {len(rows)} scenarios "
          f"({sum(1 for r in rows if r['split']=='holdout')} held-out) -> {OUT}")


if __name__ == "__main__":
    main()
