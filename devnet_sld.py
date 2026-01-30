"""
devnet_sld.py

Purpose
  Build the baseline USA-lite 6-bus DevNet network (SLD) in PyPSA, plot an annotated
  one-line diagram (buses/lines + generators/loads), and export the network as a CSV folder.

What it does
  - Prompts for DEVNET_NAME and creates per-devnet plots/ and logs/ directories.
  - Builds a symmetric 6-bus hexagon topology with 6 intertie lines.
  - Adds 1 gas generator + 1 metro load per bus (baseline components) and defines carriers.
  - Generates a publication-style SLD plot with bus/line labels + symmetric gen/load overlays.
  - Exports the full network (buses/lines/generators/loads/carriers/snapshots/etc.) to DEVNET_BLD_PATH.

Outputs
  - DEVNET_BLD_PATH/ (CSV network definition)
  - DEVNET_BLD_PATH/plots/<DEVNET_NAME>.png
  - DEVNET_BLD_PATH/logs/<DEVNET_NAME>_<TS>.log
"""
# Run: devnet_sld.py

# Datacenter Network (DevNet) Single Line Diagram (SLD) builder script for PyPSA
# Baseline DevNet: USA-lite 6-bus SLD with basic components
# SLC exported as CSVs + plotted SLD diagram
# Exported CSVs can be re-imported into PyPSA for further modeling/analysis
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
print("PyPSA DevNet Builder Script...\n")

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
#   Prompt user for DevNet name
# ----------------------------------------------------------------------
default_devnet = "devnet-sld"

user_input = input(f"Enter DevNet name [{default_devnet}]: ").strip()
DEVNET_NAME = user_input if user_input else default_devnet
print(f"ASR-DBG::Using DEVNET_NAME::\n\t{DEVNET_NAME}\n")

# ------------------------------------------------------------------------------
#   Define DevNet Log & CSV/Excel paths
# ------------------------------------------------------------------------------
DEVNET_BLD_PATH = os.path.join(SCRIPT_DIR, DEVNET_NAME)
DEVNET_BLD_DIR = os.path.basename(DEVNET_BLD_PATH)
print("ASR-DBG::DEVNET_BLD_PATH::\n\t{0}\n" .format(DEVNET_BLD_PATH))
# --- Delete existing CSV build folder if present ---
if os.path.isdir(DEVNET_BLD_PATH):
    print(f"ASR-DBG: Found existing build folder:\n\t{DEVNET_BLD_DIR}")
    if not confirm(f"ASR-DBG: Keep existing {DEVNET_BLD_DIR}.\n"):
        print("Manually remove folder and re-run script. Exiting...")
        print(SECTION_SEPARATOR)
        sys.exit(0)
    else:
        print(f"ASR-DBG: Keeping existing {DEVNET_BLD_PATH}.\n")

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
#   Build DevNet Single Line Diagram (SLD) Network
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("Build DevNet Single Line Diagram (SLD) in PyPSA…")
devnet = pypsa.Network()

# --- Set network name
devnet.name = DEVNET_NAME
print(f"ASR-DBG::DevNet SLD name::\n\t{devnet.name}\n")

# Buses (USA-lite regions) — hexagon in line-chain order
# Order around the ring:
# WECC_NW -> WECC_SW -> SPP_MISO -> PJM_NE -> SERC_SE -> ERCOT -> back to WECC_NW
R = 10.0
buses = {
    "WECC_NW":  ( R,  0.0),           # 0°  (right)
    "WECC_SW":  ( R/2, -0.866*R),     # -60°
    "SPP_MISO": (-R/2, -0.866*R),     # -120°
    "PJM_NE":   (-R,  0.0),           # 180° (left)
    "SERC_SE":  (-R/2,  0.866*R),     # 120°
    "ERCOT":    ( R/2,  0.866*R),     # 60°
}
for name, (x, y) in buses.items():
    devnet.add("Bus", name, x=x, y=y, v_nom=345, carrier="ac")

