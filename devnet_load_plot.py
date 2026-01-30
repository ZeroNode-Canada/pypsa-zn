"""
devnet_load_plot.py

Objective
- Generate a 4-panel stacked plot of DevNet system metrics vs total system load.

What it does
- Reads a single worksheet from devnet_plots.xlsx, auto-detects required metric columns,
  sorts cases by total system load, and saves a PNG with:
  (1) Objective (system cost) with infeasible points marked as INF,
  (2) LMP spread,
  (3) Max line loading (p.u.),
  (4) Near-bind constraint count.

Inputs
- Excel file: <script_dir>/denvnet-stress-vectors/devnet_plots.xlsx
- Sheet: DevNet_load<>SystemCost
- Header row index: HDR_ROW (default 9)

Outputs
- PNG file: <script_dir>/denvnet-stress-vectors/load_vs_metrics.png
- Console: prints output path; raises KeyError if required columns are missing.
"""

import os
import shutil
import tempfile
import pandas as pd
import matplotlib.pyplot as plt

import numpy as np

# ------------------------------------------------------------------------------
#   Configuration: paths, filenames, worksheet selection 
# ------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_VECTORS_DIR_NAME = "denvnet-stress-vectors"

DEVNET_XLSX_NAME = "devnet_plots.xlsx"
SHEET_NAME = "DevNet_load<>SystemCost"
DEVNET_XLSX_PATH = os.path.join(SCRIPT_DIR, TEST_VECTORS_DIR_NAME)
DEVNET_XLSX = os.path.join(DEVNET_XLSX_PATH, DEVNET_XLSX_NAME)

LOAD_PLOT_PNG_NAME = "load_vs_metrics.png"
LOAD_PLOT_PNG_PATH = os.path.join(SCRIPT_DIR, "denvnet-stress-vectors")
LOAD_PLOT_PNG = os.path.join(LOAD_PLOT_PNG_PATH, LOAD_PLOT_PNG_NAME)

# ------------------------------------------------------------------------------
#   Load input workbook (copy to temp, read sheet, normalize headers)
# ------------------------------------------------------------------------------
tmp_dir = tempfile.mkdtemp()
tmp_xlsx = os.path.join(tmp_dir, os.path.basename(DEVNET_XLSX))
shutil.copy2(DEVNET_XLSX, tmp_xlsx)

# If your sheet has a title row, set HDR_ROW accordingly (same pattern as earlier).
# If it already has clean headers on first row, set HDR_ROW=0.
HDR_ROW = 9
df = pd.read_excel(tmp_xlsx, sheet_name=SHEET_NAME, header=HDR_ROW)
shutil.rmtree(tmp_dir)

df = df.dropna(axis=1, how="all")
df.columns = [str(c).strip() for c in df.columns]

# ------------------------------------------------------------------------------
#   Column detection (robust header matching)
# ------------------------------------------------------------------------------
def find_col(keys):
    for c in df.columns:
        s = str(c).lower().replace(" ", "").replace("_", "")
        if all(k in s for k in keys):
            return c
    return None

col_load = find_col(["totalsystemload"]) or find_col(["totalload"]) or find_col(["load"])
col_obj  = find_col(["objective"]) or find_col(["operatingcost"]) or find_col(["systemcost"])
col_lmp  = find_col(["lmp", "spread"])
col_pu   = find_col(["max", "loading", "pu"]) or find_col(["maxloadingpu"])
col_nb   = find_col(["near", "bind", "ct"]) or find_col(["nearbindct"])

missing = [("Total System Load", col_load), ("objective", col_obj), ("lmp_spread", col_lmp), ("max_loading_pu", col_pu), ("near_bind_ct", col_nb)]
missing = [name for name, col in missing if col is None]
if missing:
    raise KeyError(f"Missing required columns: {missing}. Have columns={list(df.columns)}")

# ------------------------------------------------------------------------------
#   Normalize types, validate required fields, sort by total load
# ------------------------------------------------------------------------------
df = df.copy()
df[col_load] = pd.to_numeric(df[col_load], errors="coerce")
df[col_obj]  = pd.to_numeric(df[col_obj],  errors="coerce")
df[col_lmp]  = pd.to_numeric(df[col_lmp],  errors="coerce")
df[col_pu]   = pd.to_numeric(df[col_pu],   errors="coerce")
df[col_nb]   = pd.to_numeric(df[col_nb],   errors="coerce")
df = df.sort_values(col_load)

x = df[col_load].values
obj = df[col_obj].values
lmp = df[col_lmp].values
pu  = df[col_pu].values
nb  = df[col_nb].values

# ------------------------------------------------------------------------------
# Infeasible handling: map NaN objective to sentinel + annotate as INF
# ------------------------------------------------------------------------------
finite_obj = obj[np.isfinite(obj)]
sentinel = (np.nanmax(finite_obj) * 1.25) if finite_obj.size else 1.0
obj_plot = np.where(np.isfinite(obj), obj, sentinel)

# ------------------------------------------------------------------------------
#   Plot + export (4 stacked panels)
# ------------------------------------------------------------------------------
fig, axs = plt.subplots(4, 1, figsize=(12, 10), sharex=True)

# Objective
axs[0].plot(x, obj_plot, marker="o", linewidth=1)
axs[0].set_ylabel("Objective (USD)")
axs[0].set_title("DevNet: Load vs Objective / LMP Spread / Max Loading / Near-Bind")

# annotate infeasible points
for xi, oi, is_ok in zip(x, obj_plot, np.isfinite(obj)):
    if not is_ok:
        axs[0].annotate("INF", (xi, oi), textcoords="offset points", xytext=(0, -12), ha="center")
        axs[0].annotate("↑", (xi, oi), textcoords="offset points", xytext=(0, -2), ha="center")

# lmp_spread
axs[1].plot(x, lmp, marker="o", linewidth=1)
axs[1].set_ylabel("LMP spread")

# max_loading_pu
axs[2].plot(x, pu, marker="o", linewidth=1)
axs[2].set_ylabel("max_loading_pu")

# near_bind_ct
axs[3].plot(x, nb, marker="o", linewidth=1)
axs[3].set_ylabel("near_bind_ct")
axs[3].set_xlabel("Total System Load (MW)")

plt.tight_layout()
plt.savefig(LOAD_PLOT_PNG, dpi=200, bbox_inches="tight")
print("Wrote", LOAD_PLOT_PNG)
# ------------------------------------------------------------------------------