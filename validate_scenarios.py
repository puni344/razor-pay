"""Validate all scenario specs against ScenarioWorld model."""
import yaml
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))
from faisla.world.models import ScenarioWorld

specs_dir = project_root / "data" / "scenario_specs"
errors = []
scenarios = []
for f in sorted(specs_dir.glob("SC-*.yaml")):
    try:
        with open(f, encoding='utf-8') as fh:
            data = yaml.safe_load(fh)
        sw = ScenarioWorld(**data)
        scenarios.append({
            "id": sw.scenario_id,
            "failure_class": sw.failure_class.value,
            "split": sw.split,
            "causal_category": sw.ground_truth.causal_category.value,
            "scope_violation": sw.ground_truth.scope_violation,
            "amount_charged": str(sw.payment_outcome.amount_charged),
            "user_intent": sw.user_intent[:70],
        })
    except Exception as e:
        errors.append(f"{f.name}: {e}")

if errors:
    print("ERRORS:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"All {len(scenarios)} scenarios validated successfully.")
    print()
    from collections import Counter
    fc_counts = Counter(s["failure_class"] for s in scenarios)
    split_counts = Counter(s["split"] for s in scenarios)
    print(f"Total: {len(scenarios)} | Dev: {split_counts['dev']} | Holdout: {split_counts['holdout']}")
    print()
    for fc, count in sorted(fc_counts.items()):
        print(f"  {fc}: {count}")
    print()
    print(f"{'ID':12s} | {'Split':7s} | {'Failure Class':50s} | {'Causal':20s} | Scope")
    print("-" * 110)
    for s in scenarios:
        print(f"{s['id']:12s} | {s['split']:7s} | {s['failure_class']:50s} | {s['causal_category']:20s} | {s['scope_violation']}")
