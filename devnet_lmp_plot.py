"""
devnet_lmp_plot.py

Objective
- Visualize DevNet Monte Carlo (mc) bus perturbation cases against LMP spread, with
  aligned congestion/feasibility context.

What it does
- Reads a DevNet MC/LMP worksheet from devnet_plots.xlsx and produces a figure with:
  - Left: MC table (bus mc values per case) with highlight rules.
  - Middle: heatmap where color encodes LMP spread (replicated across bus columns).
  - Right: metrics panel (max_loading_pu heatbar, near_bind_ct heatbar, objective sparkline,
    and top congested lines text filtered by loading >= 0.95).

Inputs
- Excel file: <script_dir>/denvnet-stress-vectors/devnet_plots.xlsx
- Sheet: DevNetGen_mc<>LMP
- Header row index: HDR_ROW (default 4)
- Expected fields: bus mc columns (WECC_NW, WECC_SW, SPP_MISO, PJM_NE, SERC_SE, ERCOT),
  lmp_spread, objective, max_loading_pu, near_bind_ct, top line labels + loading columns.

Outputs
- PNG file: <script_dir>/denvnet-stress-vectors/heatmap_lmp_spread.png
- Console: prints output path; raises KeyError if required columns are missing.
"""

import os
import shutil
import tempfile
import pandas as pd
import matplotlib.pyplot as plt

import numpy as np
from matplotlib.colors import BoundaryNorm

from matplotlib.ticker import FuncFormatter

# ------------------------------------------------------------------------------
#   Configuration: paths, filenames, worksheet selection
# ------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_VECTORS_DIR_NAME = "denvnet-stress-vectors"

DEVNET_XLSX_NAME = "devnet_plots.xlsx"
SHEET_NAME = "DevNetGen_mc<>LMP"
DEVNET_XLSX_PATH = os.path.join(SCRIPT_DIR, TEST_VECTORS_DIR_NAME)
DEVNET_XLSX = os.path.join(DEVNET_XLSX_PATH, DEVNET_XLSX_NAME)

HEAT_MAP_PNG_NAME = "heatmap_lmp_spread.png"
HEAT_MAP_PNG_PATH = os.path.join(SCRIPT_DIR, "denvnet-stress-vectors")
HEAT_MAP_PNG = os.path.join(HEAT_MAP_PNG_PATH, HEAT_MAP_PNG_NAME)

# ------------------------------------------------------------------------------
#   Helpers: formatting / labels
# ------------------------------------------------------------------------------
# ----- Build y-axis labels from mc_bus values -----
def fmt_mc(row):
    return (
        f"WECC_NW={row['WECC_NW']}, "
        f"WECC_SW={row['WECC_SW']}, "
        f"SPP_MISO={row['SPP_MISO']}, "
        f"PJM_NE={row['PJM_NE']}, "
        f"SERC_SE={row['SERC_SE']}, "
        f"ERCOT={row['ERCOT']}"
    )

# ------------------------------------------------------------------------------
#   Load input workbook (copy to temp, read sheet, normalize headers)
# ------------------------------------------------------------------------------
tmp_dir = tempfile.mkdtemp()
tmp_xlsx = os.path.join(tmp_dir, os.path.basename(DEVNET_XLSX))

shutil.copy2(DEVNET_XLSX, tmp_xlsx)

# ----- Read Excel with explicit header row -----
HDR_ROW = 4  # zero-based index (row 6 in Excel)
df = pd.read_excel(tmp_xlsx, sheet_name=SHEET_NAME, header=HDR_ROW)

# Clean columns
df = df.dropna(axis=1, how="all")
df.columns = [str(c).strip() for c in df.columns]

shutil.rmtree(tmp_dir)

# ------------------------------------------------------------------------------
#   Build heatmap input: index selection + LMP spread extraction
# ------------------------------------------------------------------------------
# Expected columns:
# - commit (or case)
# - WECC_NW, WECC_SW, SPP_MISO, PJM_NE, SERC_SE, ERCOT
# - lmp_spread
bus_cols = ["WECC_NW", "WECC_SW", "SPP_MISO", "PJM_NE", "SERC_SE", "ERCOT"]

# Create a matrix where each cell is MC, and row color encodes LMP spread
# (Heatmap: MC values; overlay bar for LMP spread is clearer, but you asked “Color: LMP spread”)
# So: color = lmp_spread, columns = buses, rows = commits/cases.
# We replicate lmp_spread across bus columns to create a heatmap.
# Pick an index column robustly
cands = ["commit", "case", "Case", "CASE", "test_case", "TestCase", "Test Case", "Commit"]
idx_col = next((c for c in cands if c in df.columns), None)

if idx_col is None:
    # fallback: use the first column as the index
    idx_col = df.columns[0]

# Normalize lmp_spread column name (common variants)
lmp_col = next((c for c in df.columns if "lmp" in str(c).lower() and "spread" in str(c).lower()), None)
if lmp_col is None:
    raise KeyError(f"Could not find LMP spread column. Columns={list(df.columns)}")
# Create DataFrame for heatmap
z = df.set_index(idx_col)[lmp_col].astype(float)

