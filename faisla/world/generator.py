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

from pathlib import Path

import yaml

from faisla.world.models import ScenarioWorld


# Default directories
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIO_SPECS_DIR = _PROJECT_ROOT / "data" / "scenario_specs"


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


def load_rendered_scenarios(
    path: Path = _PROJECT_ROOT / "data" / "pilot_scenarios.jsonl",
) -> list[ScenarioWorld]:
    """Load previously rendered canonical scenarios from JSONL."""
    scenarios = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                scenarios.append(ScenarioWorld.model_validate_json(line))
    return scenarios
