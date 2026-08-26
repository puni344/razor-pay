"""
FAISLA — Sufficiency/Correctness Divergence Chart

Plots the Day-1 primary finding: across the two rule versions, causal
correctness moves substantially while the flip rate does not move at all.

Reads the two frozen adjudication result files and the scenario specs.
Computes nothing new — the same counts the kill-test report already states.

Entrypoint: python -m faisla.evaluation.plot_divergence
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from faisla.world.oracle import get_ground_truth, reset_cache

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = _PROJECT_ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "divergence.png"

VERSIONS = [
    "dev-calibration-0.1.0",
    "holdout-informed-bugfix-0.2.0",
]

DUP_CLASS = "DUPLICATE_OR_RETRY_EXECUTION"

# Palette — one hue per series, readable in print and on screen.
FLIP_COLOR = "#3F6FB5"
CORRECT_COLOR = "#C2603F"
INK = "#22252A"
MUTED = "#6B7280"
GRID = "#DFE3E8"


def _load(version: str) -> list[dict]:
    path = RESULTS_DIR / f"adjudication_{version}.jsonl"
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _metrics(rows: list[dict]) -> tuple[float, float]:
    """Return (flip rate over held-out non-duplicates, causal correctness over
    all 18 held-out) — the two figures the report quotes."""
    held = [r for r in rows if r["split"] == "holdout"]

    non_dup = [r for r in held if r["failure_class"] != DUP_CLASS]
    flips = sum(
        1 for r in non_dup
        if r["E0"]["sufficiency"] == "INSUFFICIENT"
        and r["E3"]["sufficiency"] == "SUFFICIENT"
    )

    correct = sum(
        1 for r in held
        if r["E3"]["causal_category"]
        == get_ground_truth(r["scenario_id"]).causal_category.value
    )

    return flips / len(non_dup), correct / len(held)


def build_figure():
    reset_cache()

    flip_rates, correctness, counts = [], [], []
    for version in VERSIONS:
        rows = _load(version)
        held = [r for r in rows if r["split"] == "holdout"]
        non_dup = [r for r in held if r["failure_class"] != DUP_CLASS]
        flip, corr = _metrics(rows)
        flip_rates.append(flip * 100)
        correctness.append(corr * 100)
        counts.append((
            round(flip * len(non_dup)), len(non_dup),
            round(corr * len(held)), len(held),
        ))

    x = [0, 1]
    fig, ax = plt.subplots(figsize=(10, 6.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.plot(x, flip_rates, "-o", color=FLIP_COLOR, linewidth=2.6,
            markersize=10, zorder=3)
    ax.plot(x, correctness, "-o", color=CORRECT_COLOR, linewidth=2.6,
            markersize=10, zorder=3)

    # Direct labels on the lines, not only a legend.
    ax.annotate("Flip rate\n(held-out non-duplicate)",
                xy=(0.02, flip_rates[0]), xytext=(0.02, flip_rates[0] - 9),
                color=FLIP_COLOR, fontsize=11.5, fontweight="bold",
                ha="left", va="top", linespacing=1.35)
    ax.annotate("Causal correctness\n(all 18 held-out)",
                xy=(0.98, correctness[1]), xytext=(0.98, correctness[1] - 8),
                color=CORRECT_COLOR, fontsize=11.5, fontweight="bold",
                ha="right", va="top", linespacing=1.35)

    # Data labels at every point.
    for i in x:
        f_n, f_d, c_n, c_d = counts[i]
        ax.annotate(f"{flip_rates[i]:.1f}%  ({f_n}/{f_d})",
                    xy=(i, flip_rates[i]), xytext=(0, 14),
                    textcoords="offset points", ha="center",
                    fontsize=12, fontweight="bold", color=FLIP_COLOR)
        ax.annotate(f"{correctness[i]:.1f}%  ({c_n}/{c_d})",
                    xy=(i, correctness[i]), xytext=(0, 14),
                    textcoords="offset points", ha="center",
                    fontsize=12, fontweight="bold", color=CORRECT_COLOR)

    # The gap between the series is the finding — shade it.
    ax.fill_between(x, correctness, flip_rates, color="#9AA3AE", alpha=0.11,
                    zorder=1)
    delta = correctness[1] - correctness[0]
    ax.annotate(
        f"correctness +{delta:.1f} pts\nflip rate unchanged",
        xy=(0.5, (flip_rates[0] + correctness[0] + correctness[1]) / 3),
        ha="center", va="center", fontsize=10.5, color=MUTED,
        style="italic", linespacing=1.4,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(["dev-calibration-0.1.0\n(unbiased held-out estimate)",
                        "holdout-informed-bugfix-0.2.0\n(held-out-informed)"],
                       fontsize=10.5, color=INK)
    ax.set_xlim(-0.28, 1.28)
    ax.set_ylim(30, 112)
    ax.set_yticks([40, 50, 60, 70, 80, 90, 100])
    ax.set_yticklabels([f"{v}%" for v in [40, 50, 60, 70, 80, 90, 100]],
                       fontsize=10.5, color=INK)
    ax.set_ylabel("Held-out rate", fontsize=11.5, color=INK, labelpad=10)
    ax.set_xlabel("rule_version", fontsize=11.5, color=INK, labelpad=12)

    ax.set_title(
        "Sufficiency and correctness diverge",
        fontsize=16, fontweight="bold", color=INK, pad=46, loc="left",
    )
    ax.text(
        0, 1.012,
        "Two bug fixes raised causal correctness by "
        f"{delta:.1f} points and moved the flip rate by zero.",
        transform=ax.transAxes, fontsize=11, color=MUTED, va="bottom",
    )

    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)

    fig.text(
        0.01, 0.015,
        "PILOT — n=18 held out. Flip rate denominator excludes "
        "DUPLICATE_OR_RETRY_EXECUTION per §13.",
        fontsize=9, color=MUTED,
    )

    fig.tight_layout(rect=(0, 0.03, 1, 0.99))
    return fig


def main() -> None:
    fig = build_figure()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, dpi=200, facecolor="white")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
