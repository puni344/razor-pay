"""
FAISLA — World Generator

Loads hand-authored scenario specifications from YAML files,
validates them against the ScenarioWorld schema, and deterministically
renders canonical ScenarioWorld records.

This module NEVER invents scenario content. Its job is to load, validate,
and render — not to decide what any scenario says. If this file contains
logic that chooses a causal_category, an amount, or an injection_payload
on its own (randomly or via rule), that is a bug.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Sequence

import yaml

from faisla.world.models import ScenarioWorld


# Default directories
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIO_SPECS_DIR = _PROJECT_ROOT / "data" / "scenario_specs"
PILOT_SCENARIOS_PATH = _PROJECT_ROOT / "data" / "pilot_scenarios.jsonl"


def load_scenario_spec(spec_path: Path) -> ScenarioWorld:
    """Load a single YAML scenario spec and validate against ScenarioWorld.

    No transformation, no invention. The YAML must contain every field
    the ScenarioWorld model requires, exactly as the human author wrote it.
    """
    with open(spec_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ScenarioWorld(**data)


def load_all_scenario_specs(
    specs_dir: Path = SCENARIO_SPECS_DIR,
) -> list[ScenarioWorld]:
    """Load all scenario specs from the directory, sorted by scenario_id."""
    specs = []
    for path in sorted(specs_dir.glob("SC-*.yaml")):
        specs.append(load_scenario_spec(path))
    return specs


def render_pilot_scenarios(
    specs_dir: Path = SCENARIO_SPECS_DIR,
    output_path: Path = PILOT_SCENARIOS_PATH,
) -> list[ScenarioWorld]:
    """Load all specs, validate, and write canonical JSONL output.

    Deterministic: re-running against the same specs produces byte-identical output.
    """
    scenarios = load_all_scenario_specs(specs_dir)

    # Validate uniqueness of scenario IDs
    ids = [s.scenario_id for s in scenarios]
    if len(ids) != len(set(ids)):
        duplicates = [sid for sid in ids if ids.count(sid) > 1]
        raise ValueError(f"Duplicate scenario IDs found: {set(duplicates)}")

    # Write canonical JSONL — sorted by scenario_id for determinism
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for scenario in scenarios:
            f.write(scenario.model_dump_json() + "\n")

    return scenarios


def load_rendered_scenarios(
    path: Path = PILOT_SCENARIOS_PATH,
) -> list[ScenarioWorld]:
    """Load previously rendered canonical scenarios from JSONL."""
    scenarios = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                scenarios.append(ScenarioWorld.model_validate_json(line))
    return scenarios