heat = pd.DataFrame({c: z for c in bus_cols})

# ----------------------------------------------------------------------
#   Figure layout: table + heatmap + metrics panel
# ----------------------------------------------------------------------
import matplotlib.gridspec as gridspec

nrows = len(heat.index)

fig = plt.figure(figsize=(20, max(4, 0.55 * nrows)))
gs = gridspec.GridSpec(
    nrows=1, ncols=3,
    width_ratios=[2.2, 3.0, 1.8],  # table | heatmap | metrics panel
    wspace=0.08
)

ax_tbl = fig.add_subplot(gs[0, 0])
ax_hm  = fig.add_subplot(gs[0, 1])
ax_met = fig.add_subplot(gs[0, 2])  # metrics panel (we'll subdivide inside)

# --- Heatmap (right) with discrete colorbar ---
vals = np.array(sorted(set(float(x) for x in z.values)))  # unique LMP spreads

if len(vals) == 1:
    boundaries = np.array([vals[0] - 0.5, vals[0] + 0.5])
else:
    mid = (vals[:-1] + vals[1:]) / 2.0
    boundaries = np.concatenate(([vals[0] - (mid[0] - vals[0])], mid, [vals[-1] + (vals[-1] - mid[-1])]))

norm = BoundaryNorm(boundaries, ncolors=256, clip=True)
im = ax_hm.imshow(heat.values, aspect="auto", norm=norm)

ax_hm.set_xticks(range(len(bus_cols)))
ax_hm.set_xticklabels(bus_cols, rotation=45, ha="right")

# Use simple row numbers on heatmap y-axis (table carries the MC detail)
ax_hm.set_yticks(range(nrows))
ax_hm.set_yticklabels([str(i+1) for i in range(nrows)])

cbar = fig.colorbar(im, ax=ax_hm, ticks=vals)
cbar.set_label("LMP spread")
cbar.ax.set_yticklabels([str(int(v)) if float(v).is_integer() else str(v) for v in vals])

ax_hm.set_title("LMP spread vs test case (replicated across buses)")

# ------------------------------------------------------------------------------
#    Build metrics panel (far right): max_loading_pu + 
#       near_bind_ct heatbars + top_lines text
# ------------------------------------------------------------------------------
# Column detection (robust to slight header changes)
def find_col(substrs):
    for c in df.columns:
        s = str(c).lower().replace(" ", "").replace("_", "")
        if all(sub in s for sub in substrs):
            return c
    return None

col_maxload = find_col(["max", "loading", "pu"]) or find_col(["maxloadingpu"])
col_near    = find_col(["near", "bind", "ct"]) or find_col(["nearbindct"])

col_obj = find_col(["objective"]) or find_col(["obj"])
if col_obj is None:
    raise KeyError(f"Missing objective column. Have columns={list(df.columns)}")

# Your Excel uses top1_line/top2_line/top3_line + loading_pu... columns (not a single top_lines string)
col_top1 = "top1_line" if "top1_line" in df.columns else None
col_top2 = "top2_line" if "top2_line" in df.columns else None
col_top3 = "top3_line" if "top3_line" in df.columns else None

# Loading columns are fixed in this sheet (adjacent to top1/top2/top3)
col_ld1 = "loading_pu\nPower Distribution Factor (PDF)"
col_ld2 = "loading_pu\nPower Distribution Factor (PDF).1"
col_ld3 = "loading_pu\nPower Distribution Factor (PDF).2"

for c in (col_ld1, col_ld2, col_ld3):
    if c not in df.columns:
        raise KeyError(f"Missing expected loading column: '{c}'. Columns={list(df.columns)}")

# ------------------------------------------------------------------------------
#   Assemble per-case metrics (max loading, near-bind, objective, top lines)
# ------------------------------------------------------------------------------
# Collect metric values in row order
maxload_vals = []
near_vals = []
obj_vals = []
toplines_txt = []

for idx in heat.index:
    r = df.loc[df[idx_col] == idx].iloc[0]
    maxload_vals.append(float(r[col_maxload]))
    near_vals.append(int(r[col_near]))
    obj_vals.append(float(r[col_obj]))

    kept = []
    # top1
    if col_top1 and pd.notna(r[col_top1]) and float(r[col_ld1]) >= 0.95:
        kept.append(str(r[col_top1]).strip())
    # top2
    if col_top2 and pd.notna(r[col_top2]) and float(r[col_ld2]) >= 0.95:
        kept.append(str(r[col_top2]).strip())
    # top3
    if col_top3 and pd.notna(r[col_top3]) and float(r[col_ld3]) >= 0.95:
        kept.append(str(r[col_top3]).strip())

    toplines_txt.append("\n".join(kept))

maxload_arr = np.array(maxload_vals).reshape(nrows, 1)
near_arr    = np.array(near_vals).reshape(nrows, 1)

# ------------------------------------------------------------------------------
#   Metrics panel rendering (heatbars + objective sparkline + top-lines text)
# ------------------------------------------------------------------------------
# Subdivide the metrics panel into 3 stacked axes: maxload | nearbind | toplines
ax_met.axis("off")
met_gs = gridspec.GridSpecFromSubplotSpec(
    nrows=1, ncols=4, subplot_spec=gs[0, 2],
    width_ratios=[1.0, 1.0, 1.2, 2.2], wspace=0.20
)

