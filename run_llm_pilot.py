"""LLM budget-extraction pilot harness (branch: llm-budget-pilot).

Runs the v0.2.0 rule set with ONE function swapped: the regex budget
extractor is replaced by an LLM call. Everything else — mandate, category,
merchant, line-item, fulfilment scope rules, and both causal ladders — is
reused verbatim from faisla/adjudication/deterministic.py, which this script
does not modify.

    python run_llm_pilot.py --cached    # replay recorded completions
    python run_llm_pilot.py --live      # call the provider (Groq)

STATUS: run. The pilot has been run live against openai/gpt-oss-20b on Groq;
the recorded completions are committed in
data/llm_cache/budget_extraction.jsonl and the results in
results/adjudication_llm-budget-pilot-0.1.0.jsonl. --cached replays the cache:
no API key, no network. See PILOT_STATUS.md.

Does NOT touch: main, frozen_v0_1_0.py, or either historical results file.
Writes only results/adjudication_llm-budget-pilot-0.1.0.jsonl.
"""
import argparse
import contextlib
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import faisla.adjudication.deterministic as det
from faisla.adjudication.llm_budget import (
    CACHE_PATH, CachedProvider, LiveProvider, PROMPT_VERSION, RULE_VERSION,
    _SYSTEM, build_prompt, cache_row, input_hash, parse_completion,
)
from faisla.evidence.agent_aware import render_agent_aware
from faisla.evidence.conventional import render_conventional
from faisla.world.generator import load_all_scenario_specs

OUT = Path(f"results/adjudication_{RULE_VERSION}.jsonl")


@contextlib.contextmanager
def budget_extractor(fn):
    """Temporarily swap the ONE function under test.

    Rebinding the module global rather than editing deterministic.py is
    deliberate: it guarantees the v0.2.0 source stays byte-identical, so the
    claim "only the budget extractor changed" is verifiable by diffing the
    file rather than by reading a changelog. Restored unconditionally.
    """
    original = det.extract_instruction_budget
    det.extract_instruction_budget = fn
    try:
        yield
    finally:
        det.extract_instruction_budget = original


def make_resolver(provider, *, live: bool, sink: list):
    """Build the replacement extractor.

    Signature matches the regex it replaces — str -> Decimal | None — so the
    swap is contract-preserving. The extra fields the model needs are closed
    over per scenario by the caller.
    """
    def resolve(text: str) -> Decimal | None:
        ctx = resolve.context
        ihash = input_hash(
            instruction=text, amount=ctx["amount"], currency=ctx["currency"]
        )
        prompt = build_prompt(
            instruction=text, amount=ctx["amount"], currency=ctx["currency"]
        )
        if live:
            raw = provider.complete(prompt, _SYSTEM)
        else:
            raw = provider.lookup(ctx["scenario_id"], ihash)

        parsed = parse_completion(raw)          # raises loudly, never defaults
        sink.append(cache_row(
            scenario_id=ctx["scenario_id"], provider=provider.name,
            model=provider.model, prompt=prompt, ihash=ihash,
            raw=raw, parsed=parsed,
        ))
        return parsed

    resolve.context = {}
    return resolve


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="call a real provider")
    mode.add_argument("--cached", action="store_true", help="replay the cache")
    args = ap.parse_args()

    provider = LiveProvider() if args.live else CachedProvider()
    if args.cached and len(provider) == 0:
        raise SystemExit(
            f"ABORT: cache at {CACHE_PATH} is empty. The pilot has never been "
            f"run against a live model, so there is nothing to replay. Run "
            f"--live with a configured provider first. No numbers are "
            f"available and none will be invented."
        )

    sink: list[dict] = []
    resolve = make_resolver(provider, live=args.live, sink=sink)
    rows = []

    with budget_extractor(resolve):
        for s in load_all_scenario_specs():
            e0 = render_conventional(
                scenario_id=s.scenario_id, cardholder_statement=s.user_intent,
                agent_action=s.agent_action, merchant_behavior=s.merchant_behavior,
                execution_state=s.execution_state, payment_outcome=s.payment_outcome,
            )
            e3 = render_agent_aware(
                scenario_id=s.scenario_id, cardholder_statement=s.user_intent,
                mandate=s.mandate, user_intent=s.user_intent,
                ambiguous_instruction=s.ambiguous_instruction,
                agent_action=s.agent_action, merchant_behavior=s.merchant_behavior,
                execution_state=s.execution_state, payment_outcome=s.payment_outcome,
            )
            # Fields the model may see, set per scenario. The whitelist lives
            # here and in build_prompt(); nothing else reaches the prompt.
            resolve.context = {
                "scenario_id": s.scenario_id,
                "amount": str(e3.transaction.amount),
                "currency": e3.transaction.currency,
            }
            r0, r3 = det.adjudicate(e0), det.adjudicate(e3)
            rows.append({
                "scenario_id": s.scenario_id,
                "split": s.split,
                "failure_class": s.failure_class.value,
                "E0": json.loads(r0.model_dump_json()),
                "E3": json.loads(r3.model_dump_json()),
            })

    for r in rows:                      # stamp the pilot version, not v0.2.0's
        r["E0"]["rule_version"] = RULE_VERSION
        r["E3"]["rule_version"] = RULE_VERSION

    if args.live and sink:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            for row in sink:
                f.write(json.dumps(row) + "\n")
        print(f"cached {len(sink)} completions -> {CACHE_PATH}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"provider={provider.name} model={provider.model} "
          f"prompt={PROMPT_VERSION}")
    print(f"adjudicated {len(rows)} scenarios -> {OUT}")


if __name__ == "__main__":
    main()
