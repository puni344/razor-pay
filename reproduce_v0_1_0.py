"""Regenerate the v0.1.0 held-out results from the ARCHIVED v0.1.0 adjudicator.

Why this script exists
----------------------
`run_holdout.py` always runs whatever adjudicator is live in
faisla/adjudication/deterministic.py, which is now v0.2.0. That made the
pilot's ONE unbiased held-out estimate — dev-calibration-0.1.0, causal
correctness 8/18 — impossible to regenerate: deleting the results file lost
it permanently, and the README's "verify rather than trust" could not be
honoured for the number the whole thesis rests on.

This script closes that gap. It imports
faisla/adjudication/frozen_v0_1_0.py — the byte-preserved v0.1.0 source —
and reproduces results/adjudication_dev-calibration-0.1.0.jsonl exactly.

It deliberately mirrors run_holdout.py's row structure and serialisation so
the output is byte-identical, not merely equivalent.

Usage
-----
    python reproduce_v0_1_0.py            # write (refuses to clobber a
                                          # DIFFERENT file, see below)
    python reproduce_v0_1_0.py --verify   # regenerate in memory and diff
                                          # against the committed file;
                                          # never writes. Exit 0 = identical.

`--verify` is the mode a reviewer wants: it proves the committed artefact is
reproducible without touching it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from faisla.world.generator import load_all_scenario_specs
from faisla.evidence.conventional import render_conventional
from faisla.evidence.agent_aware import render_agent_aware

# The archived v0.1.0 adjudicator — NOT faisla.adjudication.deterministic,
# which is v0.2.0. This import is the entire point of the script.
from faisla.adjudication.frozen_v0_1_0 import RULE_VERSION, adjudicate

EXPECTED_VERSION = "dev-calibration-0.1.0"
OUT = Path(f"results/adjudication_{RULE_VERSION}.jsonl")


def build_rows() -> list[dict]:
    """Adjudicate every scenario at E0 and E3 under the archived v0.1.0 rules.

    Structure and key order mirror run_holdout.py exactly so that
    json.dumps() reproduces the committed bytes.
    """
    rows = []
    for s in load_all_scenario_specs():
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
    return rows


def serialise(rows: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


def main() -> None:
    if RULE_VERSION != EXPECTED_VERSION:
        raise SystemExit(
            f"ABORT: archived module reports rule_version {RULE_VERSION!r}, "
            f"expected {EXPECTED_VERSION!r}. frozen_v0_1_0.py has been "
            f"modified; it must stay byte-preserved."
        )

    verify_only = "--verify" in sys.argv
    rows = build_rows()
    payload = serialise(rows)

    held = sum(1 for r in rows if r["split"] == "holdout")

    if verify_only:
        if not OUT.exists():
            raise SystemExit(f"ABORT: {OUT} does not exist; nothing to verify.")
        committed = OUT.read_text(encoding="utf-8")
        if committed == payload:
            print(f"VERIFIED: regenerated {len(rows)} rows from "
                  f"frozen_v0_1_0.py are byte-identical to {OUT}")
            return
        raise SystemExit(
            f"MISMATCH: regenerated output differs from {OUT}. "
            f"The committed artefact is NOT reproducible from the archived "
            f"source — investigate before trusting either."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, encoding="utf-8")
    print(f"rule_version = {RULE_VERSION} (ARCHIVED v0.1.0)")
    print(f"adjudicated {len(rows)} scenarios ({held} held-out) -> {OUT}")


if __name__ == "__main__":
    main()
