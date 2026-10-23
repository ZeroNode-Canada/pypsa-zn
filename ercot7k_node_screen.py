#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 ZeroNode
#
# ercot7k_node_screen.py
#
# Purpose
#   Screen and rank ERCOT Texas7k nodes using baseline PSO nodal LMP
#   separation from area balance price, without invoking AIMMS/CPLEX.
#
# What it does
#   - Reads researcher-selected screening configuration CSV.
#   - Streams PSO nodal LMP and area balance-price results.
#   - Calculates maximum/mean LMP spread and stress duration.
#   - Reads PSO model metadata to determine interval duration.
#   - Joins ERCOT7k geographic coordinates (latitude/longitude/zone).
#   - Supports interactive CSV selection, review, editing, and confirmation.
#   - Ranks nodes by max_spread, mean_spread, or stress_hours.
#   - Preserves all baseline PSO input and result files.
#
# Inputs
#   - ercot7k-runs/<run>/results/results_PC_Nd.csv
#   - ercot7k-runs/<run>/results/results_ED_Ara.csv
#   - ercot7k_config/ercot7k_node_filters.csv
#   - ercot7k_geo/texas7k_bus_coords.csv
#   - ercot7k/texas7k_MDL_ID.csv
#
# Outputs
#   - ercot7k-runs/<run>/ercot7k_node_ranked.csv
#
# Usage
#   python ercot7k_node_screen.py --run ercot7k-run
#   python ercot7k_node_screen.py --results <results-directory>
#   python ercot7k_node_screen.py -h
#
# ------------------------------------------------------------------------------

from __future__ import annotations

# ------------------------------------------------------------------------------
# Standard imports
# ------------------------------------------------------------------------------
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DEFAULT_FILTERS = ROOT / "ercot7k_config" / "ercot7k_node_filters.csv"
DEFAULT_GEO = ROOT / "ercot7k_geo" / "texas7k_bus_coords.csv"
DEFAULT_MODEL = ROOT / "ercot7k" / "texas7k_MDL_ID.csv"

ALLOWED_METRICS = {"max_spread", "mean_spread", "stress_hours"}

FILTER_DESCRIPTIONS = {
    "cycle": "PSO optimization cycle",
    "scenario": "PSO scenario within selected cycle",
    "ranking_metric": "Metric used to rank candidate nodes",
    "spread_threshold": "Minimum absolute LMP separation ($/MWh)",
    "min_stress_hours": "Minimum qualifying duration (hours)",
    "min_lmp": "Lower bound on nodal LMP ($/MWh)",
    "max_lmp": "Upper bound on nodal LMP ($/MWh)",
    "min_load_mw": "Reserved; must remain zero",
    "min_voltage_kv": "Reserved; must remain zero",
    "top_n": "Maximum number of ranked nodes",
}

# ------------------------------------------------------------------------------
# read_rows()
# Reads PSO CSVs whose first header field is prefixed with //.
# ------------------------------------------------------------------------------
def read_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"Empty CSV: {path}")
        reader.fieldnames = [field.removeprefix("//").strip() for field in reader.fieldnames]
        yield from reader


