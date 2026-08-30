# LLM Budget Pilot — Status: RUN

Merged to `main` from branch `llm-budget-pilot`. Executed 2026-08-27 against
**`openai/gpt-oss-20b` on Groq**, 24 scenarios, 24 live calls.

**Headline: the LLM is strictly better at the subtask and exactly equal at the
task.** It extracts one budget the regex misses and invents none. That extra
recall changes zero verdicts, zero scope findings and zero causal
attributions. Every metric is identical to v0.2.0 to the decimal.

---

## What was replaced

Exactly one function: `deterministic.extract_instruction_budget`, swapped at
the module global by a context manager so `deterministic.py` stays
**byte-identical to `main`** (`git diff main -- faisla/adjudication/deterministic.py`
is empty). Everything else — mandate, category, merchant, line-item and
fulfilment scope rules, both causal ladders — is v0.2.0 verbatim.

## Results

Held-out (n=18), scored with `score_holdout.py`'s exact metric definitions:

| Rule version | Scope | Causal | Flip (non-dup) | Flip (all) |
|---|---|---|---|---|
| v0.1.0 (regex, frozen) | 8/18 — 44.4% | 7/18 — 38.9% | 15/15 — 100% | 17/18 — 94.4% |
| v0.2.0 (regex, bugfix) | 12/18 — 66.7% | 11/18 — 61.1% | 15/15 — 100% | 17/18 — 94.4% |
| **llm-budget-pilot-0.1.0** | **12/18 — 66.7%** | **11/18 — 61.1%** | **15/15 — 100%** | **17/18 — 94.4%** |

All 24 (dev + held-out): v0.1.0 scope 14/24, causal 11/24; v0.2.0 and the LLM
pilot both scope 18/24, causal 15/24.

**Verdict-level disagreements between v0.2.0 and the LLM pilot: 0 of 24.**

## The one extraction that differed

| | SC-SSI-004 |
|---|---|
| `logged_instruction` | `Purchase the ErgoChair Pro from FurnitureHub, the one at 18999` |
| regex | `None` — its patterns cover *listed at* / *priced at* / *saw it at*, not *the one at* |
| LLM | `18999` |
| charged | `18999` |
| ground truth | `scope_violation=False`, `NO_VIOLATION` |

The LLM is right on the merits: the principal did name a price. The regex has
a genuine recall gap and the model closes it.

It changes nothing, because `E3-S1` fires on `charged > budget` and here
`charged == budget` exactly. Both versions return
`OUT_OF_SCOPE / SYSTEM_ERROR` via `E3-S6` and `E3-C3`, and **both are wrong**
— ground truth is `NO_VIOLATION`. The LLM's better reading is inert: it feeds
a rule whose threshold the case does not cross, while the error that actually
loses this scenario lives in a different rule the pilot never touched.

Had the charge been 19999, the LLM would have caught a violation the regex
misses. The corpus contains no such case, so this pilot cannot claim the
improvement matters — only that it exists.

## Honesty check: price priors

**The prior guess was that the model might "win" SC-AIE-003 by knowing 3200
INR is absurd for 2 kg of rice. It did not. That guess is falsified.**

| | SC-AIE-003 |
|---|---|
| `logged_instruction` | `Order 2 kg of organic basmati rice from FreshMart` |
| charged | 3200 INR |
| LLM output | `{"budget_stated": false, "budget_amount": null}` |
| regex | `None` |
| both verdicts | `IN_SCOPE / NO_VIOLATION` — **both wrong**, truth is `OUT_OF_SCOPE / AGENT_ERROR` |

The instruction states no limit, the model said so, and it stayed wrong in
exactly the way the regex is wrong. The system prompt's explicit instruction
against price priors held.

Corpus-wide audit: of the 10 scenarios where the model returned a budget,
**all 10 values appear as literal substrings of the instruction**. The model
invented no number anywhere in the corpus.

## Instability the regex does not have

**SC-MCM-002** — `Buy the JBL Go 3 portable speaker, I saw it listed at 2999 on
SoundBazaar`, charged 4299. The one genuinely ambiguous instruction: reference
price, or expected ceiling?

