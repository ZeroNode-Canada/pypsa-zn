#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 ZeroNode
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# devnet_stress.py
# 
# Congestion/LMP stress harness for DevNet:
# - Stress knobs: bus load multiplier, corridor capacity reducer, bus gen marginal cost
# - Optional datacenter overlay modes (grid-only, partial BYOG, off-grid)
# - Outputs: objective, LMPs, line loadings, binding indicators
# 
# Usage examples:
#   python devnet_stress.py --net ./devnet-sld --scenario baseline
#   python devnet_stress.py --net ./devnet-sld --scenario sweep_line --line L1 --kmin 1.0 --kmax 0.2 --kstep -0.1

# Run: devnet_stress.py
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Datacenter BYOG Modeling — ECON MODE + CES Interpretation
# ------------------------------------------------------------------------------
# BYOG ECON MODE (target state)
# - Datacenter (DC) modeled as:
#     - Fixed load (p_set)
#     - Onsite generation (BYOG) with marginal cost (byog_mc)
# - No artificial split (dc_frac removed in ECON MODE)
# - OPF determines dispatch based on cost:
#     byog_mc < grid_mc → BYOG dispatches (self-supply first, possible export if surplus)
#     byog_mc > grid_mc → Grid supplies DC load, BYOG idle
#
# Key physical constraint:
# - Export / grid participation requires:
#     available BYOG (and storage) > instantaneous DC load
#
# ------------------------------------------------------------------------------
# CES Interpretation (ρ)
# ------------------------------------------------------------------------------
# ρ ≈ 0  (Low substitutability)
# - DC operates in "corner solution" mode:
#     - Either self-supplies (BYOG) OR draws from grid
# - BYOG primarily offsets local load (BTM)
# - No meaningful participation in grid dispatch
# - Condition (practical):
#     byog_mc > grid_mc OR no physical surplus (p_byog ≤ p_set)
#
# ρ ≈ 1  (Moderate substitutability)
# - BYOG can participate in grid dispatch when economical
# - DC self-supplies AND may export surplus
# - Can reduce congestion and LMP spread
# - Condition:
#     byog_mc < grid_mc AND physical surplus exists (p_byog > p_set)
#
# ρ → ∞  (High substitutability / competition)
# - BYOG behaves like grid-scale generation at the node
# - Competes directly with grid supply
# - Can materially set marginal price (LMP) and alter system dispatch
# - Condition:
#     byog_mc < grid_mc AND BYOG capacity built beyond DC needs (system-scale)
#
# ------------------------------------------------------------------------------
# Modeling Notes
# ------------------------------------------------------------------------------
# - Current dc_frac formulation is an analytical control (non-economic split)
# - ECON MODE replaces dc_frac with cost-based dispatch behavior
# - LMP impact occurs only if:
#     - BYOG displaces marginal generation OR
#     - BYOG reduces binding congestion
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Deprecation Note — dc_frac (Analytical Split)
# ------------------------------------------------------------------------------
# The dc_frac construct was introduced as an analytical knob to split BYOG into:
#     (1 - dc_frac) → BTM self-consumption
#     dc_frac       → grid-dispatchable supply
#
# However, this does NOT reflect real economic dispatch behavior:
# - It forces participation rather than letting OPF decide based on cost
# - It can double-count load under stress (k_load applied before netting)
# - It breaks consistency with CES-based interpretation of substitutability
#
# In real systems:
# - Datacenter chooses supply based on marginal cost
# - Grid sees NET load after BTM dispatch
# - No artificial split exists
#
# Therefore:
# - dc_frac should be REMOVED (or retained only for controlled experiments)
# - Replaced by BYOG ECON MODE:
#     → Full load + BYOG generator
#     → Dispatch determined purely by byog_mc vs grid_mc
#
# This aligns with:
# - Real-world behavior
# - CES interpretation (ρ regimes)
# - Correct LMP and congestion response modeling
# ------------------------------------------------------------------------------

import os
import io
import sys
import logging
from datetime import datetime

import argparse
import copy
import json
from pathlib import Path

import math
import numpy as np
import pandas as pd
import pypsa

import html as html_lib

# Global defines
SECTION_SEPARATOR = "="*80 + "\n" # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n" # for print separation

print(SECTION_SEPARATOR)
print("PyPSA DevNet Asymptote finder Script...\n")

# ----- Resolve paths next to this script -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt):
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")

def solve_with_duals(n: pypsa.Network, solver: str = "highs") -> tuple[bool, str]:
    """
    Run optimization and report success/failure.
    Returns (ok, message).
    """
    try:
        n.optimize(solver_name=solver, assign_all_duals=True)
    except Exception as e:
        return (False, f"Solver raised exception: {e}")

    obj = getattr(n, "objective", None)

    # Robust failure detection:
    # - obj is None (common on infeasible)
    # - obj cannot be cast to float
    # - obj is NaN (numpy or python)
    try:
        obj_f = float(obj)
    except Exception:
        return (False, "Optimization failed or infeasible (objective not numeric).")

    if np.isnan(obj_f):
        return (False, "Optimization failed or infeasible (objective is NaN).")

    return (True, "Optimal")

def apply_load_multipliers(n: pypsa.Network, k_load: dict[str, float]) -> None:
    """
    k_load: {bus: multiplier}
    Multiplies loads at each bus by multiplier.
    Works whether loads are stored as static (n.loads.p_set) or time-series (n.loads_t.p_set).
    """
    if n.loads.empty:
        return

    has_ts = hasattr(n, "loads_t") and hasattr(n.loads_t, "p_set") and n.loads_t.p_set is not None
    ts_cols = n.loads_t.p_set.columns if (has_ts and len(getattr(n.loads_t, "p_set", []))) else None

    for bus, k in k_load.items():
        loads_at_bus = n.loads.index[n.loads.bus == bus]
        if len(loads_at_bus) == 0:
            continue

        # Always update static p_set (this exists in your exported devnet)
        if "p_set" in n.loads.columns:
            n.loads.loc[loads_at_bus, "p_set"] = n.loads.loc[loads_at_bus, "p_set"].astype(float) * float(k)

        # Update time-series p_set only if the columns exist
        if has_ts and ts_cols is not None:
            cols = ts_cols.intersection(loads_at_bus)
            if len(cols) > 0:
                n.loads_t.p_set.loc[:, cols] = n.loads_t.p_set.loc[:, cols].astype(float) * float(k)

def apply_corridor_reducers(n: pypsa.Network, k_line: dict[str, float]) -> None:
    """
    k_line: {line_name: multiplier}
    Scales s_nom for target lines.
    """
    for ln, k in k_line.items():
        if ln in n.lines.index:
            n.lines.loc[ln, "s_nom"] = n.lines.loc[ln, "s_nom"] * float(k)

def apply_gen_marginal_cost_by_bus(n: pypsa.Network, mc_bus: dict[str, float], mode: str = "set") -> None:
    """
    mc_bus: {bus: value}
    mode: "set" sets marginal_cost to value, "add" adds value
    """
    if n.generators.empty:
        return

    for bus, v in mc_bus.items():
        gens = n.generators.index[n.generators.bus == bus]
        if len(gens) == 0:
            continue
        if mode == "add":
            n.generators.loc[gens, "marginal_cost"] = n.generators.loc[gens, "marginal_cost"] + float(v)
        else:
            n.generators.loc[gens, "marginal_cost"] = float(v)

