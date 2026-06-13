#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 ZeroNode
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

# devnet_stress_lib.py
#
# Congestion/LMP stress library for DevNet:
# - Stress knobs: bus load multiplier, corridor capacity reducer, bus gen marginal cost
# - Datacenter BYOG ECON MODE support
# - Outputs: objective, LMPs, line loadings, binding indicators
#
# Notes:
# - This library contains NO input() prompts
# - This library contains NO researcher menu loop
# - devnet_stress.py should remain the interactive researcher shell
# - demo_runner.py should call this library directly
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------
#   Standard library imports
# ------------------------------------------------------------------
import copy
import os
import json
from pathlib import Path
from pydoc import html

# ------------------------------------------------------------------
#   Third-party imports
# ------------------------------------------------------------------
import numpy as np
import pandas as pd
import pypsa

# ------------------------------------------------------------------
#    HTML escaping utilities
# ------------------------------------------------------------------
import html as html_lib

# ------------------------------------------------------------------------------
#   HTML template paths
# ------------------------------------------------------------------------------
LIB_DIR = os.path.dirname(os.path.abspath(__file__))

DEVNET_STRESS_FRAME_TEMPLATE = os.path.join(
    LIB_DIR,
    "devnet_stress_frame.html"
)

# Global defines
SECTION_SEPARATOR = "=" * 80 + "\n"
SUBSECTION_SEPARATOR = "-" * 40 + "\n"

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
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
        # ------------------------------------------------------------------
        # ASR-NOTE:
        # Do NOT apply regional load stress multiplier to explicit
        # datacenter load objects.
        #
        # Datacenter load must remain independently controllable via:
        #   dc_p_set
        #
        # This prevents:
        #   k_load from silently multiplying DC demand.
        #
        # Example:
        #   PJM_NE regional load stress = 6000 MW
        #   Regional load multiplier    = k_load
        #   DC load                     = 2000 MW
        #   Total PJM_NE load           = [(6000 * k_load) + 2000] MW
        #
        # NOT:
        #   [(6000 + 2000) * k_load] MW
        # ------------------------------------------------------------------
        loads_at_bus = n.loads.index[
            (n.loads.bus == bus)
            &
            (~n.loads.index.str.contains("DC", case=False, na=False))
        ]
        if len(loads_at_bus) == 0:
            continue

        if "p_set" in n.loads.columns:
            n.loads.loc[loads_at_bus, "p_set"] = n.loads.loc[loads_at_bus, "p_set"].astype(float) * float(k)

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
def resolve_dc_csv_values(devnet: pypsa.Network) -> dict:
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

    out["dc_dispatch_mw"] = np.nan

    if hasattr(n, "buses_t") and hasattr(n.buses_t, "marginal_price") and not n.buses_t.marginal_price.empty:
        out["lmp"] = n.buses_t.marginal_price.loc[snap].to_dict()
    else:
        out["lmp"] = {}

    if hasattr(n, "lines_t") and hasattr(n.lines_t, "p0") and not n.lines_t.p0.empty and not n.lines.empty:
        loading = (n.lines_t.p0.loc[snap].abs() / n.lines.s_nom).replace([np.inf, -np.inf], np.nan)
        out["line_loading_pu"] = loading.to_dict()
    else:
        out["line_loading_pu"] = {}

    # --------------------------------------------------------------
    # Datacenter BYOG dispatch
    #
    # Only valid for devnetDC-sld where:
    #
    #   Gen_DC_PJM_NE
    #
    # is dynamically added.
    # --------------------------------------------------------------
    try:

        if (
            "Gen_DC_PJM_NE"
            not in n.generators.index
        ):
            return out

        if (
            hasattr(n, "generators_t")
            and hasattr(n.generators_t, "p")
            and "Gen_DC_PJM_NE" in n.generators_t.p.columns
        ):

            out["dc_dispatch_mw"] = float(
                n.generators_t.p.loc[
                    snap,
                    "Gen_DC_PJM_NE"
                ]
            )

    except Exception:

        pass

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
def parse_json_dict(s) -> dict:
    if not s:
        return {}
    if isinstance(s, dict):
        return s
    return json.loads(s)


