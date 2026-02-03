# DevNet – Datacenter BYOG DoE (PyPSA)

This repository contains a **research-grade DevNet workflow** for studying datacenter
**Bring-Your-Own-Generation (BYOG)** impacts on grid feasibility, congestion, and
Locational Marginal Prices (LMPs), using **PyPSA**.

The project is designed as a **deterministic, lightweight “USA-lite” 6-bus system**
that supports systematic stress testing, reproducible plots, and supervisory reporting,
while remaining structurally compatible with PyPSA-USA scale-up.

---

## High-level workflow

The intended execution flow is **menu-driven** via `devnet_menu.py`:

```bash
    1. Build SLD once        → devnet_sld.py
    2. Run DoE sanity once   → devnet_doe.py
    3. Stress / asymptotes   → devnet_stress.py   (iterative)
    4. Plot load metrics     → devnet_load_plot.py
    5. Plot MC + LMP heatmap → devnet_lmp_plot.py
    6. Plot line deration    → devnet_line_plot.py
```

**Important**
- Steps **(1)** and **(2)** should only be re-run if you intentionally want to
  rebuild the base DevNet.
- Step **(3)** is the primary research loop.
- Steps **(4)**, **(5)**, and **(6)** are fast, repeatable visualization passes.

---

## Entry point

### Run the menu
```bash
    python devnet_menu.py
```

This launches an interactive CLI that:

* Runs scripts in the correct order
* Preserves the active Python environment
* Keeps console output structured and readable

---

## Script overview

### `devnet_sld.py` — Network construction

* Builds a **6-bus USA-lite DevNet**
* Exports CSVs, logs, and an SLD image
* Output directory:

```bash
    ./devnet-sld/
        ├─ csv/
        ├─ plots/
        └─ logs/
```

### `devnet_doe.py` — Sanity & baseline validation

* Loads exported DevNet CSVs
* Confirms DC-OPF feasibility and baseline behavior
* Acts as a “known-good” checkpoint

### `devnet_stress.py` — Core research engine

* Interactive stress testing and asymptote discovery
* Supports:

  * Load scaling (`k_load`)
  * Corridor derating (`k_line`)
  * Generator marginal cost perturbations (`mc_bus`)
  * Optional datacenter injection (BYOG)
* Each committed run generates:

```bash
  ./devnet-sld/stress_out/
    ├─ c1_*.csv
    ├─ c1_dashboard.md
    ├─ c2_*.csv
    ├─ c2_dashboard.md
    └─ index.html
```

* `index.html` is automatically regenerated after each commit.

For replication of published results, see **Replication notes (reference runs)** below,
including `devnet_stress_tc.md` and `DevNet Stress Report_5.html`.

### `devnet_load_plot.py` — Load vs system metrics

* Produces a 4-panel stacked plot:

  1. System objective (cost)
  2. LMP spread
  3. Maximum line loading (p.u.)
  4. Near-binding constraint count
* Used to identify:

  * Feasibility boundaries
  * Linear cost scaling with load
* Output:

```bash
    ./devnet-sld/stress_out/load_vs_metrics.png
```

This plot is generated from the consolidated workbook `devnet_plots.xlsx`
assembled as described in **Replication notes (reference runs)**.

### `devnet_lmp_plot.py` — MC table + LMP heatmap

* Composite visualization:

  * Left: MC perturbation table (per bus)
  * Middle: LMP spread heatmap (case-aligned)
  * Right: metrics panel:

    * max_loading_pu
    * near_bind_ct
    * objective sparkline
    * top congested lines
* Directly links:
  **perturbation → congestion → LMP separation**
* Output:

```bash
  ./devnet-sld/stress_out/heatmap_lmp_spread.png
```

This plot consumes LMP spread test cases extracted from the reference stress report
and compiled into `devnet_plots.xlsx` (see **Replication notes (reference runs)**).

### `devnet_line_plot.py` — Line deration vs system metrics

* Produces a 4-panel stacked plot against **transmission line deration (k_line)**:

  1. System objective (cost)
  2. LMP spread
  3. Maximum line loading (p.u.)
  4. Near-binding constraint count

* X-axis is ordered as:
  **1.0 → 0.8 → 0.6 → 0.4 → 0.2 → 0.1**

* Used to isolate **pure network capacity stress** effects independent of load growth.

* Output:

```bash
  ./devnet-sld/stress_out/line_vs_metrics.png
```

Line-deration results are sourced from manually extracted reference cases and compiled
into `devnet_plots.xlsx` as documented in **Replication notes (reference runs)**.

---

## Visualization & reporting

