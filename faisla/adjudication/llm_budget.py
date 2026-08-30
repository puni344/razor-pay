"""
FAISLA — LLM Budget-Extraction Pilot (branch: llm-budget-pilot)

SCOPE: replaces exactly ONE function —
`faisla.adjudication.deterministic.extract_instruction_budget` — with a single
LLM call. Nothing else changes. The mandate, category, merchant, line-item and
fulfilment scope rules, and both causal ladders, are untouched and are reused
verbatim from the v0.2.0 module.

WHY THIS FUNCTION: the held-out error analysis put the accuracy ceiling at
scope resolution, and within scope resolution the budget comparison is the
only step that reads natural language. Everything else is a field comparison
where an LLM could add nothing. If a language model helps anywhere in this
adjudicator, it helps here; if it does not help here, it does not help.

STATUS: RUN. `LiveProvider.complete()` is implemented against Groq's
OpenAI-compatible chat/completions endpoint over plain stdlib HTTPS -- no
vendor SDK, so requirements.txt is unchanged at four packages and the scoring
path still carries no third-party network client.

MODEL: openai/gpt-oss-20b, substituted for the specified llama-3.1-8b-instant,
which Groq has retired. See the note on LiveProvider.MODEL.

DETERMINISM, HONESTLY: the request pins temperature=0 and seed=42. Groq
documents seed as best-effort and does NOT guarantee bit-identical output
across calls; shared-batch scheduling and kernel selection can vary. The seed
is a variance reducer, not a reproducibility mechanism. The cache below is the
reproducibility mechanism: once recorded, a --cached run replays the exact
bytes the model returned, with no network and no provider, and is reproducible
in the same sense the regex was.

REPRODUCIBILITY CONTRACT
------------------------
Every call is cached to data/llm_cache/budget_extraction.jsonl keyed by
scenario_id, recording provider, model, prompt_version, input hash, the raw
completion and the parsed value. A cached run needs no provider and no
network, which is the substitute for the determinism the regex had for free.
The input hash makes a stale cache detectable: if the prompt or the inputs
change, the hash changes and the entry no longer matches.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = _PROJECT_ROOT / "data" / "llm_cache" / "budget_extraction.jsonl"

# Bumped whenever the prompt text changes. Cached entries carry the version
# they were produced under, so a prompt edit invalidates them visibly rather
# than silently reusing answers to a different question.
PROMPT_VERSION = "budget-v1"

RULE_VERSION = "llm-budget-pilot-0.1.0"


# ---------------------------------------------------------------------------
# Prompt construction — whitelist, never strip-a-dict
# ---------------------------------------------------------------------------
# The model receives the full delegated instruction, not the substring the
# regex happened to consume, so this tests semantic interpretation rather than
# reproducing the regex's blind spots.
#
# Deliberately WITHHELD, and the whitelist is why they cannot leak by accident:
#   scenario_id            — encodes the failure class (SC-MPI-*, SC-AHI-*)
#   failure_class          — the label under test
#   ground_truth           — scope_violation and causal_category
#   agent_context flags    — cart_manipulated, catalog_injection_present,
#                            system_state_inconsistent, duplicate_or_retry
#   mandate                — the authority record; a separate rule's input
#   adjudicator output     — any prior verdict
#   reviewer labels        — §9.1 judgments

_SYSTEM = (
    "You extract explicit spending limits from purchase instructions. "
    "You report only what the instruction states. You never estimate what a "
    "reasonable price would be, and you never use knowledge of typical market "
    "prices. If the instruction does not state a limit, there is no limit to "
    "report, however unusual the amount charged may seem."
)

_TEMPLATE = """A principal gave an agent this purchase instruction:

<instruction>
{instruction}
</instruction>

The agent was charged {amount} {currency}.

Did the instruction state an explicit spending limit?

Answer with JSON only, no other text:
{{"budget_stated": true or false, "budget_amount": <number or null>}}

Rules:
- budget_stated is true ONLY if the instruction names a price ceiling or a
  specific price the principal expected.
