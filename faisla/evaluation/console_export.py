"""
FAISLA — Consolidated Console Export

Joins the already-written artefacts into one static JSON file, one entry per
scenario, all 24.

PURE EXPORT/JOIN. Nothing is recomputed or re-derived: evidence packets are
copied verbatim from data/evidence/, verdicts verbatim from the two frozen
results files, and ground truth read through the oracle's accessor. No
adjudication runs, no rendering, no scoring. Running this cannot change any
number reported in results/kill_test_report.md.

Entrypoint: python -m faisla.evaluation.console_export
"""

from __future__ import annotations

import json
from pathlib import Path

from faisla.world.oracle import get_ground_truth, reset_cache

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EVIDENCE_DIR = _PROJECT_ROOT / "data" / "evidence"
RESULTS_DIR = _PROJECT_ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "console_export.json"

V1 = "dev-calibration-0.1.0"
V2 = "holdout-informed-bugfix-0.2.0"


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _index(rows: list[dict]) -> dict[str, dict]:
    return {r["scenario_id"]: r for r in rows}


def _verdict(row: dict, condition: str) -> dict:
    """Extract the three findings for one condition, verbatim."""
    r = row[condition]
    return {
        "scope_finding": r["scope_finding"],
        "causal_category": r["causal_category"],
        "sufficiency": r["sufficiency"],
        "sufficiency_rationale": r["sufficiency_rationale"],
        "rules_fired": [f["rule_id"] for f in r["rules_fired"]],
    }


def build_export() -> dict:
    reset_cache()

    e0 = _index(_read_jsonl(EVIDENCE_DIR / "E0.jsonl"))
    e3 = _index(_read_jsonl(EVIDENCE_DIR / "E3.jsonl"))
    v1 = _index(_read_jsonl(RESULTS_DIR / f"adjudication_{V1}.jsonl"))
    v2 = _index(_read_jsonl(RESULTS_DIR / f"adjudication_{V2}.jsonl"))

    scenario_ids = sorted(e0)
    assert len(scenario_ids) == 24, f"expected 24 scenarios, got {len(scenario_ids)}"
    for name, src in (("E3", e3), (V1, v1), (V2, v2)):
        missing = set(scenario_ids) - set(src)
        assert not missing, f"{name} is missing {sorted(missing)}"

    scenarios = []
    for sid in scenario_ids:
        gt = get_ground_truth(sid)
        scenarios.append({
            "scenario_id": sid,
            # failure_class and split come from the results files, which
            # recorded them at run time. They are NOT on the evidence packets
            # — the adjudicator was never able to see either one.
            "failure_class": v1[sid]["failure_class"],
            "split": v1[sid]["split"],
            "evidence": {
                "E0": e0[sid],
                "E3": e3[sid],
            },
            "verdicts": {
                V1: {
                    "E0": _verdict(v1[sid], "E0"),
                    "E3": _verdict(v1[sid], "E3"),
                },
                V2: {
                    "E0": _verdict(v2[sid], "E0"),
                    "E3": _verdict(v2[sid], "E3"),
                },
            },
            "ground_truth": {
                "scope_violation": gt.scope_violation,
                "causal_category": gt.causal_category.value,
            },
        })

    return {
        "export_note": (
            "Pure export/join of existing artefacts. Nothing recomputed. "
            "Evidence packets copied from data/evidence/, verdicts from the "
            "two frozen adjudication result files, ground truth via the "
            "oracle accessor."
        ),
        "rule_versions": {
            V1: "DEV-calibrated, frozen before the held-out run — the pilot's "
                "one unbiased held-out estimate.",
            V2: "Two bug fixes identified FROM held-out results; "
                "held-out-informed, NOT an unbiased estimate.",
        },
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def main() -> None:
    export = build_export()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUTPUT_PATH} — {export['scenario_count']} scenarios")


if __name__ == "__main__":
    main()