# Simple interties (lines) – this is your one-line structure
lines = [
    ("L_WECC_NW_WECC_SW", "WECC_NW", "WECC_SW"),
    ("L_WECC_SW_SPP_MISO", "WECC_SW", "SPP_MISO"),
    ("L_SPP_MISO_ERCOT", "SPP_MISO", "ERCOT"),
    ("L_SPP_MISO_PJM_NE", "SPP_MISO", "PJM_NE"),
    ("L_PJM_NE_SERC_SE", "PJM_NE", "SERC_SE"),
    ("L_SERC_SE_ERCOT", "SERC_SE", "ERCOT"),
]
for name, b0, b1 in lines:
    devnet.add("Line", name, bus0=b0, bus1=b1, x=0.1, r=0.01, s_nom=5000, carrier="ac")
print("ASR-DBG::SLD buses::\n\t{0}\n" .format(buses))
print("ASR-DBG::SLD lines::\n\t{0}\n" .format(lines))

# ----------------------------------------------------------------------
#   Add 1 generator + 1 load per bus (baseline: gas gen, metro load)
# ----------------------------------------------------------------------
# Define carriers for generators and loads
devnet.add("Carrier", "gas", co2_emissions=0.19)   # tCO2/MWh (example)
devnet.add("Carrier", "load")
devnet.add("Carrier", "ac")

for b in devnet.buses.index:
    devnet.add(
        "Generator",
        f"Gen_{b}",
        bus=b,
        carrier="gas",
        p_nom=8000.0,
        marginal_cost=50.0,
    )
    devnet.add(
        "Load",
        f"Load_{b}",
        bus=b,
        carrier="load",
        p_set=5000.0,
    )
print("ASR-DBG::SLD carriers::\n\t{0}\n".format(devnet.carriers.index.tolist()))
print("ASR-DBG::SLD generators::\n\t{0}\n" .format(devnet.generators.index.tolist()))
print("ASR-DBG::SLD loads::\n\t{0}\n" .format(devnet.loads.index.tolist()))

# ----------------------------------------------------------------------
#   Sanity Report: adequacy + per-bus balance + corridor bottlenecks
# ----------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Proceed with DevNet SLD Sanity Report\nPress Enter to confirm...")
print("DevNet SLD Sanity Report...\n")

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

print("\n" + SECTION_SEPARATOR)

# ------------------------------------------------------------------------------
# Plot: "One-line diagram" for USA-lite
# --- Figure with dedicated title band (top) + SLD plot (bottom)
# ------------------------------------------------------------------------------
print("Overlay buses & lines on SLD plot...\n")

fig = plt.figure(figsize=(9, 7))

gs = fig.add_gridspec(
    nrows=2,
    ncols=1,
    height_ratios=[0.18, 0.82],   # more space for title
)

# Title band
ax_title = fig.add_subplot(gs[0])
ax_title.axis("off")
ax_title.text(
    0.5, 0.5,
    "USA-lite 6-bus one-line (regions + interties)",
    ha="center", va="center",
    fontsize=16,
    fontweight="bold",
)

# Main SLD axis
ax = fig.add_subplot(gs[1])

# --- Plot network (NO title here)
devnet.plot.map(
    ax=ax,
    geomap=False,
    bus_sizes=0.4,
    bus_colors="tab:blue",
    line_widths=2.0,
)

# --- Annotate buses ---
for bus, row in devnet.buses.iterrows():
    ax.text(
        row["x"], row["y"] + 0.6,   # slight offset above the marker
        bus,
        ha="center",
        va="bottom",
        fontsize=9,
        color="black"
    )

# --- Annotate lines (angled along line direction) ---
for line, row in devnet.lines.iterrows():
    x0, y0 = devnet.buses.loc[row.bus0, ["x", "y"]]
    x1, y1 = devnet.buses.loc[row.bus1, ["x", "y"]]

    # midpoint
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2

    # angle of the line in degrees
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))

    # keep text readable (avoid upside-down labels)
    if angle < -90:
        angle += 180
    elif angle > 90:
        angle -= 180

    ax.text(
        xm, ym,
        line,
        fontsize=8,
        color="brown",
        ha="center",
        va="center",
        rotation=angle,
        rotation_mode="anchor",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7),
    )

