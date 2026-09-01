"""
FAISLA — LLM Budget Pilot: harness tests (branch: llm-budget-pilot)

The pilot HAS now been run, against groq/openai/gpt-oss-20b. Nothing here
tests model behaviour even so — model outputs are recorded in the cache and
scored separately, and asserting on them would pin a vendor's weights into the
test suite. What these cover is the machinery around the call, which is where
a pilot most easily fools its author:

  - the parser must fail loudly, because `None` is a MEANINGFUL answer
    ("no budget stated"). Degrading a bad completion to None would score a
    broken model as a legitimate finding.
  - the prompt must not carry the label. A whitelist is only a whitelist if
    something checks it.
  - the cache must reject stale entries, or a prompt edit silently replays
    answers to a different question.
  - the swap must restore the original function, or the v0.2.0 rules stay
    monkeypatched for the rest of the process.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from faisla.adjudication import deterministic as det
from faisla.adjudication.llm_budget import (
    BudgetParseError, LiveProvider, RULE_VERSION,
    build_prompt, input_hash, parse_completion,
)


class TestParserAcceptsValidShapes:
    @pytest.mark.parametrize("raw,expected", [
        ('{"budget_stated": true, "budget_amount": 500}', Decimal("500")),
        ('{"budget_stated": false, "budget_amount": null}', None),
        ('  {"budget_stated": true, "budget_amount": 4000}  ', Decimal("4000")),
        ('```json\n{"budget_stated": true, "budget_amount": 2999}\n```', Decimal("2999")),
        ('Here you go: {"budget_stated": false, "budget_amount": null} done',  None),
        ('{"budget_stated": true, "budget_amount": 1500.50}', Decimal("1500.50")),
    ])
    def test_valid(self, raw, expected):
        assert parse_completion(raw) == expected


class TestParserFailsLoudly:
    """Every one of these would otherwise be silently readable as `None`."""

    @pytest.mark.parametrize("raw", [
        "",                                              # empty completion
        "I cannot determine the budget.",                # prose, no JSON
        "{not json at all}",                             # malformed
        '{"budget_amount": 500}',                        # missing the flag
        '{"budget_stated": "yes", "budget_amount": 500}',  # flag not a bool
        '{"budget_stated": true}',                       # claims one, gives none
        '{"budget_stated": true, "budget_amount": null}',  # contradictory
        '{"budget_stated": false, "budget_amount": 500}',  # contradictory
        '{"budget_stated": true, "budget_amount": "cheap"}',  # non-numeric
        '{"budget_stated": true, "budget_amount": -100}',  # nonsensical
        '{"budget_stated": true, "budget_amount": 0}',    # nonsensical
        '["budget_stated"]',                             # wrong container
    ])
    def test_raises(self, raw):
        with pytest.raises(BudgetParseError):
            parse_completion(raw)

    def test_none_is_a_real_answer_not_an_error_path(self):
        """The distinction the whole parser exists to preserve."""
        assert parse_completion('{"budget_stated": false, "budget_amount": null}') is None
        with pytest.raises(BudgetParseError):
            parse_completion("I don't know")


class TestPromptCarriesNoLabel:
    """The model must not be able to read the answer off its own prompt."""

    def _prompt(self):
        return build_prompt(
            instruction="Buy a basic USB-C charging cable under 500 rupees",
            amount="2499", currency="INR",
        )

    @pytest.mark.parametrize("forbidden", [
        "SC-MPI", "SC-AHI", "SC-AIE", "SC-MCM", "SC-DRE", "SC-SSI",
        "failure_class", "MERCHANT_PROMPT_OR_CATALOG_INJECTION",
        "scope_violation", "causal_category", "ground_truth",
        "AGENT_ERROR", "MERCHANT_INDUCED", "SYSTEM_ERROR", "NO_VIOLATION",
        "AMBIGUOUS_INTENT", "OUT_OF_SCOPE", "IN_SCOPE",
        "cart_manipulated", "catalog_injection_present",
        "system_state_inconsistent", "duplicate_or_retry",
        "mandate", "max_amount", "allowed_categories", "reviewer",
    ])
    def test_absent(self, forbidden):
        assert forbidden not in self._prompt()

    def test_carries_exactly_the_three_whitelisted_inputs(self):
        p = self._prompt()
        assert "Buy a basic USB-C charging cable under 500 rupees" in p
        assert "2499" in p
        assert "INR" in p

    def test_instructs_against_price_priors(self):
        """The one guard against world-knowledge leakage that lives in text."""
        p = self._prompt().lower()
        assert "do not infer" in p or "never estimate" in p


class TestCacheKeying:
    def test_hash_changes_with_each_input(self):
        base = dict(instruction="buy a cable", amount="2499", currency="INR")
        h = input_hash(**base)
        assert h != input_hash(**{**base, "instruction": "buy a cable under 500"})
        assert h != input_hash(**{**base, "amount": "2500"})
        assert h != input_hash(**{**base, "currency": "USD"})

    def test_hash_is_stable(self):
        base = dict(instruction="buy a cable", amount="2499", currency="INR")
        assert input_hash(**base) == input_hash(**base)

    def test_prompt_version_is_recorded_in_the_hash(self):
        """A prompt edit must invalidate the cache, not silently reuse it."""
        import faisla.adjudication.llm_budget as m
        base = dict(instruction="buy a cable", amount="2499", currency="INR")
        before = input_hash(**base)
        original = m.PROMPT_VERSION
        try:
            m.PROMPT_VERSION = "budget-v2"
            assert input_hash(**base) != before
        finally:
            m.PROMPT_VERSION = original


class TestNoFabricatedResults:
    """Guards that the pilot's numbers came from a real model.

    These previously asserted the scaffold state — that LiveProvider raised
    NotImplementedError and that no results file existed. The live Groq run
    retired both. They are replaced, not deleted: the intent was never "no run
    has happened", it was "no number is fabricated", and that still needs
    enforcing now that numbers exist.
    """

    def test_live_provider_refuses_rather_than_inventing_a_key(self):
        """No key must fail loudly, never fall back to a canned completion."""
        import os
        saved = os.environ.pop("GROQ_API_KEY", None)
        try:
            with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
                LiveProvider()
        finally:
            if saved is not None:
                os.environ["GROQ_API_KEY"] = saved

    def test_pilot_version_is_distinct_from_shipped_versions(self):
        assert RULE_VERSION == "llm-budget-pilot-0.1.0"
        assert RULE_VERSION != det.RULE_VERSION

    def test_results_came_from_a_named_real_provider(self):
        """A results file may exist now — but only from an attributable run."""
        p = _PROJECT_ROOT / "results" / f"adjudication_{RULE_VERSION}.jsonl"
        if not p.exists():
            pytest.skip("no pilot run recorded yet")
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(rows) == 24
        for r in rows:
            assert r["E3"]["rule_version"] == RULE_VERSION, r["scenario_id"]

        cache = _PROJECT_ROOT / "data" / "llm_cache" / "budget_extraction.jsonl"
        assert cache.exists(), (
            "results exist with no cache behind them — the numbers cannot be "
            "traced to model outputs and must not be trusted"
        )
        crows = [json.loads(l) for l in cache.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(crows) == 24
        for c in crows:
            # The scaffold's placeholder sentinels must never reach an artefact.
            assert c["provider"] not in ("UNCONFIGURED", "EMPTY_CACHE"), c["scenario_id"]
            assert c["model"] not in ("UNCONFIGURED", "EMPTY_CACHE"), c["scenario_id"]
            assert c["raw_output"].strip(), c["scenario_id"]

    def test_cache_carries_no_credential_material(self):
        """The cache is a committed artefact; a key must never reach it."""
        cache = _PROJECT_ROOT / "data" / "llm_cache" / "budget_extraction.jsonl"
        if not cache.exists():
            pytest.skip("no cache recorded yet")
        text = cache.read_text(encoding="utf-8")
        for needle in ("gsk_", "Bearer ", "Authorization", "api_key", "GROQ_API_KEY"):
            assert needle not in text, f"cache contains {needle!r}"

    def test_repr_does_not_leak_the_key(self):
        import os
        saved = os.environ.get("GROQ_API_KEY")
        os.environ["GROQ_API_KEY"] = "gsk_SENTINEL_must_not_appear"
        try:
            assert "SENTINEL" not in repr(LiveProvider())
        finally:
            if saved is None:
                os.environ.pop("GROQ_API_KEY", None)
            else:
                os.environ["GROQ_API_KEY"] = saved


class TestSwapIsContained:
    """The v0.2.0 rules must not stay monkeypatched after the pilot runs."""

    def test_context_manager_restores_the_original(self):
        from run_llm_pilot import budget_extractor
        original = det.extract_instruction_budget
        with budget_extractor(lambda t: Decimal("1")):
            assert det.extract_instruction_budget is not original
        assert det.extract_instruction_budget is original

    def test_restores_even_when_the_body_raises(self):
        from run_llm_pilot import budget_extractor
        original = det.extract_instruction_budget
        with pytest.raises(RuntimeError):
            with budget_extractor(lambda t: Decimal("1")):
                raise RuntimeError("boom")
        assert det.extract_instruction_budget is original

    def test_replacement_matches_the_regex_contract(self):
        """Same signature in, same type out — the swap is contract-preserving."""
        import inspect
        sig = inspect.signature(det.extract_instruction_budget)
        assert len(sig.parameters) == 1
        assert det.extract_instruction_budget("under 500 rupees") == Decimal("500")
        assert det.extract_instruction_budget("no limit mentioned") is None