# ------------------------------------------------------------------------------
# load_filters()
# ------------------------------------------------------------------------------
def load_filters(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing node-screening filter CSV:\n  {path}\n"
            "Create ercot7k_config/ercot7k_node_filters.csv "
            "or supply an alternate file using --filters."
        )

    settings = {}
    for row in read_rows(path):
        key = (row.get("parameter") or "").strip()
        if key and not key.startswith("#"):
            if key in settings:
                raise ValueError(f"Duplicate filter parameter: {key}")
            settings[key] = (row.get("value") or "").strip()

    required = ("cycle", "scenario", "ranking_metric", "spread_threshold",
                "min_stress_hours", "min_lmp", "max_lmp", "min_load_mw",
                "min_voltage_kv", "top_n")
    missing = [key for key in required if key not in settings]
    if missing:
        raise ValueError(f"Missing filter parameter(s): {', '.join(missing)}")
    if settings["ranking_metric"] not in ALLOWED_METRICS:
        raise ValueError(f"Invalid ranking_metric: {settings['ranking_metric']}")

    for key in ("spread_threshold", "min_stress_hours", "min_lmp", "max_lmp",
                "min_load_mw", "min_voltage_kv"):
        settings[key] = float(settings[key])
        if not math.isfinite(settings[key]):
            raise ValueError(f"Non-finite filter: {key}")
    settings["top_n"] = int(settings["top_n"])
    if settings["top_n"] <= 0 or settings["spread_threshold"] < 0 or settings["min_stress_hours"] < 0:
        raise ValueError("top_n must be positive; spread_threshold/min_stress_hours cannot be negative")
    if settings["min_lmp"] > settings["max_lmp"]:
        raise ValueError("min_lmp cannot exceed max_lmp")
    if settings["min_load_mw"] != 0 or settings["min_voltage_kv"] != 0:
        raise ValueError("min_load_mw and min_voltage_kv are not implemented; keep both at 0")
    return settings


# ------------------------------------------------------------------------------
# review_filters()
# Displays the active screening configuration and calculation basis.
# ------------------------------------------------------------------------------
def review_filters(path: Path, settings: dict, interval_hours: float) -> None:
    print("\n" + "=" * 80)
    print("ERCOT7k Node Screening — Active Configuration")
    print(f"Filter CSV: {path.resolve()}")
    print("-" * 80)
    print(f"{'Parameter':<22} {'Value':<16} Interpretation")
    print("-" * 80)

    for key, description in FILTER_DESCRIPTIONS.items():
        print(f"{key:<22} {str(settings[key]):<16} {description}")

    print("-" * 80)
    print(f"Model interval duration: {interval_hours:g} hours")
    print("\nCalculation basis:")
    print("  signed_spread      = nodal LMP - area BalancePrice")
    print("  max_spread         = maximum absolute spread")
    print("  mean_spread        = mean absolute spread")
    print("  stress_hours       = qualifying intervals x interval duration")
    print("  qualifying node    = abs(signed_spread) >= spread_threshold")
    print("\nRanking: descending selected metric; node ID breaks ties.")
    print("=" * 80)

# ------------------------------------------------------------------------------
# confirm_filters()
# Allows the researcher to proceed, edit/reload, or cancel.
# ------------------------------------------------------------------------------
def confirm_filters(path: Path, interval_hours: float) -> dict | None:
    while True:
        settings = load_filters(path)
        review_filters(path, settings, interval_hours)

        print("\n[Y] Proceed with screening")
        print("[E] Edit filter CSV and reload")
        print("[N] Cancel")

        choice = input("Select [Y/E/N]: ").strip().lower()

        if choice in ("y", "yes"):
            return settings

        if choice in ("n", "no"):
            print("ASR-DBG: Node screening cancelled.")
            return None


        if choice == "e":
            print("\nEdit the filter CSV using your preferred editor:")
            print(f"  {path.resolve()}")
            print("\nSave and close the file before continuing.")

            input("\nPress Enter after completing your edits...")

            print("\nReloading screening parameters...")
            continue

        print("Invalid selection. Enter Y, E, or N.")

# ------------------------------------------------------------------------------
# select_filter_path()
# Selects the default or an alternate filter configuration.
# ------------------------------------------------------------------------------
def select_filter_path(default_path: Path) -> Path:
    print("\nERCOT7k Node Screening")
    print("CLI help: python ercot7k_node_screen.py -h")
    print(f"\nDefault filter CSV:\n  {default_path.resolve()}")

    alternate = input(
        "\nPress Enter to use this file, or enter an alternate CSV path: "
    ).strip().strip('"')

    return Path(alternate).expanduser().resolve() if alternate else default_path.resolve()