# ------------------------------------------------------------------------------
#   Symmetric overlay: Generators + Loads placed radially from bus center
# ------------------------------------------------------------------------------
print("Symmetric overlay generators & loads on SLD plot...\n")

# Hexagon center (use average of bus coordinates)
cx = float(devnet.buses["x"].mean())
cy = float(devnet.buses["y"].mean())

# Distances from bus node for icons and labels (tune these if needed)
R_ICON = 1.4     # how far generator/load markers sit from bus
R_TEXT = 2.2     # how far text sits from bus (keeps labels away)

def radial_unit(x, y, cx, cy):
    vx, vy = x - cx, y - cy
    norm = (vx * vx + vy * vy) ** 0.5
    if norm == 0:
        return 0.0, 1.0
    return vx / norm, vy / norm

# --- Generators ---
for gen, row in devnet.generators.iterrows():
    b = row["bus"]
    x, y = devnet.buses.loc[b, ["x", "y"]]
    ux, uy = radial_unit(x, y, cx, cy)

    # generator marker outward from bus
    gx, gy = x + ux * R_ICON, y + uy * R_ICON
    ax.scatter(gx, gy, s=140, marker="s", zorder=6)

    # generator label further outward
    carrier = row.get("carrier", "")
    p_nom = row.get("p_nom", np.nan)
    tx, ty = x + ux * R_TEXT, y + uy * R_TEXT
    ax.text(
        tx, ty,
        f"{gen}\n{carrier}, p_nom={p_nom:g}",
        ha="center", va="center",
        fontsize=7, color="black",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7),
        zorder=7,
    )

# --- Loads ---
for ld, row in devnet.loads.iterrows():
    b = row["bus"]
    x, y = devnet.buses.loc[b, ["x", "y"]]
    ux, uy = radial_unit(x, y, cx, cy)

    # load marker inward from bus (opposite direction)
    lx, ly = x - ux * R_ICON, y - uy * R_ICON
    ax.scatter(lx, ly, s=120, marker="v", zorder=6)

    # load label further inward
    carrier = row.get("carrier", "")
    p_set = row.get("p_set", np.nan)
    tx, ty = x - ux * R_TEXT, y - uy * R_TEXT
    ax.text(
        tx, ty,
        f"{ld}\n{carrier}, p_set={p_set:g}",
        ha="center", va="center",
        fontsize=7, color="black",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7),
        zorder=7,
    )

# ------------------------------------------------------------------------------
#   Plot DevNet SLD: A PyPSA network
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print(f"Plot {DEVNET_NAME} : A PyPSA network…\n")

# plt.tight_layout()
# Plot explicit spacing control (prevents title overlap)
fig.subplots_adjust(
    top=0.95,      # keep title visible
    bottom=0.05,
    left=0.05,
    right=0.95,
    hspace=0.0     # no vertical squeeze
)
plt.savefig(os.path.join(PLOT_PATH, f"{DEVNET_NAME}.png"), dpi=150)
plt.show()
input(f"ASR-DBG: Confirm PyPSA line plot OK\nPress Enter to continue...\n")

# ------------------------------------------------------------------------------
#   Export DevNet SLD as CSVs
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print(f"Exporting {DEVNET_NAME} network CSVs:\n\t{DEVNET_BLD_DIR}...\n")
devnet.export_to_csv_folder(DEVNET_BLD_PATH)
input(f"ASR-DBG: Confirm network CSVs exists at:\t{DEVNET_BLD_DIR}\nPress Enter to continue...\n")

# ------------------------------------------------------------------------------
# --- Tear down (IMPORTANT: restore orig stdout, stderr handles, then close) ---
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("Tearing down logging redirection...")
sys.stdout = _orig_stdout
sys.stderr = _orig_stderr
# Close the extra log stream
_log_file_for_prints.close()
# ------------------------------------------------------------------------------
# END OF devnet_sld.py
# ------------------------------------------------------------------------------