After running stress cases:

* Open the interactive report:

  ```
  ./devnet-sld/stress_out/index.html
  ```
* Regenerate plots at any time using menu options **(4)**, **(5)**, and **(6)**

> Note: Plot scripts expect `devnet_plots.xlsx` to exist.
> If missing, run **devnet_stress.py** first.

---

## Replication notes (reference runs)

This repository includes **reference artifacts** to support replication of published
DevNet stress results without requiring an identical interactive replay.

### Reference stress cases and reports

- **Test case definitions**
  - See: `denvnet-stress-vectors/devnet_stress_tc.md`
  - Documents the exact set of stress scenarios executed (load, LMP, and line-deration cases).

- **Reference stress report**
  - See: `denvnet-stress-vectors/DevNet Stress Report_5.html`
  - Snapshot of `index.html` corresponding to a full execution of
    `devnet_stress_tc.md`.

### Manual extraction workflow (used for plotting)

The composite plotting scripts (`devnet_*_plot.py`) consume a consolidated workbook
`devnet_plots.xlsx`, which is constructed as follows:

1. From **DevNet Stress Report_5.html**, manually extract:
   - Load stress cases → `devnet_load_tc.xlsx`
   - LMP spread cases → `devnet_lmp_tc.xlsx`
   - Line deration cases → `devnet_line_tc.xlsx`

2. Place the extracted files in: `devnnet-stress-vectors/`

3. Manually compile the extracted tables into a single workbook: `devnet_plots.xlsx` with each table placed under the expected sheet names.

4. A **reference copy** of `devnet_plots.xlsx` corresponding to
**DevNet Stress Report_5.html** is provided in: `devnnet-stress-vectors/`

This approach ensures deterministic reproduction of plots while keeping the
interactive `devnet_stress.py` workflow flexible and research-oriented.

---

## Design philosophy

* **Research-grade determinism** (no hidden state)
* **Fast iteration** (small network, structured sweeps)
* **Clear causal traceability**

  * perturbation → constraint → LMP
* **Supervisor-ready artifacts**

  * CSVs, dashboards, publication-quality plots

---

## Dependencies

* Python 3.10+
* PyPSA
* pandas
* numpy
* matplotlib
* openpyxl

(Use the same environment for all scripts; `devnet_menu.py` preserves it.)

---

## Status

* Stable
* Reproducible
* Actively used for PhD research on datacenter BYOG and grid stress behavior

---

## Next steps (planned)

* Analysis module (post-processing, hypothesis tests)
* Scaling bridge to PyPSA-USA
* Automated scenario batch runs

---

## Environment & setup

The `pypsa-zn` workflow has been **developed and tested** in the following environment:

### Tested environment

- **Operating system**
  - Windows 11 Pro (x64)  
    - Primary development and test environment.
  - Ubuntu 22.04 LTS (x86_64)  
    - Preliminary validation only.  
    - Full replication runs pending.  
    - Replication steps may differ from Windows due to native Linux server graphics
      support limitations (headless environments).

- **Python**
  - Python **3.10.x**
  - Python **3.11.x** (verified working)

- **Core packages**
  - pypsa
  - numpy
  - pandas
  - matplotlib
  - openpyxl
  - scipy
  - networkx

- **Solver**
  - HiGHS (via PyPSA default configuration)
  - Tested using PyPSA’s built-in solver interface

### Recommended setup (clean install)

```bash
python -m venv pypsa-zn-env
source pypsa-zn-env/bin/activate   # Linux / macOS
pypsa-zn-env\Scripts\activate      # Windows

pip install --upgrade pip
pip install pypsa numpy pandas matplotlib scipy networkx openpyxl
```

---

## Academic contribution

This work contributes a **research-grade, reproducible framework** for studying datacenter
Bring-Your-Own-Generation (BYOG) impacts on power system feasibility, congestion, and
locational marginal prices (LMPs). By combining a deliberately lightweight but structurally
faithful 6-bus “USA-lite” DevNet with systematic stress testing (load growth, corridor
derating, and marginal cost perturbations), the framework enables clear causal tracing from
datacenter-driven perturbations to binding constraints and nodal price separation. The
approach bridges the gap between abstract academic test cases and operator-relevant grid
behavior, providing a scalable experimental scaffold that can be extended toward
PyPSA-USA–scale formulations while preserving interpretability, determinism, and
publication-quality artifacts.

---

## AI assistance

This work benefited from the use of ChatGPT (OpenAI) as a productivity aid for code
organization, documentation, and workflow clarity. All modeling decisions, analysis, and
interpretation remain the responsibility of the author.

---