# ------------------------------------------------------------------------------
# resolve_byog_mc()
# Determines effective BYOG marginal cost for dispatch:
# - Uses CLI override if provided (--byog_mc)
# - Falls back to loads.csv (default model input)
# Centralizes BYOG cost logic for consistency across runs
# ------------------------------------------------------------------------------
def resolve_byog_mc(n: pypsa.Network, args, devnet_name: str):
    if devnet_name != "devnetDC-sld":
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
# See BYOG ECON MODE + CES Interpretation (top of original devnet_stress.py)
# ------------------------------------------------------------------------------
def run_single(n0: pypsa.Network, args, tag: str, devnet_name: str) -> dict:
    n = copy.deepcopy(n0)

    apply_load_multipliers(n, parse_json_dict(args.k_load))
    apply_corridor_reducers(n, parse_json_dict(args.k_line))
    apply_gen_marginal_cost_by_bus(n, parse_json_dict(args.mc_bus), mode=args.mc_mode)

    if devnet_name == "devnetDC-sld" and "Load_DC_PJM_NE" in n.loads.index:
        byog_p = float(n.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
        # --------------------------------------------------------------
        # ASR-NOTE:
        # Explicit datacenter load is additive to regional PJM_NE load.
        #
        # Regional stress:
        #   apply_load_multipliers()
        #
        # Datacenter load:
        #   dc_p_set
        #
        # Therefore:
        #   DC load is NOT multiplied by k_load.
        # --------------------------------------------------------------
        p_set = float(n.loads.at["Load_DC_PJM_NE", "p_set"])

        if getattr(args, "dc_p_nom", None) is not None:
            byog_p = float(args.dc_p_nom)

        if getattr(args, "dc_p_set", None) is not None:
            p_set = float(args.dc_p_set)

        mc = resolve_byog_mc(n, args, devnet_name)

        n.loads.at["Load_DC_PJM_NE", "p_set"] = p_set

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
# See BYOG ECON MODE + CES Interpretation (top of original devnet_stress.py)
# ------------------------------------------------------------------------------
def run_sweep_line(n0: pypsa.Network, args, devnet_name: str, file_prefix: str = "") -> pd.DataFrame:
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

        if devnet_name == "devnetDC-sld" and "Load_DC_PJM_NE" in n.loads.index:
            byog_p = float(n.loads.at["Load_DC_PJM_NE", "byog_p_nom"])
            # --------------------------------------------------------------
            # ASR-NOTE:
            # Explicit datacenter load is additive to regional PJM_NE load.
            #
            # Regional stress:
            #   apply_load_multipliers()
            #
            # Datacenter load:
            #   dc_p_set
            #
            # Therefore:
            #   DC load is NOT multiplied by k_load.
            # --------------------------------------------------------------
            p_set = float(n.loads.at["Load_DC_PJM_NE", "p_set"])

            if getattr(args, "dc_p_nom", None) is not None:
                byog_p = float(args.dc_p_nom)

            if getattr(args, "dc_p_set", None) is not None:
                p_set = float(args.dc_p_set)

            mc = resolve_byog_mc(n, args, devnet_name)

            n.loads.at["Load_DC_PJM_NE", "p_set"] = p_set

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
    obj = float(res.get("objective", np.nan))

    lmp = res.get("lmp", {}) or {}
    lmp_vals = np.array(list(lmp.values()), dtype=float) if len(lmp) else np.array([])
    lmp_spread = float(np.nanmax(lmp_vals) - np.nanmin(lmp_vals)) if lmp_vals.size else np.nan
    max_lmp_bus = max(lmp, key=lambda b: float(lmp[b])) if len(lmp) else ""
    max_lmp = float(lmp[max_lmp_bus]) if max_lmp_bus else np.nan

    loading = res.get("line_loading_pu", {}) or {}
    loading_vals = np.array(list(loading.values()), dtype=float) if len(loading) else np.array([])
    max_loading_pu = float(np.nanmax(loading_vals)) if loading_vals.size else np.nan
    max_loading_line = max(loading, key=lambda ln: float(loading[ln])) if len(loading) else ""
    near_bind_ct = int(np.sum(loading_vals >= 0.95)) if loading_vals.size else 0

    top_lines = []
    if len(loading):
        top_lines = sorted(loading.items(), key=lambda kv: float(kv[1]), reverse=True)[:3]

    dc_dispatch_mw = float(
        res.get(
            "dc_dispatch_mw",
            np.nan
        )
    )

    return {
        "objective": obj,
        "lmp_spread": lmp_spread,
        "max_lmp_bus": max_lmp_bus,
        "max_lmp": max_lmp,
        "max_loading_pu": max_loading_pu,
        "max_loading_line": max_loading_line,
        "near_bind_ct": near_bind_ct,
        "dc_dispatch_mw": dc_dispatch_mw,
        "top_lines": top_lines,
    }


def _dashboard_from_sweep(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"empty": True}

    obj_min = float(df["objective"].min()) if "objective" in df.columns else np.nan
    obj_max = float(df["objective"].max()) if "objective" in df.columns else np.nan

    lmp_spread_max = float(df["lmp_spread"].max()) if "lmp_spread" in df.columns else np.nan
    if "lmp_spread" in df.columns and df["lmp_spread"].notna().any():
        idx = int(df["lmp_spread"].idxmax())
        k_at = float(df.loc[idx, "k_line"])
    else:
        k_at = np.nan

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


def dashboard_text(args, mode: str, dash: dict, devnet: pypsa.Network) -> str:
    """
    Returns the same dashboard you print to console, as a single string.
    mode examples: "PREVIEW" or "COMMIT::c3"
    """
    lines = []
    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    lines.append(f"ASR-DASH::{mode}::{args.scenario}")
    lines.append(SUBSECTION_SEPARATOR.rstrip("\n"))

    dc_csv = resolve_dc_csv_values(devnet)

    dc_mc = getattr(args, "byog_mc", None)
    dc_p_set = getattr(args, "dc_p_set", None)
    dc_p_nom = getattr(args, "dc_p_nom", None)

    dc_p_set_str = f"CSV Preset::{dc_csv['p_set']}" if dc_p_set is None else dc_p_set
    dc_p_nom_str = f"CSV Preset::{dc_csv['p_nom']}" if dc_p_nom is None else dc_p_nom
    dc_mc_str = f"CSV Preset::{dc_csv['byog_mc']}" if dc_mc is None else dc_mc

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
    """
    buses_n = int(len(devnet.buses.index)) if hasattr(devnet, "buses") else 0

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
            mc_repr = float(np.nanmin(mc_unique))
            mc_note = f"(multiple mc values; showing min of {mc_unique.size})"
    else:
        mc_repr = np.nan
        mc_note = "mc: missing"

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
    base = devnet_base_params(devnet)

    total_gen = float(devnet.generators["p_nom"].sum()) if len(devnet.generators) else 0.0
    total_load = float(devnet.loads["p_set"].sum()) if len(devnet.loads) else 0.0
    adequate = "YES" if total_gen >= total_load else "NO"

    lines = []
    lines.append("")
    lines.append("DevNet base params:")
    lines.append(f"  Buses_N            = {base['buses_n']}")

    dc_mc = None
    if "byog_mc" in devnet.loads.columns:
        dc_rows = devnet.loads[devnet.loads.index.str.contains("DC", case=False, na=False)]
        if not dc_rows.empty:
            try:
                dc_mc = float(dc_rows["byog_mc"].iloc[0])
            except Exception:
                dc_mc = None

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

def update_index_html(
    outdir: str,
    devnet: pypsa.Network,
    devnet_name: str,
    use_http_paths: bool = False
) -> str:
    """
    Regenerates stress_out/index.html by scanning commit artifacts.
    Lists commits, embeds dashboard text (preformatted), and links CSV files.
    Returns the filepath.
    """
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)

    commits = set()
    for f in p.glob("c*_*"):
        name = f.name
        if not name.startswith("c"):
            continue
        i = 1
        while i < len(name) and name[i].isdigit():
            i += 1
        if i > 1 and i < len(name) and name[i] == "_":
            commits.add(name[:i])

    def _cnum(c: str) -> int:
        try:
            return int(c[1:])
        except Exception:
            return 0

    commits = sorted(commits, key=_cnum)

    def _read_commit_metrics(c: str) -> dict:
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
            for line in txt:
                line = line.strip()
                if line.startswith("ASR-DASH::"):
                    parts = line.split("::")
                    if len(parts) >= 4:
                        m["scenario"] = parts[-1].strip()
                elif line.startswith("objective"):
                    if ":" in line:
                        m["objective"] = line.split(":", 1)[1].strip()
                elif line.startswith("lmp_spread"):
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

    # ------------------------------------------------------------------
    # Load HTML frame template
    # ------------------------------------------------------------------
    if not os.path.exists(DEVNET_STRESS_FRAME_TEMPLATE):
        raise FileNotFoundError(
            f"Missing HTML template:\n\t{DEVNET_STRESS_FRAME_TEMPLATE}"
        )

    with open(
        DEVNET_STRESS_FRAME_TEMPLATE,
        "r",
        encoding="utf-8"
    ) as f:
        html = f.read()

    body = []

    body.append("<h1>DevNet Stress Report</h1>")

    body.append("<h2>Commit Summary</h2>")
    body.append("<div class='top-row'>")
    body.append("<div class='left-col'>")

    if summary_rows:
        body.append("<table class='summary-table'>")
        body.append(
            "<tr>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>commit</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>scenario</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>objective</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>lmp_spread</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>max_loading_pu</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>near_bind_ct</th>"
            "<th style='border:1px solid #ddd;padding:6px;text-align:left'>k_first_near_bind</th>"
            "</tr>"
        )
        for r in summary_rows:
            body.append(
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
        body.append("</table>")
    else:
        body.append("<p><i>(no commits found yet)</i></p>")
    # Close left-col: Commit summary metrics table
    body.append("</div>")

    # ------------------------------------------------------------------
    # Right panel
    #   - compact SLD image
    #   - base params BELOW image
    # ------------------------------------------------------------------
    body.append("<div class='right-col'>")

    # ------------------------------------------------------------------
    # Resolve SLD image path
    # ------------------------------------------------------------------
    if use_http_paths:

        if devnet_name == "devnetDC-sld":
            plot_png_rel = "/devnetDC-sld/plots/devnetDC-sld.png"
        else:
            plot_png_rel = "/devnet-sld/plots/devnet-sld.png"
    else:

        if devnet_name == "devnetDC-sld":
            plot_png_rel = "../../devnetDC-sld/plots/devnetDC-sld.png"
        else:
            plot_png_rel = "../../devnet-sld/plots/devnet-sld.png"

    body.append(
        f"<img class='side-img' "
        f"src='{plot_png_rel}' "
        f"alt='DevNet SLD' "
        f"style='max-width:100%; height:auto;'>"
    )

    right_lines = build_sanity_panel_lines(devnet)
    right_text = "\n".join(right_lines).strip("\n")

    body.append("<pre class='side-pre'>")
    body.append(html_lib.escape(right_text))
    body.append("</pre>")
    # Close right-col: SLD image + base params
    body.append("</div>")
    # Close top-row: Commit summary + right panel
    body.append("</div>")

    # ------------------------------------------------------------------
    # Commit navigation bar
    # - Sticky top navigation
    # - Quick jump links to committed stress runs
    # - Links anchor into per-commit dashboard sections below
    # ------------------------------------------------------------------
    body.append("<div class='nav'>")
    body.append("<b>Commits:</b> ")
    if commits:
        for c in commits:
            body.append(f"<a href='#{c}'>{c}</a>")
    else:
        body.append("<i>(no commits found)</i>")
    # Close sticky commit navigation bar
    body.append("</div>")

    for c in commits:
        body.append(f"<div class='card' id='{c}'>")
        body.append(f"<h2>{c}</h2>")

        md = p / f"{c}_dashboard.md"
        if md.exists():
            dash_txt = md.read_text(encoding="utf-8", errors="replace")
            body.append("<pre>")
            body.append(html_lib.escape(dash_txt))
            body.append("</pre>")
        else:
            body.append("<pre>(dashboard markdown not found)</pre>")

        csvs = sorted([f.name for f in p.glob(f"{c}_*.csv")])
        if csvs:
            body.append("<div style='margin-top:10px'><b>CSV artifacts:</b></div>")
            body.append("<pre>")
            for fn in csvs:
                body.append(html_lib.escape(fn))
            body.append("</pre>")
        else:
            body.append("<div><b>CSV artifacts:</b> <i>(none found)</i></div>")
        # Close per-commit dashboard card
        body.append("</div>")

    # ------------------------------------------------------------------
    # Inject generated report body into HTML frame
    # ------------------------------------------------------------------
    html = html.replace(
        "{{DEVNET_STRESS_BODY}}",
        "\n".join(body)
    )
    out_path = p / "index.html"

    out_path.write_text(
        html,
        encoding="utf-8"
    )

    return str(out_path)

# ------------------------------------------------------------------------------
# Commit / Preview Helpers
# - run_preview()
# - _next_commit_id()
# - run_commit()
# Non-interactive helpers used by:
# - devnet_stress.py researcher shell
# - demo_runner.py automation
# ------------------------------------------------------------------------------
def run_preview(devnet: pypsa.Network, args, devnet_name: str) -> dict:
    """
    Preview run writes into outdir/_preview.
    Returns dict with either:
      {"kind":"single","res":res}
      {"kind":"sweep","df":df}
    """
    outdir_orig = args.outdir
    args.outdir = str(Path(outdir_orig) / "_preview")

    if args.scenario in ("baseline", "single"):
        res = run_single(devnet, args, tag=f"preview_{args.scenario}", devnet_name=devnet_name)
        args.outdir = outdir_orig
        return {"kind": "single", "res": res}

    if args.scenario == "sweep_line":
        df = run_sweep_line(devnet, args, devnet_name=devnet_name)
        args.outdir = outdir_orig
        return {"kind": "sweep", "df": df}

    args.outdir = outdir_orig
    return {"kind": "unknown"}


def _next_commit_id(outdir: str) -> str:
    """
    Returns next commit prefix like 'c1', 'c2', ...
    """
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)

    counter_path = p / "commit_counter.txt"

    if counter_path.exists():
        try:
            n = int(counter_path.read_text(encoding="utf-8").strip())
        except Exception:
            n = 0
    else:
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

    n_next = n + 1
    counter_path.write_text(str(n_next), encoding="utf-8")

    return f"c{n_next}"

def run_commit(
    devnet: pypsa.Network,
    args,
    devnet_name: str,
    use_http_paths: bool = False
) -> dict:
    """
    Runs and commits current args into stress_out.
    Returns:
      {
        "commit_id": "cN",
        "kind": "single" | "sweep",
        "dash": dict,
        "dashboard_text": str,
        "index_path": str
      }
    """
    commit_id = _next_commit_id(args.outdir)
    prefix = f"{commit_id}_"

    if args.scenario in ("baseline", "single"):
        res = run_single(devnet, args, tag=f"{prefix}{args.scenario}", devnet_name=devnet_name)
        dash = _dashboard_from_single(res)
        kind = "single"
    else:
        df = run_sweep_line(devnet, args, devnet_name=devnet_name, file_prefix=prefix)
        dash = _dashboard_from_sweep(df)
        kind = "sweep"

    dash_txt = dashboard_text(args, f"COMMIT::{commit_id}", dash, devnet)
    write_commit_dashboard_md(args.outdir, commit_id, dash_txt)
    index_path = update_index_html(
        args.outdir,
        devnet,
        devnet_name,
        use_http_paths=use_http_paths
    )

    return {
        "commit_id": commit_id,
        "kind": kind,
        "dash": dash,
        "dashboard_text": dash_txt,
        "index_path": index_path,
    }

# ------------------------------------------------------------------------------
# END OF devnet_stress_lib.py
# ------------------------------------------------------------------------------