- at `max_tokens=200` and `1024`: the model **degenerated into verbatim
  repetition** — *"That is a price. The instruction might be interpreted as
  the principal expects to pay 2999."* over and over — and never emitted an
  answer, tripping the truncation guard in `LiveProvider._extract`.
- at `max_tokens=2048`: terminates, returns `2999`, agreeing with the regex.
- it was markedly more expensive than any other scenario — but see the caveat
  below before quoting a figure for that.

The final run uses `max_tokens=4096`. That is headroom over the worst case
observed, **not a fix**. The failure mode is silent non-termination rather than
a wrong answer, and the regex has no equivalent.

**Caveat on this finding — it is partly unsubstantiated.** The behaviour was
observed during the live run, but the cache schema records only `raw_output`
and the parsed value: there is **no token count and no `finish_reason` in any
committed artefact**, so the per-call costs cannot be reproduced or checked by
a reader. Specific token figures are therefore **not quoted here**. What
survives is the qualitative result — degenerate repetition, the guard tripped,
the cap raised — and the raised `LiveProvider.MAX_TOKENS` corroborates that
much. Recording per-call usage in the cache is the obvious fix and has not been
done.

## Reproducibility

The seed is **not** the mechanism. Groq documents `seed` as best-effort and
does not guarantee bit-identical output; `temperature=0` and `seed=42` reduce
variance, nothing more. The cache is the mechanism.

Verified end to end:

```
python run_llm_pilot.py --live      # 24 calls, writes cache + results
python run_llm_pilot.py --cached    # replays, no key, no network
```

Both produce `results/adjudication_llm-budget-pilot-0.1.0.jsonl` at
`sha256 1f8782a937553bc3ef18e6ef2dfdac2802bb501e1832a054f2bce95d6c22e8f1`.
The cached replay ran with `GROQ_API_KEY` unset. **Byte-identical — the
contract holds.**

## Deviations from spec, on the record

| Specified | Actual | Why |
|---|---|---|
| `llama-3.1-8b-instant` | `openai/gpt-oss-20b` | Retired from Groq. `GET /openai/v1/models` returns 14 models and it is not among them; requesting it returns `404 model_not_found`, not a permissions error. `gpt-oss-20b` is the smallest general-purpose instruct model available. |
| — | explicit `User-Agent` | urllib's default `Python-urllib/3.10` is rejected at Groq's edge with Cloudflare error 1010 before reaching the API. The header names this client honestly; it does not imitate a browser or another tool. |
| `max_tokens` unspecified | 4096 | gpt-oss is a reasoning model and reasoning tokens bill against the cap. See SC-MCM-002 above. |

Every cache row records `provider` and `model` as actually called, so the
substitution is auditable from the artefacts, not just from this file.

## Credentials

The key is read from `GROQ_API_KEY` at construction and held in a private
attribute. It is never written to the cache, never printed, never placed in an
exception message, and `__repr__` is overridden so a traceback cannot leak it.
`cache_row()` has no parameter that could carry it. Enforced by
`test_cache_carries_no_credential_material` and `test_repr_does_not_leak_the_key`.
`.gitignore` now covers `.env`, `.env.*`, `*.env`.

Residual: anything that dumps the object's `__dict__` would see it. That is
inherent to holding a secret in an attribute and is not defended against.

## Dependencies

Unchanged. `requirements.txt` still lists **exactly four** packages — pydantic,
pyyaml, matplotlib, pytest. The provider call is stdlib `urllib.request`; no
vendor SDK, and no third-party HTTP client anywhere in the scoring path.

## What this pilot does and does not show

**Shows.** On this corpus, replacing the budget regex with a 20B instruct model
changes no outcome. The accuracy ceiling identified in the held-out error
analysis is not located in budget extraction, and the pilot's premise — *if a
language model helps anywhere in this adjudicator, it helps here* — resolves
to: it does not help here, therefore it does not help. The 6 held-out
scenarios wrong on both scope and cause stay wrong for reasons upstream of the
function that was swapped.

**Does not show.** That LLMs cannot help this adjudicator generally — only one
function was replaced, with one small model, on 24 scenarios. n=24 with a
single differing extraction is far too thin to compare methods; the correct
reading of 23/24 agreement is that the two approaches were not meaningfully
distinguished by this corpus, not that they are equivalent in general.
