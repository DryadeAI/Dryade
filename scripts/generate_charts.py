#!/usr/bin/env python3
"""
Generate competitive analysis charts for Dryade.

Reads architecture-radar-data.json and pricing-heatmap-data.json,
generates radar chart and pricing heatmap PNG files.

Usage:
    python scripts/generate_charts.py
    python scripts/generate_charts.py --output-dir docs/competitive/charts
"""

import argparse
import json
import sys
from pathlib import Path

def find_repo_root():
    """Find the repository root (directory containing docs/competitive)."""
    script_dir = Path(__file__).parent
    # Try parent of scripts/ directory
    repo_root = script_dir.parent
    if (repo_root / "docs" / "competitive").exists():
        return repo_root
    # Fallback: current working directory
    cwd = Path.cwd()
    if (cwd / "docs" / "competitive").exists():
        return cwd
    raise RuntimeError(
        f"Cannot find repository root. Expected docs/competitive/ to exist. "
        f"Tried: {repo_root}, {cwd}"
    )

def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)

def generate_radar_chart(radar_data: dict, output_path: Path) -> None:
    """Generate a radar chart comparing Dryade vs top 8 competitors."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    dimensions = radar_data["dimensions"]
    players_data = radar_data["players"]

    # Select players to compare: Dryade + top 8 competitors by threat level
    selected_players = [
        "dryade",
        "dify",
        "langflow",
        "microsoft_maf",
        "azure_foundry",
        "n8n",
        "crewai",
        "aws_bedrock",
        "google_adk",
    ]
    # Filter to only players that exist in data
    selected_players = [p for p in selected_players if p in players_data]

    # Color scheme
    colors = {
        "dryade": "#1e40af",  # Blue — Dryade
        "dify": "#dc2626",  # Red — HIGH threat
        "langflow": "#d97706",  # Orange — MEDIUM threat
        "microsoft_maf": "#7c3aed",  # Purple
        "azure_foundry": "#dc2626",  # Red — HIGH threat
        "n8n": "#16a34a",  # Green
        "crewai": "#d97706",  # Orange
        "aws_bedrock": "#6b7280",  # Gray
        "google_adk": "#6b7280",  # Gray
    }
    linewidths = {
        "dryade": 3.0,  # Thick line for Dryade
    }

    labels = [d.replace("_", "\n").title() for d in dimensions]
    N = len(dimensions)

    # Compute angle for each axis
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw={"polar": True})

    for player in selected_players:
        values = players_data[player]
        values += values[:1]  # close the polygon

        color = colors.get(player, "#94a3b8")
        lw = linewidths.get(player, 1.5)
        alpha = 0.25 if player == "dryade" else 0.08
        label = player.replace("_", " ").title()

        ax.plot(angles, values, "o-", linewidth=lw, color=color, label=label)
        ax.fill(angles, values, alpha=alpha, color=color)

    # Labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=11, fontweight="bold")
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], size=8, color="gray")
    ax.grid(color="gray", linestyle="--", linewidth=0.5, alpha=0.7)

    # Title and legend
    ax.set_title(
        "Dryade vs Competitors — Architecture Radar\n"
        "Dimensions: Extensibility, Security, Scalability, Simplicity, Ecosystem",
        size=13,
        fontweight="bold",
        pad=20,
    )
    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.35, 1.15),
        fontsize=9,
        title="Players",
        title_fontsize=10,
    )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Radar chart saved: {output_path}")

def generate_pricing_heatmap(heatmap_data: dict, output_path: Path) -> None:
    """Generate a pricing heatmap showing tier pricing across players."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    players = heatmap_data["players"]
    tiers = heatmap_data["meta"]["tiers"]
    values = heatmap_data["values"]

    # Only include players with at least one non-null price value
    def has_price(player):
        row = values.get(player, [None, None, None, None])
        return any(v is not None for v in row)

    filtered_players = [p for p in players if has_price(p)]

    # Build the matrix
    matrix = []
    for player in filtered_players:
        row = values.get(player, [None, None, None, None])
        matrix.append(row)

    # Convert to numpy array, replacing None with NaN
    data = np.array([[v if v is not None else np.nan for v in row] for row in matrix], dtype=float)

    # Normalize for coloring: log scale works well for pricing spread
    # Replace 0 with 0.5 for log scale (free tier is distinct from null)
    data_log = np.where(data == 0, 0.5, data)
    data_log = np.log10(np.where(np.isnan(data_log), np.nan, data_log + 1))

    # Figure size based on player count
    fig_height = max(8, len(filtered_players) * 0.35)
    fig, ax = plt.subplots(figsize=(12, fig_height))

    # Custom colormap: white for NaN, green for $0, yellow->orange->red for prices
    cmap = plt.cm.YlOrRd
    cmap.set_bad("lightgray")

    im = ax.imshow(data_log, aspect="auto", cmap=cmap, interpolation="nearest")

    # Axis labels
    tier_labels = ["Free", "Starter", "Team/Pro", "Enterprise"]
    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels(tier_labels, fontsize=11, fontweight="bold")
    ax.set_yticks(range(len(filtered_players)))
    ax.set_yticklabels(
        [p.replace("-", " ").replace("_", " ").title() for p in filtered_players],
        fontsize=8,
    )

    # Annotate each cell with the actual price
    for i, player in enumerate(filtered_players):
        for j, tier in enumerate(tiers):
            val = matrix[i][j]
            if val is None:
                text = "—"
                color = "gray"
            elif val == 0:
                text = "Free"
                color = "darkgreen"
            else:
                text = f"${val:,.0f}"
                color = "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=7, color=color)

    # Title and colorbar
    ax.set_title(
        "Pricing Heatmap — Agentic AI Platform Tier Pricing (USD/month)\n"
        "Gray = not applicable | Green = free | Yellow→Red = price level",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )

    # Highlight Dryade row
    if "dryade" in filtered_players:
        dryade_idx = filtered_players.index("dryade")
        ax.axhline(dryade_idx - 0.5, color="#1e40af", linewidth=2)
        ax.axhline(dryade_idx + 0.5, color="#1e40af", linewidth=2)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Pricing heatmap saved: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate competitive analysis charts")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for charts (default: docs/competitive/charts/)",
    )
    args = parser.parse_args()

    # Find repo root
    try:
        repo_root = find_repo_root()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    charts_dir = (
        Path(args.output_dir) if args.output_dir else repo_root / "docs" / "competitive" / "charts"
    )
    charts_dir.mkdir(parents=True, exist_ok=True)

    radar_data_path = charts_dir / "architecture-radar-data.json"
    heatmap_data_path = charts_dir / "pricing-heatmap-data.json"

    if not radar_data_path.exists():
        print(f"ERROR: {radar_data_path} not found", file=sys.stderr)
        sys.exit(1)

    if not heatmap_data_path.exists():
        print(f"ERROR: {heatmap_data_path} not found", file=sys.stderr)
        sys.exit(1)

    # Load data
    print("Loading data...")
    radar_data = load_json(radar_data_path)
    heatmap_data = load_json(heatmap_data_path)

    # Generate charts
    print("Generating charts...")

    radar_output = charts_dir / "radar-comparison.png"
    heatmap_output = charts_dir / "pricing-heatmap.png"

    try:
        generate_radar_chart(radar_data, radar_output)
    except ImportError:
        print(
            "ERROR: matplotlib not installed. Run: uv pip install matplotlib",
            file=sys.stderr,
        )
        sys.exit(1)

    generate_pricing_heatmap(heatmap_data, heatmap_output)

    print("\nDone. Charts generated:")
    print(f"  {radar_output}")
    print(f"  {heatmap_output}")

if __name__ == "__main__":
    main()