# ------------------------------------------------------------------------------
# resolve_dc_csv_values()
# Extracts DC defaults from loaded devnet (loads.csv)
# ------------------------------------------------------------------------------
def resolve_dc_csv_values(devnet):
    dc = {"byog_mc": None, "p_set": None, "p_nom": None}

    if "Load_DC_PJM_NE" in devnet.loads.index:
        try:
            dc["p_set"] = float(devnet.loads.at["Load_DC_PJM_NE", "p_set"])
            dc["p_nom"] = float(devnet.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
            dc["byog_mc"] = float(devnet.loads.at["Load_DC_PJM_NE", "byog_mc"])
        except Exception:
            pass

    return dc

# ------------------------------------------------------------------------------
# collect_results()
# Extracts OPF outputs for a single snapshot:
# - objective value
# - nodal LMPs
# - line loading (per-unit)
# Standardizes results for reporting and downstream analysis
# ------------------------------------------------------------------------------
def collect_results(n: pypsa.Network) -> dict:
    """
    Returns snapshot-0 results (DevNet is usually single snapshot).
    """
    snap = n.snapshots[0]

    out = {
        "snapshot": str(snap),
        "objective": float(getattr(n, "objective", np.nan)) if getattr(n, "objective", None) is not None else np.nan,
    }

    if hasattr(n, "buses_t") and hasattr(n.buses_t, "marginal_price") and not n.buses_t.marginal_price.empty:
        out["lmp"] = n.buses_t.marginal_price.loc[snap].to_dict()
    else:
        out["lmp"] = {}

    if hasattr(n, "lines_t") and hasattr(n.lines_t, "p0") and not n.lines_t.p0.empty and not n.lines.empty:
        loading = (n.lines_t.p0.loc[snap].abs() / n.lines.s_nom).replace([np.inf, -np.inf], np.nan)
        out["line_loading_pu"] = loading.to_dict()
    else:
        out["line_loading_pu"] = {}

    return out

# ------------------------------------------------------------------------------
# write_outputs()
# Writes simulation outputs to disk:
# - JSON summary
# - CSVs for LMP, line loading, and objective
# Ensures consistent artifact structure for dashboards and analysis
# ------------------------------------------------------------------------------
def write_outputs(outdir: Path, tag: str, results: dict) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    with (outdir / f"{tag}.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    if results.get("lmp"):
        pd.Series(results["lmp"], name="lmp").to_csv(outdir / f"{tag}_lmp.csv")

    if results.get("line_loading_pu"):
        pd.Series(results["line_loading_pu"], name="loading_pu").to_csv(outdir / f"{tag}_line_loading_pu.csv")

    pd.Series({"objective": results.get("objective", np.nan)}).to_csv(outdir / f"{tag}_objective.csv")

# ------------------------------------------------------------------------------
# parse_json_dict()
# Utility to safely parse JSON string inputs from CLI/menu into Python dicts
# Used for k_load, k_line, mc_bus configuration inputs
# ------------------------------------------------------------------------------
def parse_json_dict(s: str) -> dict:
    if not s:
        return {}
    return json.loads(s)

# ------------------------------------------------------------------------------
# resolve_byog_mc()
# Determines effective BYOG marginal cost for dispatch:
# - Uses CLI override if provided (--byog_mc)
# - Falls back to loads.csv (default model input)
# Centralizes BYOG cost logic for consistency across runs
# ------------------------------------------------------------------------------
def resolve_byog_mc(n, args):
    if DEVNET_NAME != "devnetDC-sld":
        return None
    mc = float(n.loads.at["Load_DC_PJM_NE", "byog_mc"])
    return float(args.byog_mc) if getattr(args, "byog_mc", None) is not None else mc

# ------------------------------------------------------------------------------
# run_single()
# Executes a single OPF scenario:
# - Applies stress inputs (load, line, marginal cost)
# - Models DC as load + BYOG generator (ECON MODE)
# - Solves OPF and records outputs
# Core execution path for scenario-based analysis
# See BYOG ECON MODE + CES Interpretation (top of file)
# ------------------------------------------------------------------------------
def run_single(n0: pypsa.Network, args: argparse.Namespace, tag: str) -> dict:
    n = copy.deepcopy(n0)

    apply_load_multipliers(n, parse_json_dict(args.k_load))
    apply_corridor_reducers(n, parse_json_dict(args.k_line))
    apply_gen_marginal_cost_by_bus(n, parse_json_dict(args.mc_bus), mode=args.mc_mode)

    if DEVNET_NAME == "devnetDC-sld" and "Load_DC_PJM_NE" in n.loads.index:
        byog_p = float(n.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
        p_set  = float(n.loads.at["Load_DC_PJM_NE", "p_set"])

        # runtime overrides
        if getattr(args, "dc_p_nom", None) is not None:
            byog_p = float(args.dc_p_nom)

        if getattr(args, "dc_p_set", None) is not None:
            p_set = float(args.dc_p_set)
        mc = resolve_byog_mc(n, args)

        # BYOG always available — OPF decides dispatch based on cost and system conditions
        n.add(
            "Generator",
            "Gen_DC_PJM_NE",
            bus="PJM_NE",
            carrier="gas",
            p_nom=byog_p,
            marginal_cost=mc,
        )

    ok, msg = solve_with_duals(n, solver=args.solver)
    if not ok:
        print(f"\nASR-WARN: System cannot be optimized for this configuration.")
        print(f"ASR-WARN: Reason: {msg}\n")

        # IMPORTANT: still write commit artifacts so index.html retains the record
        res = {
            "snapshot": str(n.snapshots[0]),
            "objective": np.nan,
            "lmp": {},
            "line_loading_pu": {},
            "status": "infeasible",
            "reason": msg,
        }
        write_outputs(Path(args.outdir), tag, res)
        return res

    res = collect_results(n)
    write_outputs(Path(args.outdir), tag, res)
    return res

# ------------------------------------------------------------------------------
# run_sweep_line()
# Performs parameter sweep over line capacity:
# - Iteratively modifies corridor limits
# - Runs OPF for each step
# - Captures objective, LMP spread, and congestion metrics
# Used for asymptote and congestion sensitivity analysis
# See BYOG ECON MODE + CES Interpretation (top of file)
# ------------------------------------------------------------------------------
def run_sweep_line(n0: pypsa.Network, args: argparse.Namespace, file_prefix: str = "") -> pd.DataFrame:
    """
    Sweep a single line capacity multiplier and record objective + LMP deltas.
    """
    line = args.line
    k_values = np.arange(args.kmin, args.kmax + 1e-9, args.kstep)

    if len(k_values) == 0:
        raise ValueError(
            f"Empty sweep: check kmin/kmax/kstep. Got kmin={args.kmin}, kmax={args.kmax}, kstep={args.kstep}"
        )

    rows = []
    for k in k_values:
        n = copy.deepcopy(n0)

        lmp_spread = np.nan
        max_loading_pu = np.nan

        apply_load_multipliers(n, parse_json_dict(args.k_load))
        apply_corridor_reducers(n, {line: float(k)})
        apply_gen_marginal_cost_by_bus(n, parse_json_dict(args.mc_bus), mode=args.mc_mode)

        if DEVNET_NAME == "devnetDC-sld" and "Load_DC_PJM_NE" in n.loads.index:
            byog_p = float(n.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
            p_set  = float(n.loads.at["Load_DC_PJM_NE", "p_set"])
            byog_p = float(n.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
            p_set  = float(n.loads.at["Load_DC_PJM_NE", "p_set"])

            # runtime overrides
            if getattr(args, "dc_p_nom", None) is not None:
                byog_p = float(args.dc_p_nom)

            if getattr(args, "dc_p_set", None) is not None:
                p_set = float(args.dc_p_set)
            mc = resolve_byog_mc(n, args)

            # BYOG always available — OPF decides dispatch based on cost and system conditions
            n.add(
                "Generator",
                "Gen_DC_PJM_NE",
                bus="PJM_NE",
                carrier="gas",
                p_nom=byog_p,
                marginal_cost=mc,
            )

        ok, msg = solve_with_duals(n, solver=args.solver)
        if not ok:
            # record failure but keep sweep running
            row = {
                "line": line,
                "k_line": float(k),
                "objective": np.nan,
                "lmp_spread": np.nan,
                "max_loading_pu": np.nan,
                "status": "infeasible",
            }
            rows.append(row)
            continue

        res = collect_results(n)

        lmp_vals = list(res.get("lmp", {}).values())
        if lmp_vals:
            lmp_spread = float(np.nanmax(lmp_vals) - np.nanmin(lmp_vals))

        loading_vals = list(res.get("line_loading_pu", {}).values())
        if loading_vals:
            max_loading_pu = float(np.nanmax(loading_vals))

        row = {
            "line": line,
            "k_line": float(k),
            "objective": res.get("objective", np.nan),
            "lmp_spread": lmp_spread,
            "max_loading_pu": max_loading_pu,
            "status": "ok",
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    fname = f"{file_prefix}sweep_line_summary.csv" if file_prefix else "sweep_line_summary.csv"
    df.to_csv(outdir / fname, index=False)
    return df

# ------------------------------------------------------------------------------
# Menu & Configuration Helpers
# - build_argparser()
# - build_args_catalog()
# - capture_catalog_lines()
# - print_two_columns()
# - prompt_custom_*()
# - configure_args_menu()
# Handles user interaction:
# - scenario selection
# - parameter configuration
# - custom overrides
# Drives interactive research workflow
# ------------------------------------------------------------------------------
def build_argparser(devnet_bld_path: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="baseline", choices=["baseline", "single", "sweep_line"])
    p.add_argument("--solver", default="highs")

    p.add_argument("--outdir", default=os.path.join(devnet_bld_path, "stress_out"))

    p.add_argument("--k_load", default="{}", help='JSON dict: {"BUS1": 1.2, "BUS3": 1.5}')
    p.add_argument("--k_line", default="{}", help='JSON dict: {"LINE1": 0.8, "LINE2": 0.6}')
    p.add_argument("--mc_bus", default="{}", help='JSON dict: {"BUS2": 50, "BUS5": 120}')
    p.add_argument("--mc_mode", default="set", choices=["set", "add"])

    p.add_argument(
        "--byog_mc",
        type=float,
        default=None,
        help="Override datacenter BYOG marginal cost (USD/MWh). Default=None uses loads.csv value",
    )

    p.add_argument("--line", default="", help="Line name for sweep_line scenario.")
    p.add_argument("--kmin", type=float, default=1.0)
    p.add_argument("--kmax", type=float, default=0.2)
    p.add_argument("--kstep", type=float, default=-0.1)
    p.add_argument("--dc_p_set", type=float, default=None, help="Override DC load (MW)")
    p.add_argument("--dc_p_nom", type=float, default=None, help="Override DC BYOG capacity (MW)")    
    return p

def build_args_catalog(devnet: pypsa.Network) -> dict[str, list[str]]:
    bus0 = devnet.buses.index[0] if len(devnet.buses) else "BUS0"
    line0 = devnet.lines.index[0] if len(devnet.lines) else "LINE0"

    # Extract DC defaults from loaded devnet (loads.csv) for contextual display in menu
    dc_csv = resolve_dc_csv_values(devnet)

    return {
        "scenario": ["baseline", "single", "sweep_line"],
        "mc_mode": ["set", "add"],
        "k_load": [
            "{}",
            json.dumps({bus0: 1.2}),
            json.dumps({bus0: 1.5}),
            json.dumps({b: 1.2 for b in devnet.buses.index}) if len(devnet.buses) else "{}",
            "__CUSTOM__",   # option 5
        ],
        "k_line": [
            "{}",
            json.dumps({line0: 0.8}),
            json.dumps({line0: 0.6}),
            json.dumps({line0: 0.5}),
            "__CUSTOM__",   # option 5
        ],
        "mc_bus": [
            "{}",
            json.dumps({bus0: 70}),
            json.dumps({bus0: 100}),
            "__CUSTOM__",   # custom per-bus MC like k_line / k_load
        ],
        "line": (list(devnet.lines.index[:6]) if len(devnet.lines) else [""]) + ["<manual>"],
        "kmin": ["1.0", "0.9", "0.8"],
        "kmax": ["0.5", "0.4", "0.3", "0.2"],
        "kstep": ["-0.1", "-0.05", "-0.02"],

        # Set BYOG and DC load presets based on CSV values for contextual relevance
        "byog_mc": [f"CSV Preset = {dc_csv['byog_mc']}", 45.0, 50.0, 60.0, "__CUSTOM__"],
        "dc_p_set": [f"CSV Preset = {dc_csv['p_set']}", 1000.0, 2000.0, "__CUSTOM__"],
        "dc_p_nom": [f"CSV Preset = {dc_csv['p_nom']}", 1000.0, 2000.0, "__CUSTOM__"],
    }

def capture_catalog_lines(catalog: dict[str, list[str]]) -> list[str]:
    """
    Capture the same content as print_args_catalog_table(), but as a list of strings.
    (So we can render it as the left column.)
    """
    out = []
    out.append(SECTION_SEPARATOR.rstrip("\n"))
    out.append("Configurable args + menu values (catalog)")
    out.append(SUBSECTION_SEPARATOR.rstrip("\n"))

    col1 = 12
    col2 = 92

    def clip(s: str, n: int) -> str:
        s = str(s)
        return s if len(s) <= n else s[: n - 3] + "..."

    header = f"{'arg':<{col1}} | {'menu values':<{col2}}"
    out.append(header)
    out.append("-" * len(header))

    for arg, opts in catalog.items():
        if arg in ("k_load", "k_line"):
            out.append(f"{arg:<{col1}} | {opts[0]}")
            for o in opts[1:]:
                out.append(f"{'':<{col1}} | {o}")
            continue

        joined = " ; ".join([clip(o, 60) for o in opts])
        out.append(f"{arg:<{col1}} | {clip(joined, col2)}")

    out.append(SECTION_SEPARATOR.rstrip("\n"))
    return out

def print_two_columns(left: list[str], right: list[str], left_width: int = 95, gap: int = 4) -> None:
    n = max(len(left), len(right))
    left_pad = " " * gap

    # Detect the values-column start from the header line: "arg | menu values"
    values_start = None
    for ln in left:
        if " | " in ln and ln.strip().startswith("arg"):
            values_start = ln.find(" | ") + 3
            break
    if values_start is None:
        values_start = 0

    def _wrap_with_indent(s: str, width: int, indent: int) -> list[str]:
        s = s or ""
        if len(s) <= width:
            return [s]
        first = s[:width]
        rest = s[width:]
        chunks = [first]
        # subsequent chunks start under the values column
        while rest:
            chunk = (" " * indent) + rest[: max(0, width - indent)]
            rest = rest[max(0, width - indent):]
            chunks.append(chunk)
        return chunks

    for i in range(n):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""

        l_chunks = _wrap_with_indent(l, left_width, values_start)

        # first chunk prints with right column
        print(f"{l_chunks[0]:<{left_width}}{left_pad}{r}")

        # extra chunks print with blank right column
        for extra in l_chunks[1:]:
            print(f"{extra:<{left_width}}{left_pad}")

def prompt_custom_k_load(devnet: pypsa.Network) -> dict[str, float]:
    """
    Prompt per-bus load multipliers. Default=1.0 (no change).
    Returns dict {bus: multiplier} with only entries != 1.0.
    """
    print("\nCustom k_load (per-bus load multiplier). Enter multiplier (e.g., 1.2, 1.5, 2.0). Default=1.0\n")
    out = {}
    for b in devnet.buses.index:
        s = input(f"  {b} [default=1.0]: ").strip()
        if not s:
            continue
        try:
            v = float(s)
            if v <= 0:
                print("    Invalid; must be > 0. Skipped.")
                continue
            if v != 1.0:
                out[b] = v
        except Exception:
            print("    Invalid number. Skipped.")
    return out

def prompt_custom_k_line(devnet: pypsa.Network) -> dict[str, float]:
    """
    Prompt per-line derating. Default=1.0 (no derate).
    Returns dict {line: multiplier} with only entries != 1.0.
    """
    print("\nCustom k_line (per-line derating). Enter derating factor (e.g., 0.8, 0.6, 0.4). Default=1.0\n")
    out = {}
    for ln in devnet.lines.index:
        s = input(f"  {ln} [default=1.0]: ").strip()
        if not s:
            continue
        try:
            v = float(s)
            if v <= 0 or v > 1.0:
                print("    Invalid; must be in (0,1]. Skipped.")
                continue
            if v != 1.0:
                out[ln] = v
        except Exception:
            print("    Invalid number. Skipped.")
    return out

def prompt_custom_mc_bus(devnet: pypsa.Network) -> dict[str, float]:
    """
    Prompt per-bus generator marginal cost values (USD/MWh).
    Blank means "no override" for that bus.
    Returns dict {bus: marginal_cost_value}.
    Notes:
      - Applied to all generators at that bus by apply_gen_marginal_cost_by_bus().
      - Use mc_mode='set' to replace, 'add' to add an increment.
    """
    print(
        "\nCustom mc_bus (per-bus generator marginal cost). "
        "Enter USD/MWh (e.g., 40, 50, 70). Blank = no change for that bus.\n"
    )
    out: dict[str, float] = {}
    for b in devnet.buses.index:
        s = input(f"  {b} [blank=no change]: ").strip()
        if not s:
            continue
        try:
            out[b] = float(s)
        except Exception:
            print("    Invalid number. Skipped.")
    return out

def _pick_from_menu(title: str, options: list[str], default_idx: int = 0) -> str:
    """
    Compact picker: does NOT print option values.
    Assumes the catalog table above shows values.
    """
    opt_range = ",".join(str(i) for i in range(1, len(options) + 1))
    prompt = f"{title}[{opt_range}] <Enter selection> (default={default_idx + 1}): "
    s = input(prompt).strip()

    if not s:
        return options[default_idx]

    try:
        k = int(s)
        if 1 <= k <= len(options):
            return options[k - 1]
    except Exception:
        pass

    print("Invalid selection; using default.")
    return options[default_idx]

def configure_args_menu(devnet: pypsa.Network, args: argparse.Namespace) -> argparse.Namespace:
    print("\nSelection arg configuration values:\n")

    # Use a single catalog so option counts always match what you printed at top.
    catalog = build_args_catalog(devnet)

    # --- scenario ---
    opts = catalog["scenario"]
    args.scenario = _pick_from_menu(
        "Scenario",
        opts,
        default_idx=opts.index(args.scenario) if args.scenario in opts else 0
    )

    # --- mc_mode ---
    opts = catalog["mc_mode"]
    args.mc_mode = _pick_from_menu(
        "Generator marginal cost mode (mc_mode)",
        opts,
        default_idx=opts.index(args.mc_mode) if args.mc_mode in opts else 0
    )

    # --- k_load ---
    opts = catalog["k_load"]
    sel_load = _pick_from_menu(
        "Per-bus load multiplier preset (k_load)",
        opts,
        default_idx=opts.index(args.k_load) if args.k_load in opts else 0
    )

    if sel_load == "__CUSTOM__":
        custom_load = prompt_custom_k_load(devnet)
        args.k_load = json.dumps(custom_load) if custom_load else "{}"
        if custom_load:
            print("\nCustom k_load set:")
            for b, v in custom_load.items():
                print(f"  {b}: {v}")
    else:
        args.k_load = sel_load

    # --- k_line ---
    opts = catalog["k_line"]
    sel = _pick_from_menu(
        "Per-line capacity reducer preset (k_line)",
        opts,
        default_idx=opts.index(args.k_line) if args.k_line in opts else 0
    )

    if sel == "__CUSTOM__":
        custom = prompt_custom_k_line(devnet)
        args.k_line = json.dumps(custom) if custom else "{}"
        # echo custom config
        if custom:
            print("\nCustom k_line set:")
            for ln, v in custom.items():
                print(f"  {ln}: {v}")
    else:
        args.k_line = sel

    # --- mc_bus ---
    opts = catalog["mc_bus"]
    sel_mc = _pick_from_menu(
        "Per-bus generator marginal cost preset (mc_bus)",
        opts,
        default_idx=opts.index(args.mc_bus) if args.mc_bus in opts else 0
    )

    if sel_mc == "__CUSTOM__":
        custom_mc = prompt_custom_mc_bus(devnet)
        args.mc_bus = json.dumps(custom_mc) if custom_mc else "{}"
        if custom_mc:
            print("\nCustom mc_bus set:")
            for b, v in custom_mc.items():
                print(f"  {b}: {v}")
    else:
        args.mc_bus = sel_mc

    # --- Datacenter BYOG marginal cost override ---
    opts = catalog.get("byog_mc", ["CSV_PRESET"])  # fallback to just CSV_PRESET if not in catalog for some reason
    choice = _pick_from_menu(
        "Datacenter BYOG marginal cost override (CSV Preset = use loads.csv)",
        opts,
        default_idx=0
    )
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.byog_mc = None
    elif choice == "__CUSTOM__":
        args.byog_mc = float(input("Enter custom BYOG MC (USD/MWh): ").strip())
    else:
        args.byog_mc = float(choice)
    
    # --- DC load override ---
    opts = catalog.get("dc_p_set", ["CSV Preset"])
    choice = _pick_from_menu("Datacenter load override (MW)", opts, default_idx=0)
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.dc_p_set = None
    elif choice == "__CUSTOM__":
        args.dc_p_set = float(input("Enter DC load (MW): ").strip())
    else:
        args.dc_p_set = float(choice)

    # --- DC BYOG capacity override ---
    opts = catalog.get("dc_p_nom", ["CSV Preset"])
    choice = _pick_from_menu("Datacenter BYOG capacity override (MW)", opts, default_idx=0)
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.dc_p_nom = None
    elif choice == "__CUSTOM__":
        args.dc_p_nom = float(input("Enter BYOG capacity (MW): ").strip())
    else:
        args.dc_p_nom = float(choice)

    # --- sweep_line specific fields ---
    if args.scenario == "sweep_line":
        opts = catalog["line"]
        chosen = _pick_from_menu("Sweep target line (line)", opts, default_idx=0)
        if chosen == "<manual>":
            args.line = input("line <manual>: ").strip()
        else:
            args.line = chosen

        opts = catalog["kmin"]
        args.kmin = float(_pick_from_menu("kmin", opts, default_idx=0))

        opts = catalog["kmax"]
        args.kmax = float(_pick_from_menu("kmax", opts, default_idx=len(opts) - 1))

        opts = catalog["kstep"]
        args.kstep = float(_pick_from_menu("kstep", opts, default_idx=0))

    else:
        args.line = ""
        args.kmin, args.kmax, args.kstep = 1.0, 0.2, -0.1

    # Ordered print of final configured args for confirmation before run
    ordered_keys = [
        "scenario",
        "mc_mode",
        "k_load",
        "k_line",
        "mc_bus",
        "line",
        "kmin",
        "kmax",
        "kstep",
        "byog_mc",
        "dc_p_set",
        "dc_p_nom",
    ]
    print("\nASR-DBG::Configured args (menu):")
    for k in ordered_keys:
        if hasattr(args, k):
            print(f"\t\t{k:12s} = {getattr(args, k)}")

    input("\nARGS OK? Press Enter to run...\n")
    return args

# ------------------------------------------------------------------------------
# Dashboard Helpers
# - _dashboard_from_single()
# - _dashboard_from_sweep()
# - dashboard_text()
# Aggregate and format results into compact summaries:
# - objective
# - LMP spread
# - congestion indicators
# Used for console output and HTML reporting
# ------------------------------------------------------------------------------
def _dashboard_from_single(res: dict) -> dict:
    # objective
    obj = float(res.get("objective", np.nan))

    # LMP stats
    lmp = res.get("lmp", {}) or {}
    lmp_vals = np.array(list(lmp.values()), dtype=float) if len(lmp) else np.array([])
    lmp_spread = float(np.nanmax(lmp_vals) - np.nanmin(lmp_vals)) if lmp_vals.size else np.nan
    max_lmp_bus = max(lmp, key=lambda b: float(lmp[b])) if len(lmp) else ""
    max_lmp = float(lmp[max_lmp_bus]) if max_lmp_bus else np.nan

    # Loading stats
    loading = res.get("line_loading_pu", {}) or {}
    loading_vals = np.array(list(loading.values()), dtype=float) if len(loading) else np.array([])
    max_loading_pu = float(np.nanmax(loading_vals)) if loading_vals.size else np.nan
    max_loading_line = max(loading, key=lambda ln: float(loading[ln])) if len(loading) else ""
    near_bind_ct = int(np.sum(loading_vals >= 0.95)) if loading_vals.size else 0

    # top 3 lines by loading (for a compact “feel” of stress)
    top_lines = []
    if len(loading):
        top_lines = sorted(loading.items(), key=lambda kv: float(kv[1]), reverse=True)[:3]

    return {
        "objective": obj,
        "lmp_spread": lmp_spread,
        "max_lmp_bus": max_lmp_bus,
        "max_lmp": max_lmp,
        "max_loading_pu": max_loading_pu,
        "max_loading_line": max_loading_line,
        "near_bind_ct": near_bind_ct,
        "top_lines": top_lines,
    }

def _dashboard_from_sweep(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"empty": True}

    # min/max objective
    obj_min = float(df["objective"].min()) if "objective" in df.columns else np.nan
    obj_max = float(df["objective"].max()) if "objective" in df.columns else np.nan

    # max lmp_spread and where it happens
    lmp_spread_max = float(df["lmp_spread"].max()) if "lmp_spread" in df.columns else np.nan
    if "lmp_spread" in df.columns and df["lmp_spread"].notna().any():
        idx = int(df["lmp_spread"].idxmax())
        k_at = float(df.loc[idx, "k_line"])
    else:
        k_at = np.nan

    # first k where loading reaches threshold
    k_first_bind = np.nan
    if "max_loading_pu" in df.columns and "k_line" in df.columns:
        hit = df[df["max_loading_pu"] >= 0.95]
        if not hit.empty:
            k_first_bind = float(hit.iloc[0]["k_line"])

    return {
        "objective_min": obj_min,
        "objective_max": obj_max,
        "lmp_spread_max": lmp_spread_max,
        "k_at_lmp_spread_max": k_at,
        "k_first_near_bind": k_first_bind,
        "empty": False,
    }

def dashboard_text(args: argparse.Namespace, mode: str, dash: dict) -> str:
    """
    Returns the same dashboard you print to console, as a single string.
    mode examples: "PREVIEW" or "COMMIT::c3"
    """
    lines = []
    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    lines.append(f"ASR-DASH::{mode}::{args.scenario}")
    lines.append(SUBSECTION_SEPARATOR.rstrip("\n"))

    # Extract DC defaults from loaded devnet (loads.csv) for contextual display in menu
    dc_csv = resolve_dc_csv_values(devnet)

    # args summary (include key config values for context)
    dc_mc = getattr(args, "byog_mc", None)
    dc_p_set = getattr(args, "dc_p_set", None)
    dc_p_nom = getattr(args, "dc_p_nom", None)

    # DC-related fields:: if:arg is None::CSV preset value; Else::show the override value.
    dc_p_set_str = f"CSV Preset::{dc_csv['p_set']}" if dc_p_set is None else dc_p_set
    dc_p_nom_str = f"CSV Preset::{dc_csv['p_nom']}" if dc_p_nom is None else dc_p_nom
    dc_mc_str    = f"CSV Preset::{dc_csv['byog_mc']}" if dc_mc is None else dc_mc

    lines.append(
        f"args: scenario={args.scenario}  mc_mode={args.mc_mode}  line={args.line or '-'}  "
        f"k_load={args.k_load}  k_line={args.k_line}  mc_bus={args.mc_bus}  "
        f"byog_mc={dc_mc_str}  dc_p_set={dc_p_set_str}  dc_p_nom={dc_p_nom_str}"
    )

    if args.scenario in ("baseline", "single"):
        lines.append(f"objective        : {dash['objective']:.3e}")
        lines.append(f"lmp_spread       : {dash['lmp_spread']:.3f}   max_lmp: {dash['max_lmp']:.3f} @ {dash['max_lmp_bus']}")
        lines.append(f"max_loading_pu   : {dash['max_loading_pu']:.3f} @ {dash['max_loading_line']}")
        lines.append(f"near_bind_ct(>=.95): {dash['near_bind_ct']}")
        if dash.get("top_lines"):
            tl = " | ".join([f"{ln}:{float(u):.2f}" for ln, u in dash["top_lines"]])
            lines.append(f"top_lines        : {tl}")

    elif args.scenario == "sweep_line":
        if dash.get("empty", False):
            lines.append("sweep: EMPTY (check kmin/kmax/kstep)")
        else:
            lines.append(f"objective(min/max): {dash['objective_min']:.3e} / {dash['objective_max']:.3e}")
            lines.append(f"lmp_spread_max    : {dash['lmp_spread_max']:.3f} @ k_line={dash['k_at_lmp_spread_max']}")
            lines.append(f"first_near_bind_k : {dash['k_first_near_bind']}")
            lines.append("sweep output      : sweep_line_summary.csv")

    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    return "\n".join(lines) + "\n"

# ------------------------------------------------------------------------------
# DevNet Sanity & Base Parameter Helpers
# - devnet_base_params()
# - build_sanity_panel_lines()
#
# Extracts and presents core network characteristics for validation:
# - Base parameters (bus count, generator marginal cost, line capacity)
# - Datacenter BYOG marginal cost (from loads.csv if present)
# - System-wide adequacy (generation vs load)
# - Per-bus supply/demand balance (surplus / deficit)
#
# Provides a quick, structured snapshot of the network state to:
# - validate input data integrity
# - understand baseline system conditions
# - contextualize stress test results
# ------------------------------------------------------------------------------
def devnet_base_params(devnet: pypsa.Network) -> dict:
    """
    Extract base network parameters for documentation:
      - Buses_N
      - base marginal cost (USD/MWh) from generator CSV
      - base line s_nom (MW) from line CSV

    Notes:
      - Uses the loaded CSV network devnet = pypsa.Network(DEVNET_BLD_PATH)
      - For marginal cost: returns a single representative value.
        If multiple unique values exist, returns the minimum and flags it.
      - For line s_nom: returns a single representative value.
        If multiple unique values exist, returns the minimum and flags it.
    """
    buses_n = int(len(devnet.buses.index)) if hasattr(devnet, "buses") else 0

    # Generator marginal cost(s)
    if len(devnet.generators) and "marginal_cost" in devnet.generators.columns:
        mc_vals = pd.to_numeric(devnet.generators["marginal_cost"], errors="coerce").dropna().values
        mc_unique = np.unique(mc_vals) if mc_vals.size else np.array([])
        if mc_unique.size == 0:
            mc_repr = np.nan
            mc_note = "mc: missing"
        elif mc_unique.size == 1:
            mc_repr = float(mc_unique[0])
            mc_note = ""
        else:
            # If heterogeneous, pick min as “base” and note heterogeneity
            mc_repr = float(np.nanmin(mc_unique))
            mc_note = f"(multiple mc values; showing min of {mc_unique.size})"
    else:
        mc_repr = np.nan
        mc_note = "mc: missing"

    # Line s_nom(s)
    if len(devnet.lines) and "s_nom" in devnet.lines.columns:
        sn_vals = pd.to_numeric(devnet.lines["s_nom"], errors="coerce").dropna().values
        sn_unique = np.unique(sn_vals) if sn_vals.size else np.array([])
        if sn_unique.size == 0:
            sn_repr = np.nan
            sn_note = "s_nom: missing"
        elif sn_unique.size == 1:
            sn_repr = float(sn_unique[0])
            sn_note = ""
        else:
            # If heterogeneous, pick min as representative and note heterogeneity
            sn_repr = float(np.nanmin(sn_unique))
            sn_note = f"(multiple s_nom values; showing min of {sn_unique.size})"
    else:
        sn_repr = np.nan
        sn_note = "s_nom: missing"

    return {
        "buses_n": buses_n,
        "mc_repr": mc_repr,
        "mc_note": mc_note,
        "s_nom_repr": sn_repr,
        "s_nom_note": sn_note,
    }

def build_sanity_panel_lines(devnet: pypsa.Network) -> list[str]:
    # Base parameters (for self-contained test case docs)
    base = devnet_base_params(devnet)

    # System-wide adequacy
    total_gen = float(devnet.generators["p_nom"].sum()) if len(devnet.generators) else 0.0
    total_load = float(devnet.loads["p_set"].sum()) if len(devnet.loads) else 0.0
    adequate = "YES" if total_gen >= total_load else "NO"

    lines = []
    lines.append("")  # align with left header line

    # Base DevNet params (before adequacy block)
    lines.append("DevNet base params:")
    lines.append(f"  Buses_N            = {base['buses_n']}")

    # --- Datacenter BYOG MC (from loads.csv if present) ---
    dc_mc = None
    if "byog_mc" in devnet.loads.columns:
        dc_rows = devnet.loads[devnet.loads.index.str.contains("DC", case=False, na=False)]
        if not dc_rows.empty:
            try:
                dc_mc = float(dc_rows["byog_mc"].iloc[0])
            except Exception:
                dc_mc = None

    # --- Datacenter p_set / p_nom ---
    dc_p_set = None
    dc_p_nom = None

    if "Load_DC_PJM_NE" in devnet.loads.index:
        try:
            dc_p_set = float(devnet.loads.at["Load_DC_PJM_NE", "p_set"])
            dc_p_nom = float(devnet.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
        except Exception:
            pass

    if dc_p_set is not None and dc_p_nom is not None:
        lines.append(f"  dc_p_set (MW)        = {dc_p_set:.1f}")
        lines.append(f"  dc_p_nom (MW)        = {dc_p_nom:.1f}")
    else:
        lines.append(f"  dc_p_set / p_nom     = n/a")

    if dc_mc is not None:
        lines.append(f"  dc_byog_mc (USD/MWh) = {dc_mc:.2f} [loads.csv]")
    else:
        lines.append(f"  dc_byog_mc (USD/MWh) = n/a")

    if not np.isnan(base["mc_repr"]):
        lines.append(f"  c_g (USD/MWh)      = {base['mc_repr']:.2f} {base['mc_note']}".rstrip())
    else:
        lines.append(f"  c_g (USD/MWh)      = (missing) {base['mc_note']}".rstrip())
    if not np.isnan(base["s_nom_repr"]):
        lines.append(f"  line s_nom (MW)    = {base['s_nom_repr']:.1f} {base['s_nom_note']}".rstrip())
    else:
        lines.append(f"  line s_nom (MW)    = (missing) {base['s_nom_note']}".rstrip())
    lines.append("")

    lines.append("System-wide adequacy check:")
    lines.append(f"  Σ p_nom (generation) = {total_gen:,.1f} MW")
    lines.append(f"  Σ p_set (load)       = {total_load:,.1f} MW")
    lines.append(f"  Adequate?            = {adequate}")
    lines.append("")
    lines.append("Per-bus balance (local surplus/deficit):")
    lines.append("  surplus = Σ p_nom(gen@bus) - Σ p_set(load@bus)")
    lines.append("")

    gen_by_bus = devnet.generators.groupby("bus")["p_nom"].sum() if len(devnet.generators) else None
    load_by_bus = devnet.loads.groupby("bus")["p_set"].sum() if len(devnet.loads) else None

    rows = []
    for b in devnet.buses.index:
        g = float(gen_by_bus.get(b, 0.0)) if gen_by_bus is not None else 0.0
        l = float(load_by_bus.get(b, 0.0)) if load_by_bus is not None else 0.0
        rows.append((b, g, l, g - l))

    lines.append("              gen     load   surplus")
    for b, g, l, s in sorted(rows, key=lambda x: x[3]):
        status = "EXPORT" if s > 0 else ("BAL" if s == 0 else "IMPORT")
        lines.append(f"  {b:8s}    {g:7.1f}  {l:7.1f}  {s:7.1f}  [{status}]")

    return lines

# ------------------------------------------------------------------------------
# HTML Reporting Helpers
# - write_commit_dashboard_md()
# - update_index_html()
# Generates HTML dashboard:
# - commit summaries
# - embedded results
# - links to CSV artifacts
# Provides persistent visual report of stress runs
# ------------------------------------------------------------------------------
def write_commit_dashboard_md(outdir: str, commit_id: str, text: str) -> str:
    """
    Writes cN_dashboard.md and returns the filepath.
    """
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    md_path = p / f"{commit_id}_dashboard.md"
    md_path.write_text(text, encoding="utf-8")
    return str(md_path)

def update_index_html(outdir: str, devnet: pypsa.Network) -> str:
    """
    Regenerates stress_out/index.html by scanning commit artifacts.
    Lists commits, embeds dashboard text (preformatted), and links CSV files.
    Returns the filepath.
    """
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)

    # discover commits by scanning for cN_* files
    commits = set()
    for f in p.glob("c*_*"):
        name = f.name
        if not name.startswith("c"):
            continue
        i = 1
        while i < len(name) and name[i].isdigit():
            i += 1
        if i > 1 and i < len(name) and name[i] == "_":
            commits.add(name[:i])  # e.g. "c12"

    # sort numerically
    def _cnum(c: str) -> int:
        try:
            return int(c[1:])
        except Exception:
            return 0
    commits = sorted(commits, key=_cnum)

    def _read_commit_metrics(c: str) -> dict:
        """
        Pull minimal metrics from cN_* artifacts for summary table.
        Uses: cN_dashboard.md (preferred) and falls back to objective CSV if needed.
        """
        m = {
            "commit": c,
            "scenario": "",
            "objective": "",
            "lmp_spread": "",
            "max_loading_pu": "",
            "near_bind_ct": "",
            "k_first_near_bind": "",
            "lmp_spread_max": "",
        }

        md = p / f"{c}_dashboard.md"
        if md.exists():
            txt = md.read_text(encoding="utf-8", errors="replace").splitlines()
            # parse a few known dashboard lines (string parsing is fine here)
            for line in txt:
                line = line.strip()
                if line.startswith("ASR-DASH::"):
                    # example: ASR-DASH::COMMIT::c3::baseline
                    parts = line.split("::")
                    if len(parts) >= 4:
                        m["scenario"] = parts[-1].strip()
                elif line.startswith("objective"):
                    # objective        : 1.500e+06
                    if ":" in line:
                        m["objective"] = line.split(":", 1)[1].strip()
                elif line.startswith("lmp_spread"):
                    # lmp_spread       : 0.000   max_lmp: ...
                    if ":" in line:
                        m["lmp_spread"] = line.split(":", 1)[1].strip().split()[0]
                elif line.startswith("max_loading_pu"):
                    if ":" in line:
                        m["max_loading_pu"] = line.split(":", 1)[1].strip().split()[0]
                elif line.startswith("near_bind_ct"):
                    if ":" in line:
                        m["near_bind_ct"] = line.split(":", 1)[1].strip()
                elif line.startswith("first_near_bind_k"):
                    if ":" in line:
                        m["k_first_near_bind"] = line.split(":", 1)[1].strip()
                elif line.startswith("lmp_spread_max"):
                    if ":" in line:
                        m["lmp_spread_max"] = line.split(":", 1)[1].strip()

        # fallback: objective CSV (if dashboard missing)
        if not m["objective"]:
            obj_csv = list(p.glob(f"{c}_*_objective.csv"))
            if obj_csv:
                try:
                    obj_txt = obj_csv[0].read_text(encoding="utf-8", errors="replace").splitlines()
                    if len(obj_txt) >= 2 and "," in obj_txt[1]:
                        m["objective"] = obj_txt[1].split(",", 1)[1].strip()
                except Exception:
                    pass
        return m
    summary_rows = [_read_commit_metrics(c) for c in commits]

    # build HTML
    html = []
    html.append("<!doctype html>")
    html.append("<html><head><meta charset='utf-8'>")
    html.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    html.append("<title>DevNet Stress Report</title>")
    html.append("<style>")
    html.append("body{font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;margin:20px;}")
    html.append("a{color:#0b5fff;text-decoration:none} a:hover{text-decoration:underline}")
    html.append(".nav{position:sticky;top:0;background:#fff;padding:10px 0;border-bottom:1px solid #ddd;}")
    html.append(".nav a{margin-right:12px}")
    html.append("pre{background:#f6f8fa;border:1px solid #ddd;padding:12px;border-radius:8px;overflow:auto;}")
    html.append(".card{margin:18px 0;padding:14px;border:1px solid #eee;border-radius:10px;}")
    html.append("h1{margin:0 0 8px 0} h2{margin:0 0 10px 0}")
    html.append(".top-row{display:flex;gap:24px;align-items:flex-start;}")
    html.append(".left-col{flex:0 0 66vw;max-width:66vw;}")
    html.append(".right-col{flex:1;min-width:260px;}")
    html.append(".summary-table{width:100%;table-layout:fixed;border-collapse:collapse;} .summary-table th,.summary-table td{word-break:break-word;overflow-wrap:anywhere;}")
    html.append(".side-img{display:block;max-width:100%;height:auto;margin:0 auto 12px auto;border:1px solid #ddd;border-radius:10px;}")
    html.append(".side-pre{background:#f6f8fa;border:1px solid #ddd;padding:12px;border-radius:10px;white-space:pre; font-family:ui-monospace,Consolas,Monaco,'Courier New',monospace;}")
    html.append("</style></head><body>")
    html.append("<h1>DevNet Stress Report</h1>")

    # commit summary table + right panel
    html.append("<h2>Commit Summary</h2>")
    html.append("<div class='top-row'>")

    # LEFT
    html.append("<div class='left-col'>")
    if summary_rows:
        html.append("<table class='summary-table'>")
        html.append("<tr>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>commit</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>scenario</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>objective</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>lmp_spread</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>max_loading_pu</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>near_bind_ct</th>"
                    "<th style='border:1px solid #ddd;padding:6px;text-align:left'>k_first_near_bind</th>"
                    "</tr>")
        for r in summary_rows:
            html.append(
                "<tr>"
                f"<td style='border:1px solid #ddd;padding:6px'><a href='#{r['commit']}'>{r['commit']}</a></td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['scenario'])}</td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['objective'])}</td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['lmp_spread'] or r['lmp_spread_max'])}</td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['max_loading_pu'])}</td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['near_bind_ct'])}</td>"
                f"<td style='border:1px solid #ddd;padding:6px'>{html_lib.escape(r['k_first_near_bind'])}</td>"
                "</tr>"
            )
        html.append("</table>")
    else:
        html.append("<p><i>(no commits found yet)</i></p>")
    html.append("</div>")  # closes left-col

    # RIGHT (always)
    html.append("<div class='right-col'>")
    if DEVNET_NAME == "devnetDC-sld":
        html.append("<img class='side-img' src='../plots/devnetDC-sld.png' alt='DevNetDC SLD'>")
    else:
        html.append("<img class='side-img' src='../plots/devnet.png' alt='DevNet SLD'>")

    right_lines = build_sanity_panel_lines(devnet)
    right_text = "\n".join(right_lines).strip("\n")
    html.append("<pre class='side-pre'>")
    html.append(html_lib.escape(right_text))
    html.append("</pre>")
    html.append("</div>")  # closes right-col

    html.append("</div>")  # closes top-row

    # nav
    html.append("<div class='nav'>")
    html.append("<b>Commits:</b> ")
    if commits:
        for c in commits:
            html.append(f"<a href='#{c}'>{c}</a>")
    else:
        html.append("<i>(no commits found)</i>")
    html.append("</div>")

    # sections per commit
    for c in commits:
        html.append(f"<div class='card' id='{c}'>")
        html.append(f"<h2>{c}</h2>")

        # dashboard (embed contents if md exists)
        md = p / f"{c}_dashboard.md"
        if md.exists():
            dash_txt = md.read_text(encoding="utf-8", errors="replace")
            html.append("<pre>")
            html.append(html_lib.escape(dash_txt))
            html.append("</pre>")
        else:
            html.append("<pre>(dashboard markdown not found)</pre>")

        # links to CSV artifacts for this commit
        csvs = sorted([f.name for f in p.glob(f"{c}_*.csv")])
        if csvs:
            html.append("<div style='margin-top:10px'><b>CSV artifacts:</b></div>")
            html.append("<pre>")
            for fn in csvs:
                html.append(html_lib.escape(fn))
            html.append("</pre>")
        else:
            html.append("<div><b>CSV artifacts:</b> <i>(none found)</i></div>")

        html.append("</div>")
    html.append("</body></html>")

    out_path = p / "index.html"
    out_path.write_text("\n".join(html), encoding="utf-8")
    return str(out_path)

def print_dashboard(args: argparse.Namespace, mode: str, dash: dict) -> None:
    print(dashboard_text(args, mode, dash), end="")

def run_preview(devnet: pypsa.Network, args: argparse.Namespace) -> dict:
    """
    Preview run writes into outdir/_preview and prints dashboard.
    Returns dict with either:
      {"kind":"single","res":res}
      {"kind":"sweep","df":df}
    """
    outdir_orig = args.outdir
    args.outdir = os.path.join(outdir_orig, "_preview")

    if args.scenario in ("baseline", "single"):
        res = run_single(devnet, args, tag=f"preview_{args.scenario}")
        args.outdir = outdir_orig
        return {"kind": "single", "res": res}

    if args.scenario == "sweep_line":
        df = run_sweep_line(devnet, args)
        args.outdir = outdir_orig
        return {"kind": "sweep", "df": df}

    args.outdir = outdir_orig
    return {"kind": "unknown"}

def _next_commit_id(outdir: str) -> str:
    """
    Returns next commit prefix like 'c1', 'c2', ...

    IMPORTANT:
      Use a persistent counter file to ensure commit IDs NEVER repeat,
      even if artifacts are missing, moved, renamed, or written elsewhere.
    """
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)

    counter_path = p / "commit_counter.txt"

    # If counter exists, trust it (monotonic).
    if counter_path.exists():
        try:
            n = int(counter_path.read_text(encoding="utf-8").strip())
        except Exception:
            n = 0
    else:
        # Initialize counter from existing artifacts (best-effort).
        n = 0
        for f in p.glob("c*_*"):
            name = f.name
            if not name.startswith("c"):
                continue
            i = 1
            while i < len(name) and name[i].isdigit():
                i += 1
            if i > 1 and i < len(name) and name[i] == "_":
                try:
                    n = max(n, int(name[1:i]))
                except Exception:
                    pass

    # Next commit number
    n_next = n + 1

    # Persist immediately so even crashes mid-commit won't reuse an ID
    counter_path.write_text(str(n_next), encoding="utf-8")

    return f"c{n_next}"

# ------------------------------------------------------------------------------
# Main Execution & Research Loop
# - researcher_loop()
# - main()
# Orchestrates workflow:
# - load network
# - configure scenarios
# - preview runs
# - commit results
# - update dashboards
# Entry point for DevNet stress testing framework
# ------------------------------------------------------------------------------
def researcher_loop(devnet: pypsa.Network, args: argparse.Namespace, catalog: dict[str, list[str]]) -> None:

    """
    R: reselect args + preview
    C: commit current args set
    Q: quit (warn if nothing committed)
    """
    last_committed = False

    while True:
        # configure
        args = configure_args_menu(devnet, args)

        # preview
        prev = run_preview(devnet, args)
        if prev["kind"] == "single":
            dash = _dashboard_from_single(prev["res"])
            print_dashboard(args, "PREVIEW", dash)
        elif prev["kind"] == "sweep":
            dash = _dashboard_from_sweep(prev["df"])
            print_dashboard(args, "PREVIEW", dash)

        # control
        cmd = input("R=reselect  C=commit  Q=quit : ").strip().lower()
        if cmd == "r":
            os.system("cls" if os.name == "nt" else "clear")
            catalog = build_args_catalog(devnet)
            left = capture_catalog_lines(catalog)
            right = build_sanity_panel_lines(devnet)
            print_two_columns(left, right, left_width=95, gap=4)
            continue

        if cmd == "c":
            commit_id = _next_commit_id(args.outdir)   # e.g. 'c1'
            prefix = f"{commit_id}_"

            # commit run writes uniquely tagged artifacts
            if args.scenario in ("baseline", "single"):
                res = run_single(devnet, args, tag=f"{prefix}{args.scenario}")
                dash = _dashboard_from_single(res)
                print_dashboard(args, f"COMMIT::{commit_id}", dash)
            else:
                df = run_sweep_line(devnet, args, file_prefix=prefix)
                dash = _dashboard_from_sweep(df)
                print_dashboard(args, f"COMMIT::{commit_id}", dash)
            print(f"Configuration output committed @:\n\t{args.outdir}\n")
            print(f"Commit id:\t{commit_id}\n")
            dash_txt = dashboard_text(args, f"COMMIT::{commit_id}", dash)
            write_commit_dashboard_md(args.outdir, commit_id, dash_txt)
            index_path = update_index_html(args.outdir, devnet)
            print(f"HTML report updated @:\n\t{index_path}\n")
            os.system("cls" if os.name == "nt" else "clear")
            catalog = build_args_catalog(devnet)
            left = capture_catalog_lines(catalog)
            right = build_sanity_panel_lines(devnet)
            print_two_columns(left, right, left_width=95, gap=4)
            last_committed = True
            continue

        if cmd == "q":
            if not last_committed:
                if not confirm("No COMMIT recorded. Quit anyway?"):
                    continue
            return

        print("Invalid input. Use R, C, or Q.")

def main():
    args = build_argparser(DEVNET_BLD_PATH).parse_args()

    # show full catalog before step-by-step config
    catalog = build_args_catalog(devnet)
    left = capture_catalog_lines(catalog)
    right = build_sanity_panel_lines(devnet)
    print_two_columns(left, right, left_width=95, gap=4)

    # Generate initial HTML report (even before first commit)
    update_index_html(args.outdir, devnet)

    input("Press Enter to start arg configuration...\n")

    # R/C/Q loop with preview + commit
    researcher_loop(devnet, args, catalog)

# ----------------------------------------------------------------------
#   Select DevNet build (baseline vs datacenter BYOG)
# ----------------------------------------------------------------------
print("Select DevNet build:")
print("  1) devnet-sld (baseline)")
print("  2) devnetDC-sld (with Datacenter BYOG)")

choice = input("Enter choice [1]: ").strip()

if choice == "2":
    DEVNET_NAME = "devnetDC-sld"
else:
    DEVNET_NAME = "devnet-sld"

print(f"ASR-DBG::Using DEVNET_NAME::\n\t{DEVNET_NAME}\n")

# ------------------------------------------------------------------------------
#   Define DevNet Log & CSV/Excel paths
# ------------------------------------------------------------------------------
DEVNET_BLD_PATH = os.path.join(SCRIPT_DIR, DEVNET_NAME)
DEVNET_BLD_DIR = os.path.basename(DEVNET_BLD_PATH)
print("ASR-DBG::DEVNET_BLD_PATH::\n\t{0}\n" .format(DEVNET_BLD_PATH))
# --- Confirm processing existing CSV build folder if present ---
if os.path.isdir(DEVNET_BLD_PATH):
    print(f"ASR-DBG: Found DevNet CSV build folder:\n\t{DEVNET_BLD_DIR}")
    if not confirm(f"ASR-DBG: Process existing {DEVNET_BLD_DIR}.\n"):
        print("Manually remove folder and re-run devnet_sld.py. Exiting...")
        print(SECTION_SEPARATOR)
        sys.exit(0)
    else:
        print(f"ASR-DBG: Keeping existing {DEVNET_BLD_PATH}.\n")
else:
    print(f"ASR-DBG: DevNet build folder not found:\n\t{DEVNET_BLD_PATH}\n")
    print("Please run devnet_sld.py to create/export the DevNet CSV folder first. Exiting...")
    print(SECTION_SEPARATOR)
    sys.exit(0)

PLOT_PATH = os.path.join(DEVNET_BLD_PATH, "plots")
PLOT_DIR = os.path.basename(PLOT_PATH)
print("ASR-DBG::PLOT_PATH::\n\t{0}\n" .format(PLOT_PATH))
# --- Create plots folder if not present ---
if not os.path.exists(PLOT_PATH):
    os.makedirs(PLOT_PATH)
elif os.path.isdir(PLOT_PATH):
    print(f"ASR-DBG: Found existing plot folder:\n\t{PLOT_DIR}")
    if not confirm(f"ASR-DBG: Keep existing {PLOT_DIR}.\n"):
        print("Manually CLEANUP[REMOVE & RECREATE] folder and re-run script. Exiting...")
        print(SECTION_SEPARATOR)
        sys.exit(0)
    else:
        print(f"ASR-DBG: Keeping existing {PLOT_PATH}.\n")

LOG_PATH = os.path.join(DEVNET_BLD_PATH, "logs")
LOG_DIR = os.path.basename(LOG_PATH)
print("ASR-DBG::LOG_PATH::\n\t{0}\n" .format(LOG_PATH))
# --- Create LOGs folder if not present ---
if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)
LOG_NAME = f"{DEVNET_NAME}_{TS}.log"
LOG_PATH = os.path.join(LOG_PATH, f"{DEVNET_NAME}_{TS}.log")
print("ASR-DBG::Log file::\n\t{0}\n" .format(LOG_NAME))

# ------------------------------------------------------------------------------
#   Logging: Single-writer log (prints + logger all go through Tee)
#   Capture Python logging + print/stdout/stderr into file
# ------------------------------------------------------------------------------
_log_file_for_prints = open(LOG_PATH, "w", encoding="utf-8")  # ONE file handle

class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = list(streams)  # list so remove() works safely
    def write(self, s):
        for st in list(self.streams):
            try:
                st.write(s)
                st.flush()
            except Exception:
                try:
                    self.streams.remove(st)
                except Exception:
                    pass
        return len(s)
    def flush(self):
        for st in list(self.streams):
            try:
                st.flush()
            except Exception:
                try:
                    self.streams.remove(st)
                except Exception:
                    pass

# Keep original stdout & stderr handles to restore later
_orig_stdout, _orig_stderr = sys.stdout, sys.stderr

# Tee prints to console + log file (single writer)
sys.stdout = Tee(_orig_stdout, _log_file_for_prints)
sys.stderr = Tee(_orig_stderr, _log_file_for_prints)

# Configure logging to flow through sys.stdout (=> Tee => same log file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

print(f"Saving logs to: {LOG_NAME}")

# ------------------------------------------------------------------------------
#   Load DevNet base network: Exported CSVs from devnet_sld.py
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("Load DevNet base network:: Exported CSVs from devnet_sld.py…")
devnet = pypsa.Network(DEVNET_BLD_PATH)
print(f"  Loaded DevNet network from CSVs at:\n\t{DEVNET_BLD_PATH}\n")
print(f"  Network summary:\n{devnet}")

# ----------------------------------------------------------------------
#   Sanity Report: adequacy + per-bus balance + corridor bottlenecks
# ----------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Proceed with DevNet Sanity Report\nPress Enter to confirm...")
print("DevNet Sanity Report (CSV-based network)...\n")

# --- System wide generation w/ marginal prices & snapshots ---
print("devenet.generators:\n", devnet.generators[["bus", "p_nom", "marginal_cost"]])
print("\ndevnet.snapshots:\n", devnet.snapshots)

# --- System-wide adequacy ---
total_gen = float(devnet.generators["p_nom"].sum()) if len(devnet.generators) else 0.0
total_load = float(devnet.loads["p_set"].sum()) if len(devnet.loads) else 0.0

print("\nSystem-wide adequacy check:")
print(f"  Σ p_nom (generation) = {total_gen:,.1f} MW")
print(f"  Σ p_set (load)       = {total_load:,.1f} MW")
print(f"  Adequate?            = {'YES' if total_gen >= total_load else 'NO'}\n")

# --- Per-bus balance intuition ---
gen_by_bus = devnet.generators.groupby("bus")["p_nom"].sum() if len(devnet.generators) else None
load_by_bus = devnet.loads.groupby("bus")["p_set"].sum() if len(devnet.loads) else None

print("Per-bus balance (local surplus/deficit):")
print("  surplus = Σ p_nom(gen@bus) - Σ p_set(load@bus)\n")
rows = []
for b in devnet.buses.index:
    g = float(gen_by_bus.get(b, 0.0)) if gen_by_bus is not None else 0.0
    l = float(load_by_bus.get(b, 0.0)) if load_by_bus is not None else 0.0
    rows.append((b, g, l, g - l))
# print sorted by most negative (largest deficit) first
rows_sorted = sorted(rows, key=lambda x: x[3])
for b, g, l, s in rows_sorted:
    status = "EXPORT" if s > 0 else ("BAL" if s == 0 else "IMPORT")
    print(f"  {b:10s}  gen={g:8.1f}  load={l:8.1f}  surplus={s:8.1f}  [{status}]")
print("\n" + SUBSECTION_SEPARATOR)

# --- Corridor deliverability sanity check (smallest s_nom lines) ---
print("Corridor deliverability check (smallest s_nom lines):\n")
if len(devnet.lines):
    cols = [c for c in ["bus0", "bus1", "s_nom"] if c in devnet.lines.columns]
    bottlenecks = devnet.lines[cols].copy()
    bottlenecks = bottlenecks.sort_values("s_nom", ascending=True)

    # show top-N smallest limits
    N = min(6, len(bottlenecks))
    for line_name, r in bottlenecks.head(N).iterrows():
        print(f"  {line_name:22s}  {r['bus0']:10s} -> {r['bus1']:10s}   s_nom={float(r['s_nom']):,.1f}")
else:
    print("  No lines found in network.")

# ------------------------------------------------------------------------------
#   Invoke DevNet: DOE Stress knobs[solve<<>>measure<<>>adjust]::Asymptote find
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Proceed with DevNet Asymptote Finder\nPress Enter to confirm...")
print("DevNet Asymptote Finder (CSV-based network)...\n")
if __name__ == "__main__":
    main()

# ------------------------------------------------------------------------------
# --- Tear down (IMPORTANT: restore orig stdout, stderr handles, then close) ---
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Tear down logging redirection\nPress Enter to confirm...")
sys.stdout = _orig_stdout
sys.stderr = _orig_stderr
# Close the extra log stream
_log_file_for_prints.close()
# ------------------------------------------------------------------------------
# END OF devnet_stress.py
# ------------------------------------------------------------------------------