- If a range is stated, budget_amount is the UPPER bound.
- If no limit is stated, return {{"budget_stated": false, "budget_amount": null}}.
- Do NOT infer a limit from what the item ought to cost."""


def build_prompt(*, instruction: str, amount: str, currency: str) -> str:
    """Render the prompt from the three whitelisted fields."""
    return _TEMPLATE.format(instruction=instruction, amount=amount, currency=currency)


def input_hash(*, instruction: str, amount: str, currency: str) -> str:
    """Stable hash of the exact model inputs plus prompt version.

    Changing the prompt or any input changes this, so a cache entry can never
    be silently reused for a different question.
    """
    payload = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "instruction": instruction,
            "amount": amount,
            "currency": currency,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Strict parser — fails loudly, never silently defaults
# ---------------------------------------------------------------------------

class BudgetParseError(ValueError):
    """Raised when a completion cannot be parsed into the regex's contract.

    Deliberately NOT caught anywhere. `None` is a meaningful answer here — it
    means "no budget was stated" — so degrading a parse failure to None would
    disguise a broken model as a legitimate finding, and the pilot would score
    its own malfunction as evidence.
    """


def parse_completion(raw: str) -> Decimal | None:
    """Parse a completion into the same contract the regex returns.

    Returns Decimal for a stated budget, None for "no budget stated".
    Raises BudgetParseError on anything else.
    """
    text = raw.strip()
    if text.startswith("```"):                      # strip fenced blocks
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.removeprefix("json").strip()

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise BudgetParseError(f"no JSON object found in completion: {raw!r}")

    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise BudgetParseError(f"completion is not valid JSON ({exc}): {raw!r}") from exc

    if not isinstance(obj, dict):
        raise BudgetParseError(f"expected a JSON object, got {type(obj).__name__}")

    if "budget_stated" not in obj:
        raise BudgetParseError(f"missing 'budget_stated' key: {obj!r}")
    stated = obj["budget_stated"]
    if not isinstance(stated, bool):
        raise BudgetParseError(f"'budget_stated' must be a bool, got {stated!r}")

    if not stated:
        # A stated budget of None is coherent; a value alongside false is not.
        if obj.get("budget_amount") not in (None, "", "null"):
            raise BudgetParseError(
                f"budget_stated=false but budget_amount={obj.get('budget_amount')!r}"
            )
        return None

    if "budget_amount" not in obj:
        raise BudgetParseError(f"budget_stated=true but no 'budget_amount': {obj!r}")
    amount = obj["budget_amount"]
    if amount is None:
        raise BudgetParseError("budget_stated=true but budget_amount is null")
    if isinstance(amount, bool):
        raise BudgetParseError(f"budget_amount must be numeric, got bool {amount!r}")
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise BudgetParseError(f"budget_amount not numeric: {amount!r}") from exc
    if value <= 0:
        raise BudgetParseError(f"budget_amount must be positive, got {value}")
    return value


# ---------------------------------------------------------------------------
# Provider boundary — the one place a real model plugs in
# ---------------------------------------------------------------------------

class Provider(Protocol):
    name: str
    model: str

    def complete(self, prompt: str, system: str) -> str:
        """Return the raw completion. Deterministic settings are the caller's
        responsibility: temperature=0 and a fixed seed where supported."""


class LiveProvider:
    """THE SINGLE CALL BOUNDARY: Groq's OpenAI-compatible chat/completions API.

    Plain stdlib HTTPS. A vendor SDK would add a dependency to a repository
    whose entire scoring path is currently pure stdlib + pydantic, to save
    about fifteen lines.

    The API key is read from GROQ_API_KEY at construction, so a missing key
    fails before any scenario is touched rather than midway through a run that
    has already spent calls. It is held in a private attribute, never written
    to the cache, never printed, and never placed in an exception message --
    `cache_row()` has no parameter that could carry it, and `__repr__` is
    overridden so an incidental repr of this object in a traceback cannot leak
    it either.
    """

    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

    # MODEL SUBSTITUTION, ON THE RECORD: this pilot was specified against
    # llama-3.1-8b-instant. That model has been retired from Groq's catalogue
    # -- GET /openai/v1/models returns 14 models and it is not among them, and
    # a request for it returns 404 model_not_found, not a permissions error.
    # openai/gpt-oss-20b is the nearest available substitute: the smallest
    # general-purpose instruct model on the platform, matching the original
    # intent (a small, fast model for a pilot, not a frontier-model benchmark).
    # Every cache row records the model actually called, so this substitution
    # is auditable from the artefacts rather than only from this comment.
    MODEL = "openai/gpt-oss-20b"

    # Pinned for variance reduction only -- see DETERMINISM, HONESTLY above.
    # Groq treats seed as best-effort; it is not a determinism guarantee, and
    # nothing in this pilot's reproducibility claim rests on it.
    TEMPERATURE = 0
    SEED = 42
    # gpt-oss is a reasoning model: its internal reasoning tokens are billed
    # against max_tokens even though only `message.content` is returned as the
    # answer. Live runs tripped the truncation guard below on SC-MCM-002
    # ("I saw it listed at 2999" -- reference price, or expected ceiling?): at
    # 1024 the model degenerated into verbatim repetition of "That is a price.
    # The instruction might be interpreted as..." and never emitted an answer.
    # At 2048 it terminates and returns 2999, agreeing with the regex, at a
    # visibly higher cost than any other scenario.
    #
    # No token figure is quoted here: the cache records raw_output and the
    # parsed value only -- no usage, no finish_reason -- so per-call cost is
    # not reproducible from any committed artefact. See PILOT_STATUS.md.
    #
    # 4096 is headroom over the worst case observed, not a fix for it. The
    # instability is a finding about the approach, and the guard stays as the
    # backstop that makes it visible instead of silent.
    MAX_TOKENS = 4096

    # urllib's default User-Agent ("Python-urllib/3.10") is rejected by Groq's
    # edge WAF with Cloudflare error 1010 before the request ever reaches the
    # API. Every vendor SDK sets a client UA; this one names the actual client
    # rather than impersonating a browser or another tool.
    USER_AGENT = "faisla-pilot/0.1.0 (+https://github.com/puni344/razor-pay)"

    def __init__(
        self,
        name: str = "groq",
        model: str = MODEL,
        *,
        endpoint: str = ENDPOINT,
        timeout: float = 60.0,
        max_retries: int = 4,
    ):
        self.name = name
        self.model = model
        self._endpoint = endpoint
        self._timeout = timeout
        self._max_retries = max_retries

        key = os.environ.get("GROQ_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. The live pilot needs a Groq API key "
                "in the environment:\n\n"
                "    export GROQ_API_KEY=...        # bash\n"
                "    $env:GROQ_API_KEY = '...'      # PowerShell\n\n"
                "Get a free key at https://console.groq.com. Do not hardcode "
                "it in this file or in any committed artefact. Use --cached "
                "to replay an existing run without a key."
            )
        self._api_key = key

    def __repr__(self) -> str:
        """Never the default repr -- that would risk the key in a traceback."""
        return f"LiveProvider(name={self.name!r}, model={self.model!r})"

    def complete(self, prompt: str, system: str) -> str:
        body = json.dumps({
            "model": self.model,
            "temperature": self.TEMPERATURE,
            "seed": self.SEED,
            "max_tokens": self.MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }).encode("utf-8")

        last_error = None
        for attempt in range(self._max_retries):
            request = urllib.request.Request(self._endpoint, data=body, method="POST")
            request.add_header("Content-Type", "application/json")
            request.add_header("User-Agent", self.USER_AGENT)
            request.add_header("Authorization", f"Bearer {self._api_key}")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._extract(payload)
            except urllib.error.HTTPError as exc:
                # exc carries Groq's error body, which never echoes the request
                # headers, so it cannot contain the key. Read it for the
                # message; never log the request object itself.
                detail = exc.read().decode("utf-8", errors="replace")[:400]
                if exc.code in (429, 500, 502, 503, 529) and attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)
                    last_error = f"HTTP {exc.code}: {detail}"
                    continue
                raise RuntimeError(
                    f"Groq request failed with HTTP {exc.code}: {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)
                    last_error = f"network error: {exc.reason}"
                    continue
                raise RuntimeError(f"Groq unreachable: {exc.reason}") from exc

        raise RuntimeError(
            f"Groq request failed after {self._max_retries} attempts: {last_error}"
        )

    @staticmethod
    def _extract(payload: dict) -> str:
        """Pull the completion text out, refusing to invent one.

        A truncated or empty completion raises here rather than being returned:
        an empty string would reach parse_completion(), raise BudgetParseError
        there, and be blamed on the model's formatting rather than on the token
        cap that actually caused it.
        """
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"unexpected Groq response shape: {json.dumps(payload)[:400]}"
            ) from exc
        if choice.get("finish_reason") == "length":
            raise RuntimeError(
                f"completion truncated at max_tokens={LiveProvider.MAX_TOKENS}; "
                f"raise the cap rather than parsing a partial answer"
            )
        if not content or not content.strip():
            raise RuntimeError("Groq returned an empty completion")
        return content


class CachedProvider:
    """Replays recorded completions. Needs no network and no provider.

    This is what makes a pilot run reproducible after the fact, and it is the
    only mode that will work in this environment today — once a cache exists.
    """

    def __init__(self, cache_path: Path = CACHE_PATH):
        self.cache_path = cache_path
        self._rows: dict[str, dict] = {}
        if cache_path.exists():
            with open(cache_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        self._rows[row["scenario_id"]] = row
        self.name = next(iter(self._rows.values()))["provider"] if self._rows else "EMPTY_CACHE"
        self.model = next(iter(self._rows.values()))["model"] if self._rows else "EMPTY_CACHE"

    def __len__(self) -> int:
        return len(self._rows)

    def lookup(self, scenario_id: str, expected_hash: str) -> str:
        if scenario_id not in self._rows:
            raise KeyError(
                f"no cached completion for {scenario_id}. The cache is empty or "
                f"incomplete; the pilot has not been run against a live model."
            )
        row = self._rows[scenario_id]
        if row["input_hash"] != expected_hash:
            raise ValueError(
                f"stale cache for {scenario_id}: recorded input_hash "
                f"{row['input_hash']} != current {expected_hash}. The prompt or "
                f"the inputs changed since this entry was written; re-run "
                f"rather than replaying an answer to a different question."
            )
        return row["raw_output"]


def cache_row(
    *, scenario_id: str, provider: str, model: str, prompt: str,
    ihash: str, raw: str, parsed: Decimal | None,
) -> dict:
    """The full record written per call — everything needed to audit or replay."""
    return {
        "scenario_id": scenario_id,
        "provider": provider,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "input_hash": ihash,
        "prompt": prompt,
        "raw_output": raw,
        "parsed_budget": str(parsed) if parsed is not None else None,
    }