ax_ml  = fig.add_subplot(met_gs[0, 0])
ax_nb  = fig.add_subplot(met_gs[0, 1])
ax_obj = fig.add_subplot(met_gs[0, 2])  # objective sparkline
ax_tl  = fig.add_subplot(met_gs[0, 3])

# Heatbar: max_loading_pu
im_ml = ax_ml.imshow(maxload_arr, aspect="auto")
ax_ml.set_title("max\nload", fontsize=9)
ax_ml.set_xticks([])
ax_ml.set_yticks(range(nrows))
ax_ml.set_yticklabels([])

# write values inside the bar
for i, v in enumerate(maxload_vals):
    ax_ml.text(
        0, i, f"{v:.2f}",
        ha="center", va="center", fontsize=9,
        bbox=dict(facecolor="white", edgecolor="none", boxstyle="round,pad=0.15")
    )
# Legend for max loading pu (bar)- commened out to reduce clutter
# fig.colorbar(im_ml, ax=ax_ml, fraction=0.046, pad=0.02)

# Heatbar: near_bind_ct
im_nb = ax_nb.imshow(near_arr, aspect="auto")
ax_nb.set_title("near\nbind", fontsize=9)
ax_nb.set_xticks([])
ax_nb.set_yticks(range(nrows))
ax_nb.set_yticklabels([])

# write values inside the bar
for i, v in enumerate(near_vals):
    ax_nb.text(
        0, i, f"{int(v)}",
        ha="center", va="center", fontsize=9,
        bbox=dict(facecolor="white", edgecolor="none", boxstyle="round,pad=0.15")
    )
# Legend for near bind ct (bar) - commented out to reduce clutter
# fig.colorbar(im_nb, ax=ax_nb, fraction=0.046, pad=0.02)

# Sparkline: objective vs row (aligned with cases)
ax_obj.set_title("obj", fontsize=9)
y = np.arange(nrows)

ax_obj.plot(obj_vals, y, marker="o", markersize=2, linewidth=1)
ax_obj.invert_yaxis()
ax_obj.set_yticks([])
ax_obj.tick_params(axis="x", labelsize=8)
# Show plain numbers (millions) on ticks
ax_obj.xaxis.set_major_formatter(
    FuncFormatter(lambda x, _: f"{x/1e6:.1f}")
)
# Single unit label at the bottom
ax_obj.set_xlabel("$M", fontsize=8, labelpad=4)

# keep it clean
ax_obj.spines["top"].set_visible(False)
ax_obj.spines["right"].set_visible(False)
ax_obj.spines["left"].set_visible(False)
ax_obj.grid(False)

# Text column: top_lines (already pre-filtered for >=0.95)
ax_tl.axis("off")
ax_tl.set_title("top_lines (>=0.95)", fontsize=9)

for i, txt in enumerate(toplines_txt):
    ax_tl.text(0.0, 1.0 - (i + 0.5) / nrows, txt, fontsize=8, va="center")

# ------------------------------------------------------------------------------
#   MC table rendering (with highlight rules + legend)
# ------------------------------------------------------------------------------
# Build the table data in the same row order as the heatmap
mc_rows = []
for idx in heat.index:
    r = df.loc[df[idx_col] == idx].iloc[0]
    mc_rows.append([r[c] for c in bus_cols])

ax_tbl.axis("off")
tbl = ax_tbl.table(
    cellText=mc_rows,
    colLabels=bus_cols,
    rowLabels=[str(i+1) for i in range(nrows)],
    loc="center"
)

tbl.auto_set_font_size(False)
tbl.set_fontsize(9)
tbl.scale(1.0, 1.5)

# Color rules:
# - PJM_NE=60: RED + BOLD (cell text)
# - Any mc=50: BLUE (cell text)
for (row, col), cell in tbl.get_celld().items():
    # header row
    if row == 0:
        cell.set_text_props(weight="bold")
        continue

    # data cells: row>=1, col>=0
    if row >= 1 and col >= 0:
        v = mc_rows[row-1][col]
        bus = bus_cols[col]

        if bus == "PJM_NE" and float(v) == 60.0:
            cell.get_text().set_color("red")
            cell.get_text().set_weight("bold")
        elif float(v) == 50.0:
            cell.get_text().set_color("blue")

# Small legend under the table
ax_tbl.text(
    0.0, -0.05,
    "Cell color rules: PJM_NE=60 → red/bold | mc=50 → blue",
    transform=ax_tbl.transAxes,
    fontsize=9,
    ha="left",
    va="top"
)

# ------------------------------------------------------------------------------
#   Export + close
# ------------------------------------------------------------------------------
# fig.tight_layout()  # not compatible with tables
# fig.tight_layout()
fig.savefig(HEAT_MAP_PNG, dpi=200, bbox_inches="tight")
print("Wrote heatmap to", HEAT_MAP_PNG)
plt.close(fig)
# ------------------------------------------------------------------------------