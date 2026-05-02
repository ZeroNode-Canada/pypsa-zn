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

# devnet_doe.py
#
# Purpose
#  Load an exported DevNet CSV folder and run baseline DoE checks: adequacy, per-bus balance,
#  corridor bottleneck scan, and a first solve to compute flows and identify constraint violations.

# What it does
#  - Prompts for DEVNET_NAME and points DEVNET_BLD_PATH to an existing exported CSV DevNet.
#  - Creates per-devnet plots/ and logs/ directories.
#  - Loads the network from CSVs: pypsa.Network(DEVNET_BLD_PATH).
#  - Runs sanity checks:
#      - system-wide Σ p_nom vs Σ p_set
#      - per-bus surplus/deficit
#      - smallest s_nom corridor list (candidate bottlenecks)
#  - Solves the network (optimize) and computes:
#      - per-line utilization |flow|/s_nom
#      - flags any violations (util > 1.0)

# Outputs
#  - DEVNET_BLD_PATH/logs/<DEVNET_NAME>_<TS>.log
#  - Console/log sanity report (and optionally plots if you add them later)

# Run: devnet_doe.py
# ------------------------------------------------------------------------------

import os
import shutil
import io
import sys
import logging
from datetime import datetime
import math
import numpy as np

import matplotlib.pyplot as plt
import pypsa

# Global defines
SECTION_SEPARATOR = "="*80 + "\n" # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n" # for print separation

print(SECTION_SEPARATOR)
print("PyPSA DevNet Design of Experiment (DoE) Script...\n")

# ----- Resolve paths next to this script -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt):
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")

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

# ------------------------------------------------------------------------------
# Datacenter BYOG Modeling — ECON MODE (aligned with devnet_stress.py)
# ------------------------------------------------------------------------------
# - Full DC load exposed to grid (no BTM netting)
# - BYOG modeled as generator at same bus
# - OPF determines dispatch based on marginal cost
#
# Behavior:
#   byog_mc < grid_mc → BYOG dispatches
#   byog_mc > grid_mc → grid serves load
#
# Enables:
# - correct economic dispatch
# - congestion / LMP response consistency
# ------------------------------------------------------------------------------
# Apply BYOG ECON MODE for devnetDC-sld if a Load_DC_* row is present
if DEVNET_NAME == "devnetDC-sld":

    dc_loads = [
        ld for ld in devnet.loads.index
        if str(ld).startswith("Load_DC_")
        and "byog_p_nom" in devnet.loads.columns
        and "byog_mc" in devnet.loads.columns
    ]

    if dc_loads:
        dc_load = dc_loads[0]
        dc_bus = str(devnet.loads.at[dc_load, "bus"])
        byog_p = float(devnet.loads.at[dc_load, "byog_p_nom"])
        mc     = float(devnet.loads.at[dc_load, "byog_mc"])

        gen_name = f"Gen_{dc_load.replace('Load_', '')}"

        if gen_name in devnet.generators.index:
            devnet.remove("Generator", gen_name)

        devnet.add(
            "Generator",
            gen_name,
            bus=dc_bus,
            carrier="gas",
            p_nom=byog_p,
            marginal_cost=mc,
        )

        print(f"ASR-DBG::DOE added BYOG generator:: {gen_name} @ {dc_bus}, p_nom={byog_p}, mc={mc}")

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
#   Solve DevNet for Linear Optimal Power Flow (LOPF) & check flows
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Solve DevNet for LOPF & check flows\nPress Enter to confirm...")

# Solve: this produces dispatch + flows + marginal prices (if feasible)
devnet.optimize()

# Pick the first snapshot (your devnet currently uses a single snapshot like "now")
t0 = devnet.snapshots[0]

# Flow at bus0 end for each line at snapshot t0
flows = devnet.lines_t.p0.loc[t0].abs()

# Capacity limits
limits = devnet.lines["s_nom"]

# util is a pandas Series indexed by line name.
# It is created implicitly via pandas index-aligned arithmetic:
#   Series (|line flow|) / Series (s_nom).
# No explicit `import pandas as pd` is needed because PyPSA’s data model:
#   Already exposes pandas objects (e.g., devnet.lines, devnet.loads,
#   devnet.generators, devnet.lines_t.p0). This is idiomatic PyPSA usage.
# pandas Series: per-line utilization = |flow| / s_nom (index-aligned via PyPSA)
util = (flows / limits).sort_values(ascending=False)

print(f"Line utilization @ snapshot '{t0}':\n")
for ln, u in util.head(10).items():
    print(f"  {ln:22s}  |p0|={flows[ln]:8.1f}   s_nom={limits[ln]:8.1f}   util={u:6.2%}")

# Note: util is a pandas Series indexed by line name
#   (values = utilization ratios like |flow| / s_nom)
# util > 1.0 creates a boolean mask (True/False for each index)
# util[mask] performs boolean indexing, returning only the entries where the mask is True
# Flag any violations
viol = util[util > 1.0]
if len(viol):
    print("\nASR-WARN: Line limit violations detected:")
    for ln, u in viol.items():
        print(f"  {ln:22s}  util={u:6.2%}")
else:
    print("\nASR-DBG: No line limit violations (all |flow| <= s_nom).")

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
# END OF devnet_doe.py
# ------------------------------------------------------------------------------




