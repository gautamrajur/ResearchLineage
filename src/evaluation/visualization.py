"""Visualization for multi-model comparison results.

Generates bar charts, radar plots, per-slice comparisons, and a self-contained
HTML report with embedded images.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# Colors per model (up to 5)
_COLORS = ["#2196F3", "#FF9800", "#4CAF50", "#E91E63", "#9C27B0"]


def _save_fig(fig: plt.Figure, path: str) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("Saved chart: %s", path)


def _fig_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def plot_overall_bar(selection_result: dict, output_dir: str) -> str:
    """Side-by-side bar chart of overall metrics across models."""
    scores = selection_result["scores"]
    model_names = list(scores.keys())
    winner = selection_result["winner"]

    metrics = [
        "predecessor_strict", "predecessor_soft", "mrr", "breakthrough",
        "secondary_f1", "schema_valid", "composite",
    ]
    # Normalize judge_overall to 0-1 for chart comparability
    metric_labels = [
        "Pred. Strict", "Pred. Soft", "MRR", "Breakthrough",
        "F1 (secondary)", "Schema Valid", "Composite",
    ]

    x = np.arange(len(metrics))
    width = 0.8 / len(model_names)

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, name in enumerate(model_names):
        values = [scores[name].get(m, 0) for m in metrics]
        bars = ax.bar(x + i * width, values, width, label=name, color=_COLORS[i % len(_COLORS)],
                       edgecolor="gold" if name == winner else "none", linewidth=2 if name == winner else 0)

    ax.set_xlabel("Metric")
    ax.set_ylabel("Score (0–1)")
    ax.set_title("Model Comparison — Overall Metrics")
    ax.set_xticks(x + width * (len(model_names) - 1) / 2)
    ax.set_xticklabels(metric_labels, rotation=30, ha="right")
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    path = str(Path(output_dir) / "comparison_bar.png")
    _save_fig(fig, path)
    return path


def plot_radar(selection_result: dict, output_dir: str) -> str:
    """Radar/spider chart comparing models across key metrics."""
    scores = selection_result["scores"]
    model_names = list(scores.keys())

    categories = ["Pred. Strict", "Pred. Soft", "MRR", "Breakthrough", "F1", "Judge (norm)"]
    metric_keys = ["predecessor_strict", "predecessor_soft", "mrr", "breakthrough", "secondary_f1", "judge_overall"]

    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    for i, name in enumerate(model_names):
        values = []
        for k in metric_keys:
            v = scores[name].get(k, 0)
            if k == "judge_overall":
                v = v / 5.0  # normalize to 0-1
            values.append(v)
        values += values[:1]
        ax.plot(angles, values, "-o", label=name, color=_COLORS[i % len(_COLORS)], linewidth=2)
        ax.fill(angles, values, alpha=0.1, color=_COLORS[i % len(_COLORS)])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=10)
    ax.set_ylim(0, 1.1)
    ax.set_title("Model Comparison — Radar", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    path = str(Path(output_dir) / "comparison_radar.png")
    _save_fig(fig, path)
    return path


def plot_by_slice(
    selection_result: dict,
    slice_key: str,
    output_dir: str,
    title: str,
    filename: str,
) -> str:
    """Grouped bar chart comparing models across slices (domain or tier)."""
    reports = selection_result["reports"]
    model_names = list(reports.keys())
    winner = selection_result["winner"]

    # Collect all slice names across all models
    all_slices: set[str] = set()
    for report in reports.values():
        by_slice = report.get(slice_key, {})
        all_slices.update(by_slice.keys())
    slice_names = sorted(all_slices)

    if not slice_names:
        logger.warning("No slices found for %s — skipping chart", slice_key)
        return ""

    metrics_to_plot = [("predecessor_soft", "Pred. Soft"), ("judge_overall", "Judge Overall")]
    fig, axes = plt.subplots(1, len(metrics_to_plot), figsize=(7 * len(metrics_to_plot), 6))
    if len(metrics_to_plot) == 1:
        axes = [axes]

    for ax, (metric_key, metric_label) in zip(axes, metrics_to_plot):
        x = np.arange(len(slice_names))
        width = 0.8 / len(model_names)

        for i, name in enumerate(model_names):
            by_slice = reports[name].get(slice_key, {})
            values = []
            for s in slice_names:
                slice_data = by_slice.get(s, {})
                if metric_key.startswith("judge"):
                    v = slice_data.get("judge", {}).get(metric_key, 0) or 0
                else:
                    v = slice_data.get("classification", {}).get(metric_key, 0) or 0
                values.append(v)

            ax.bar(x + i * width, values, width, label=name, color=_COLORS[i % len(_COLORS)])

        ax.set_xlabel(title.split(" ")[-1])
        ax.set_ylabel(metric_label)
        ax.set_title(f"{metric_label} by {title}")
        ax.set_xticks(x + width * (len(model_names) - 1) / 2)
        ax.set_xticklabels(slice_names, rotation=30, ha="right")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    path = str(Path(output_dir) / filename)
    _save_fig(fig, path)
    return path


def generate_html_report(selection_result: dict, chart_paths: list[str], output_dir: str) -> str:
    """Generate a self-contained HTML report with embedded charts."""
    scores = selection_result["scores"]
    winner = selection_result["winner"]
    rankings = selection_result["rankings"]

    # Build metrics table
    model_names = list(scores.keys())
    all_metrics = sorted({k for s in scores.values() for k in s.keys()})

    rows_html = ""
    for metric in all_metrics:
        values = {name: scores[name].get(metric, 0) for name in model_names}
        best_name = max(values, key=lambda n: values[n])
        cells = ""
        for name in model_names:
            v = values[name]
            style = ' style="background:#c8e6c9;font-weight:bold"' if name == best_name else ""
            cells += f"<td{style}>{v:.4f}</td>"
        rows_html += f"<tr><td>{metric}</td>{cells}</tr>\n"

    # Embed charts
    charts_html = ""
    for path in chart_paths:
        if path and Path(path).exists():
            b64 = _fig_to_base64(path)
            charts_html += f'<img src="data:image/png;base64,{b64}" style="max-width:100%;margin:10px 0">\n'

    # Rankings
    rankings_html = ""
    for rank, (name, score) in enumerate(rankings, 1):
        medal = {1: "&#129351;", 2: "&#129352;", 3: "&#129353;"}.get(rank, f"#{rank}")
        rankings_html += f"<tr><td>{medal}</td><td>{name}</td><td><b>{score:.4f}</b></td></tr>\n"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Model Comparison Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #fafafa; }}
h1 {{ color: #1a237e; }}
h2 {{ color: #283593; border-bottom: 2px solid #e8eaf6; padding-bottom: 8px; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: center; }}
th {{ background: #283593; color: white; }}
.winner {{ background: #e8f5e9; border: 2px solid #4caf50; padding: 16px; border-radius: 8px; margin: 16px 0; }}
.formula {{ background: #e3f2fd; padding: 12px; border-radius: 4px; font-family: monospace; }}
</style>
</head>
<body>
<h1>Model Comparison Report</h1>

<div class="winner">
<h2>Winner: {winner}</h2>
<p>Composite score: <b>{scores[winner]['composite']:.4f}</b></p>
</div>

<div class="formula">
<b>Selection formula:</b> Score = 0.75 &times; predecessor_soft + (judge_overall / 5) &times; 0.25
</div>

<h2>Rankings</h2>
<table>
<tr><th>Rank</th><th>Model</th><th>Composite Score</th></tr>
{rankings_html}
</table>

<h2>Detailed Metrics</h2>
<table>
<tr><th>Metric</th>{"".join(f"<th>{n}</th>" for n in model_names)}</tr>
{rows_html}
</table>

<h2>Visualizations</h2>
{charts_html}

<hr>
<p><small>Generated by ResearchLineage model comparison pipeline</small></p>
</body>
</html>"""

    path = str(Path(output_dir) / "model_comparison.html")
    Path(path).write_text(html)
    logger.info("Saved HTML report: %s", path)
    return path


def generate_comparison_report(selection_result: dict[str, Any], output_dir: str) -> list[str]:
    """Generate all comparison visualizations and HTML report.

    Returns list of output file paths.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    paths.append(plot_overall_bar(selection_result, output_dir))
    paths.append(plot_radar(selection_result, output_dir))
    paths.append(plot_by_slice(
        selection_result, "by_domain", output_dir,
        title="Domain", filename="comparison_by_domain.png",
    ))
    paths.append(plot_by_slice(
        selection_result, "by_citation_tier", output_dir,
        title="Citation Tier", filename="comparison_by_tier.png",
    ))

    chart_paths = [p for p in paths if p]
    paths.append(generate_html_report(selection_result, chart_paths, output_dir))

    return [p for p in paths if p]