# ------------------------------------------------------------------------------
# load_balance_prices()
# ------------------------------------------------------------------------------
def load_balance_prices(path: Path, cycle: str, scenario: str) -> dict:
    prices = {}
    areas = set()
    for row in read_rows(path):
        if row["cyc"] != cycle or row["scn"] != scenario:
            continue
        areas.add(row["ara"])
        if row["ara"] != "0":
            continue
        interval = row["int"]
        if interval in prices:
            raise ValueError(f"Duplicate area balance price at interval {interval}")
        prices[interval] = float(row["BalancePrice"])
    if not prices:
        raise ValueError(f"No area 0 balance prices for {cycle}/{scenario}; available areas: {sorted(areas)}")
    return prices


# ------------------------------------------------------------------------------
# load_coordinates()
# ------------------------------------------------------------------------------
def load_coordinates(path: Path) -> dict:
    coords = {}
    for row in read_rows(path):
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (ValueError, TypeError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            coords[row["enode"]] = (lat, lon, row.get("zone", ""))
    return coords

# ------------------------------------------------------------------------------
# read_interval_hours()
# Converts the ERCOT7k model interval length into physical hours.
# ------------------------------------------------------------------------------
def read_interval_hours(model_path: Path) -> float:
    rows = list(read_rows(model_path))

    if len(rows) != 1:
        raise ValueError(
            f"Expected one model metadata row in {model_path}; "
            f"found {len(rows)}"
        )

    row = rows[0]

    try:
        length = float(row["IntervalLength"])
        unit = row["TimeUnit"].strip().lower()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Cannot read TimeUnit/IntervalLength from {model_path}: {exc}"
        ) from exc

    factors = {
        "minute": 1.0 / 60.0,
        "minutes": 1.0 / 60.0,
        "min": 1.0 / 60.0,
        "hour": 1.0,
        "hours": 1.0,
        "hr": 1.0,
        "day": 24.0,
        "days": 24.0,
    }

    if unit not in factors:
        raise ValueError(
            f"Unsupported model TimeUnit {unit!r}; "
            "interval duration cannot be verified"
        )

    hours = length * factors[unit]

    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("Model interval duration must be positive and finite")

    return hours

# ------------------------------------------------------------------------------
# screen_nodes()
# Streams nodal rows, retaining only running aggregates per node.
# ------------------------------------------------------------------------------
def screen_nodes(
    results_dir: Path,
    filters: dict,
    coords: dict,
    interval_hours: float,
) -> tuple[list[dict], dict]:

    area = load_balance_prices(results_dir / "results_ED_Ara.csv", filters["cycle"], filters["scenario"])
    stats = defaultdict(lambda: {"count": 0, "sum_abs": 0.0, "max_abs": 0.0,
                                 "min_signed": float("inf"), "max_signed": float("-inf"),
                                 "stress": 0, "min_lmp": float("inf"), "max_lmp": float("-inf")})
    seen = set()
    skipped_intervals = 0
    for row in read_rows(results_dir / "results_PC_Nd.csv"):
        if row["cyc"] != filters["cycle"] or row["scn"] != filters["scenario"]:
            continue
        node, interval = row["nd"], row["int"]
        if node.startswith("Reference_") or node not in coords:
            continue
        if interval not in area:
            skipped_intervals += 1
            continue
        key = (node, interval)
        if key in seen:
            raise ValueError(f"Duplicate nodal price for {node} interval {interval}")
        seen.add(key)
        lmp = float(row["LMP"])
        if not math.isfinite(lmp):
            continue
        spread = lmp - area[interval]
        magnitude = abs(spread)
        s = stats[node]
        s["count"] += 1
        s["sum_abs"] += magnitude
        s["max_abs"] = max(s["max_abs"], magnitude)
        s["min_signed"] = min(s["min_signed"], spread)
        s["max_signed"] = max(s["max_signed"], spread)
        s["stress"] += magnitude >= filters["spread_threshold"]
        s["min_lmp"] = min(s["min_lmp"], lmp)
        s["max_lmp"] = max(s["max_lmp"], lmp)

    rows = []
    for node, s in stats.items():
        stress_hours = s["stress"] * interval_hours
        if not s["count"] or stress_hours < filters["min_stress_hours"]:
            continue
        # LMP limits apply to the node's full selected-cycle range.
        if s["min_lmp"] < filters["min_lmp"] or s["max_lmp"] > filters["max_lmp"]:
            continue
        lat, lon, zone = coords[node]
        mean_abs = s["sum_abs"] / s["count"]
        rows.append({"node": node, "lat": lat, "lon": lon, "zone": zone,
                     "intervals": s["count"], "min_lmp": round(s["min_lmp"], 4),
                     "max_lmp": round(s["max_lmp"], 4),
                     "max_spread": round(s["max_abs"], 4),
                     "mean_spread": round(mean_abs, 4),
                     "stress_hours": round(stress_hours, 4),
                     "min_signed_spread": round(s["min_signed"], 4),
                     "max_signed_spread": round(s["max_signed"], 4)})
    metric = filters["ranking_metric"]
    rows.sort(key=lambda r: (-r[metric], r["node"]))
    for rank, row in enumerate(rows[:filters["top_n"]], 1):
        row["rank"] = rank
    return rows[:filters["top_n"]], {"area_intervals": len(area), "nodes_observed": len(stats),
                                     "skipped_unmatched_intervals": skipped_intervals}

