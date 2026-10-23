
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 ZeroNode
#
# ercot7k_node_map.py
#
# Purpose
#   Generate a standalone interactive ERCOT7k node map from ranked PSO results.
#
# Usage
#   python geo-plots/ercot7k_node_map.py
#
# Outputs
#   geo-plots/ercot7k_node_map.html
# ------------------------------------------------------------------------------

from __future__ import annotations

# ------------------------------------------------------------------------------
# Standard imports
# ------------------------------------------------------------------------------
import argparse
import csv
from pathlib import Path

# ------------------------------------------------------------------------------
# Third-party imports
# ------------------------------------------------------------------------------
import plotly.graph_objects as go
import plotly.io as pio

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO / "ercot7k-runs" / "ercot7k-run" / "ercot7k_node_ranked.csv"
DEFAULT_OUTPUT = REPO / "geo-plots" / "ercot7k_node_map.html"
METRICS = ("max_spread", "mean_spread", "stress_hours")


# ------------------------------------------------------------------------------
# load_nodes()
# Reads ranked nodes and validates geographic coordinates.
# ------------------------------------------------------------------------------
def load_nodes(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Ranked-node CSV not found: {path}")

    nodes = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            lat = float(row["lat"])
            lon = float(row["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            nodes.append(row)

    if not nodes:
        raise ValueError("No valid ranked nodes with coordinates")
    return nodes


# ------------------------------------------------------------------------------
# build_map()
# Creates a Texas-focused interactive Plotly geographic scatter map.
# ------------------------------------------------------------------------------
def build_map(nodes: list[dict], metric: str) -> go.Figure:
    values = [float(node[metric]) for node in nodes]

    hover = [
        (
            f"Rank: {n['rank']}<br>"
            f"Node: {n['node']}<br>"
            f"Max spread: {n['max_spread']} $/MWh<br>"
            f"Mean spread: {n['mean_spread']} $/MWh<br>"
            f"Stress hours: {n['stress_hours']}<br>"
            f"LMP range: {n['min_lmp']}–{n['max_lmp']} $/MWh"
        )
        for n in nodes
    ]

    fig = go.Figure(go.Scattergeo(
        lat=[float(n["lat"]) for n in nodes],
        lon=[float(n["lon"]) for n in nodes],
        mode="markers",
        text=hover,
        hoverinfo="text",
        marker=dict(
            size=9,
            color=values,
            colorscale="YlOrRd",
            showscale=True,
            colorbar=dict(title=dict(text=metric)),
            line=dict(width=0.5, color="#333333"),
        ),
    ))

    fig.update_geos(
        scope="usa",
        center=dict(lat=31.0, lon=-99.0),
        projection=dict(
            type="albers usa",
            scale=2.0,
        ),
    )

    fig.update_layout(
        title=f"ERCOT7k Ranked Nodes — {metric}",
        height=750,
        margin=dict(l=20, r=20, t=70, b=20),
    )

    return fig


# ------------------------------------------------------------------------------
# main()
# ------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="ERCOT7k interactive node map")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metric", choices=METRICS, default="max_spread")
    args = parser.parse_args()

    try:
        nodes = load_nodes(args.input)
        fig = build_map(nodes, args.metric)
        args.output.parent.mkdir(parents=True, exist_ok=True)

        pio.write_html(
            fig,
            file=str(args.output),
            include_plotlyjs=True,
            full_html=True,
            auto_open=False,
        )

        print(f"ASR-DBG::Nodes plotted: {len(nodes)}")
        print(f"ASR-DBG::Metric: {args.metric}")
        print(f"ASR-DBG::HTML output: {args.output.resolve()}")
        return 0

    except (OSError, ValueError, KeyError) as exc:
        print(f"ASR-ERR: Map generation failed: {exc}")
        return 1


# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    raise SystemExit(main())

# ------------------------------------------------------------------------------
# END OF ercot7k_node_map.py
# ------------------------------------------------------------------------------
