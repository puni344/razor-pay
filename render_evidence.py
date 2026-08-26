"""Render E0 and E3 evidence packets for all scenarios.

Writes data/evidence/E0.jsonl and data/evidence/E3.jsonl. Deterministic:
re-running against the same specs produces byte-identical output.

This is the only place ScenarioWorld and the renderers meet. The renderers
themselves never see the hidden-world record — they take the observable
sub-records, which is what keeps faisla/evidence/ free of any import path to
the oracle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.generator import load_all_scenario_specs
from faisla.evidence.conventional import render_conventional
from faisla.evidence.agent_aware import render_agent_aware
from faisla.evidence.models import EvidenceCondition

OUT_DIR = Path("data/evidence")


def render_all():
    scenarios = load_all_scenario_specs()
    e0, e3 = [], []
    for s in scenarios:
        e0.append(render_conventional(
            scenario_id=s.scenario_id,
            cardholder_statement=s.user_intent,
            agent_action=s.agent_action,
            merchant_behavior=s.merchant_behavior,
            execution_state=s.execution_state,
            payment_outcome=s.payment_outcome,
        ))
        e3.append(render_agent_aware(
            scenario_id=s.scenario_id,
            cardholder_statement=s.user_intent,
            mandate=s.mandate,
            user_intent=s.user_intent,
            ambiguous_instruction=s.ambiguous_instruction,
            agent_action=s.agent_action,
            merchant_behavior=s.merchant_behavior,
            execution_state=s.execution_state,
            payment_outcome=s.payment_outcome,
        ))
    return scenarios, e0, e3


def main():
    scenarios, e0, e3 = render_all()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for cond, packets in ((EvidenceCondition.E0, e0), (EvidenceCondition.E3, e3)):
        path = OUT_DIR / f"{cond.value}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for p in packets:
                f.write(p.model_dump_json() + "\n")
        print(f"wrote {len(packets)} packets -> {path}")

    # Field-count contrast, as a sanity check on the E0/E3 gap.
    def leaf_count(model):
        import json
        def walk(o):
            if isinstance(o, dict):
                return sum(walk(v) for v in o.values())
            if isinstance(o, list):
                return sum(walk(v) for v in o) or (1 if o else 0)
            return 0 if o is None else 1
        return walk(json.loads(model.model_dump_json()))

    print()
    print(f"{'scenario':<12} | {'class':<38} | {'E0 leaves':>9} | {'E3 leaves':>9}")
    print("-" * 80)
    for s, a, b in zip(scenarios, e0, e3):
        print(f"{s.scenario_id:<12} | {s.failure_class.value:<38} | "
              f"{leaf_count(a):>9} | {leaf_count(b):>9}")

    print()
    print("E0 reason categories (derived from observable facts only):")
    from collections import Counter
    print(" ", Counter(p.claim.reason_category.value for p in e0))


if __name__ == "__main__":
    main()