# ------------------------------------------------------------------------------
# select_geo_path()
# Confirms or changes the geographic coordinate CSV.
# ------------------------------------------------------------------------------
def select_geo_path(default_path: Path) -> Path | None:
    print("\n" + "-" * 80)
    print("ERCOT7k Geographic Coordinate Source")
    print(f"Default/selected Geo CSV:\n  {default_path.resolve()}")

    while True:
        choice = input(
            "\n[Y] Accept  [C] Change path/filename  [N] Cancel: "
        ).strip().lower()

        if choice in ("y", "yes", ""):
            selected = default_path.resolve()

        elif choice == "c":
            value = input(
                "Enter geographic CSV path: "
            ).strip().strip('"')

            if not value:
                continue

            selected = Path(value).expanduser().resolve()

        elif choice in ("n", "no"):
            return None

        else:
            print("Invalid selection.")
            continue

        if not selected.is_file():
            print(f"ASR-ERR: Geographic CSV not found:\n  {selected}")
            continue

        if selected.suffix.lower() != ".csv":
            print("ASR-ERR: Geographic source must be a CSV file.")
            continue

        print(f"\nSelected geographic CSV:\n  {selected}")
        return selected

# ------------------------------------------------------------------------------
# select_output_path()
# Confirms or changes the ranked-node output CSV destination.
# ------------------------------------------------------------------------------
def select_output_path(default_path: Path) -> Path | None:
    print("\n" + "-" * 80)
    print("ERCOT7k Ranked Node Output")
    print(f"Default output:\n  {default_path.resolve()}")

    while True:
        choice = input(
            "\n[Y] Accept  [C] Change path/filename  [N] Cancel: "
        ).strip().lower()

        if choice in ("y", "yes", ""):
            selected = default_path.resolve()

        elif choice == "c":
            value = input(
                "Enter full output CSV path: "
            ).strip().strip('"')

            if not value:
                continue

            selected = Path(value).expanduser().resolve()

        elif choice in ("n", "no"):
            return None

        else:
            print("Invalid selection.")
            continue

        if selected.suffix.lower() != ".csv":
            print("ASR-ERR: Output filename must end with .csv")
            continue

        if selected.exists():
            answer = input(
                f"\nFile already exists:\n  {selected}\n"
                "Overwrite? [Y/N]: "
            ).strip().lower()

            if answer not in ("y", "yes"):
                continue

        print(f"\nSelected output:\n  {selected}")
        return selected

# ------------------------------------------------------------------------------
# main()
# Selects inputs, validates filters, screens nodes, and writes ranked output.
# ------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rank ERCOT7k baseline nodes by LMP separation"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--run",
        help="Run directory name under ercot7k-runs/"
    )
    group.add_argument(
        "--results",
        type=Path,
        help="Direct path to PSO results/ directory"
    )

    parser.add_argument(
        "--filters",
        type=Path,
        default=DEFAULT_FILTERS,
        metavar="CSV_PATH",
        help=f"Node screening filter CSV (default: {DEFAULT_FILTERS})",
    )

    parser.add_argument(
        "--geo",
        type=Path,
        default=DEFAULT_GEO,
        metavar="CSV_PATH",
        help=f"Geographic coordinate CSV (default: {DEFAULT_GEO})",
    )

    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        metavar="CSV_PATH",
        help=f"PSO model metadata CSV (default: {DEFAULT_MODEL})",
    )

    parser.add_argument(
        "--out",
        type=Path,
        help="Output CSV path (default: parent of results/)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive mode; use supplied filter CSV without prompts"
    )

    args = parser.parse_args()

    results_dir = (
        ROOT / "ercot7k-runs" / args.run / "results"
        if args.run else args.results
    ).resolve()

    output = (
        args.out or results_dir.parent / "ercot7k_node_ranked.csv"
    ).resolve()

    try:
        print("\nERCOT7k Node Screening")
        print(f"Results directory:\n  {results_dir}")

        for name in ("results_PC_Nd.csv", "results_ED_Ara.csv"):
            if not (results_dir / name).is_file():
                raise FileNotFoundError(
                    f"Missing PSO result: {results_dir / name}"
                )

        interval_hours = read_interval_hours(args.model)

        if args.yes:
            filter_path = args.filters.expanduser().resolve()
            filters = load_filters(filter_path)
            review_filters(filter_path, filters, interval_hours)
        else:
            filter_path = select_filter_path(args.filters)
            filters = confirm_filters(filter_path, interval_hours)

            if filters is None:
                return 0

        geo_path = args.geo.expanduser().resolve()

        if not args.yes:
            geo_path = select_geo_path(geo_path)

            if geo_path is None:
                print("\nASR-DBG: Geographic selection cancelled.")
                return 0

        coords = load_coordinates(geo_path)

        if not coords:
            raise ValueError("No valid geographic coordinates found")

        print("\nASR-DBG: Screening ERCOT7k nodes...")

        ranked, summary = screen_nodes(
            results_dir,
            filters,
            coords,
            interval_hours,
        )

        if not ranked:
            raise ValueError(
                "No nodes passed screening; adjust filter thresholds"
            )

        if not args.yes:
            output = select_output_path(output)

            if output is None:
                print("\nASR-DBG: Output generation cancelled.")
                return 0

        output.parent.mkdir(parents=True, exist_ok=True)

        columns = [
            "rank", "node", "lat", "lon", "zone",
            "intervals", "min_lmp", "max_lmp",
            "max_spread", "mean_spread", "stress_hours",
            "min_signed_spread", "max_signed_spread",
        ]

        with output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(ranked)

        print(f"\nASR-DBG::Cycle/scenario: {filters['cycle']}/{filters['scenario']}")
        print(
            f"ASR-DBG::Ranking: {filters['ranking_metric']}; "
            f"threshold: {filters['spread_threshold']} $/MWh"
        )
        print(
            f"ASR-DBG::Interval duration: {interval_hours:g} hours"
        )
        print(
            f"ASR-DBG::Area intervals: {summary['area_intervals']}; "
            f"nodes observed: {summary['nodes_observed']}"
        )
        print(
            f"ASR-DBG::Ranked nodes: {len(ranked)}; \n"
            f"\toutput: {output}"
        )

        return 0

    except (OSError, ValueError, KeyError) as exc:
        print(f"\nASR-ERR: Node screening failed: {exc}")
        return 1

    except (KeyboardInterrupt, EOFError):
        print("\nASR-DBG: User interrupted node screening.")
        return 130

# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    raise SystemExit(main())

# ------------------------------------------------------------------------------
# END OF ercot7k_node_screen.py
# ------------------------------------------------------------------------------
