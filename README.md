SPDX-License-Identifier: Apache-2.0\
Copyright 2026 ZeroNode

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at:

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

Results and reference artifacts under `devnet-stress-vectors/` and
`devnet-reference-runs/` are provided for research replication and are
not part of the licensed source code.

# PyPSA-ZN DevNet --- Datacenter BYOG Grid Modeling

`pypsa-zn` is a research-grade PyPSA workflow for studying datacenter
**Bring-Your-Own-Generation (BYOG)** interaction with the electricity
grid.

The framework uses a deterministic, lightweight six-bus **USA-lite
DevNet** to investigate:

-   Datacenter load growth and load flexibility.
-   Datacenter BYOG participation.
-   Generation availability and derating.
-   Transmission reliability and congestion.
-   System feasibility and generator dispatch.
-   Bus import/export.
-   Locational Marginal Prices (LMPs).
-   System operating cost.

The small network is intentionally designed for interpretability,
controlled experimentation, regression testing, and publication-quality
analysis while remaining structurally compatible with future
larger-network studies.

The framework also provides an independent **Polaris PSO/AIMMS integration**
for studying datacenter load, BYOG, and transmission constraints on the
ERCOT Texas7k synthetic transmission network.

The two modeling routes are complementary:

- **PyPSA DevNet:** Controlled six-bus experiments, stress testing,
  feasibility analysis, and publication workflows.
- **Polaris PSO ERCOT7k:** Larger-network optimization, nodal screening,
  geographic visualization, and datacenter/BYOG scenario development.

For the ERCOT7k architecture, experimental design, configuration,
and researcher workflows, see
[PyPSA-ZN-ERCOT7K — Modeling and Design Guide](./PyPSA-ZN-ERCOT7K.md).

------------------------------------------------------------------------

# Table of Contents
- [PyPSA-ZN DevNet --- Datacenter BYOG Grid Modeling](#pypsa-zn-devnet-----datacenter-byog-grid-modeling)
- [Table of Contents](#table-of-contents)
  - [Workflow](#workflow)
  - [Repository Structure](#repository-structure)
  - [Source-Controlled Core](#source-controlled-core)
  - [Runtime and Generated Directories](#runtime-and-generated-directories)
    - [`devnet-sld/` and `devnetDC-sld/`](#devnet-sld-and-devnetdc-sld)
    - [`stress_out/`](#stress_out)
    - [`pub_figs/`](#pub_figs)
  - [Configuration](#configuration)
    - [Reference DevNet Configuration](#reference-devnet-configuration)
  - [Building DevNet](#building-devnet)
    - [Baseline DevNet](#baseline-devnet)
    - [Datacenter BYOG DevNet](#datacenter-byog-devnet)
  - [Stress Testing and OPF Results](#stress-testing-and-opf-results)
    - [Preview and Commit](#preview-and-commit)
  - [Diagnostic Plots](#diagnostic-plots)
  - [Publication Figure Workflow](#publication-figure-workflow)
    - [Experiment Design Workbook](#experiment-design-workbook)
    - [Journal Publication — Frozen Research Snapshot](#journal-publication--frozen-research-snapshot)
      - [Journal Directory Structure](#journal-directory-structure)
      - [Running Journal Publication](#running-journal-publication)
      - [Path Resolution](#path-resolution)
      - [Figure and Table Numbering](#figure-and-table-numbering)
      - [Research Reproducibility](#research-reproducibility)
  - [ERCOT Texas7k — PSO Modeling and Design of Experiments](#ercot-texas7k--pso-modeling-and-design-of-experiments)
    - [Research Workflow](#research-workflow)
    - [ERCOT7k PSO Menu](#ercot7k-pso-menu)
    - [Key Research Artifacts](#key-research-artifacts)
    - [PSO/AIMMS Prerequisites](#psoaimms-prerequisites)
    - [License Boundary](#license-boundary)
  - [Environment/Codebase Sanity Tests](#environmentcodebase-sanity-tests)
    - [Git Working Tree Integrity](#git-working-tree-integrity)
    - [PSO Configuration Precedence](#pso-configuration-precedence)
    - [ERCOT7k Baseline Case Integrity](#ercot7k-baseline-case-integrity)
    - [ERCOT7k Derived-Case Builder](#ercot7k-derived-case-builder)
    - [Validation Scope](#validation-scope)
  - [PSO/AIMMS Troubleshooting](#psoaimms-troubleshooting)
  - [Reference Snapshots for Developers](#reference-snapshots-for-developers)
  - [Demonstration Framework](#demonstration-framework)
    - [Building a Custom Presentation Wrapper](#building-a-custom-presentation-wrapper)
  - [Reference Research Artifacts](#reference-research-artifacts)
  - [Design Principles](#design-principles)
  - [Environment and Dependencies](#environment-and-dependencies)
    - [Tested Python Environment](#tested-python-environment)
    - [Optional Clean-Slate Virtual Environment](#optional-clean-slate-virtual-environment)
    - [Capture the Tested Environment Dependency List](#capture-the-tested-environment-dependency-list)
  - [Release Diligence](#release-diligence)
  - [Research Use](#research-use)
  - [Status](#status)
  - [Next Steps](#next-steps)
  - [AI Assistance](#ai-assistance)
  - [License and Attribution](#license-and-attribution)
    - [PSO / AIMMS Integration](#pso--aimms-integration)

------------------------------------------------------------------------

## Workflow

The primary workflow is menu-driven through:

``` bash
python devnet_menu.py
```

``` text
Configure
   ↓
Build baseline DevNet
   ↓
Datacenter case — choose engine route
   ├─ PyPSA → 6-bus DevNetDC + Datacenter BYOG
   └─ PSO   → ERCOT Texas7k (6717 buses)
   ↓
Stress / Commit OPF results (PyPSA DevNet)
   ↓
Basic diagnostic plots
   ↓
Publication figures
   ↓
Demo
```

In script terms:

``` text
devnet_cfg.py
      ↓
devnet_sld.py
      ↓
Datacenter case
      ├─ PyPSA → devnetDC_sld.py
      └─ PSO   → ercot7k_pso.py
      ↓
PyPSA research workflow
      ↓
devnet_stress.py
```

------------------------------------------------------------------------

## Repository Structure

``` text
pypsa-zn/
│
├── README.md
├── PyPSA-ZN-ERCOT7K.md
├── LICENSE
├── NOTICE
├── CONTRIBUTING.md
├── CLA.md
├── THIRD_PARTY_LICENSES.md
├── .gitignore
│
├── devnet_menu.py
├── devnet_cfg.py
├── devnet_base.py
├── devnet_sld.py
├── devnetDC_sld.py
├── devnet_doe.py
├── devnet_stress.py
├── devnet_load_plot.py
├── devnet_lmp_plot.py
├── devnet_line_plot.py
├── devnet_sys_plot.py
├── devnet_pjm_ne_lmp_plot.py
├── devnet_pub_figs.py
├── devnet_callstack.md
│
├── ercot7k_pso.py
├── ercot7k_node_screen.py
├── pso_preflight.py
├── ercot7k_build.py
├── ercot7k_case.py
├── ercot7k_results.py
├── ercot7k_sweep.py
├── pso_config.py
├── pso.local.toml.example
├── ercot7k/
├── ercot7k_geo/
│   └── texas7k_bus_coords.csv
│
├── geo-plots/
│   └── ercot7k_node_map.py
│
├── lib/
│   ├── devnet_stress_lib.py
│   └── devnet_stress_frame.html
│
├── devnet_config/
│   ├── devnet_assets.csv
│   ├── devnet_buses.csv
│   ├── devnet_carriers.csv
│   ├── devnet_dc.csv
│   └── devnet_lines.csv
│
├── devnet-stress-vectors/
│   ├── README.md
│   ├── devnetDC_sysdsg.xlsx
│   ├── devnet_load_tc.xlsx
│   ├── devnet_lmp_tc.xlsx
│   ├── devnet_line_tc.xlsx
│   ├── devnet_plots.xlsx
│   ├── devnet_plot_logic.md
│   └── devnet_stress_tc.md
│
├── devnet-reference-runs/
│   ├── devnet_config_ref/
│   └── validated historical snapshots
│
├── demo/
│   ├── README.md
│   ├── pypsa_zn_demo.py
│   ├── demo_presets.json
│   ├── pypsa-zn-dep.lst
│   ├── pypsa_zn_demo.html
│   ├── pypsa_zn_demo_land.html
│   ├── assets/
│   └── plots/
│
└── compliance/
```

Generated runtime directories such as `devnet-sld/`, `devnetDC-sld/`,
`pub_figs/`, logs, caches, and temporary outputs may also appear
locally.

The ERCOT7k workflow also generates local runtime directories:

- `ercot7k_config/` — researcher-editable datacenter, stress, and
  node-screening configurations.
- `ercot7k-derived/` — derived PSO input cases and manifests.
- `ercot7k-runs/` — baseline/derived optimization results and ranked nodes.
- `geo-plots/ercot7k_node_map.html` — standalone geographic visualization.

See [ERCOT7k Code and Data Directory Map](./PyPSA-ZN-ERCOT7K.md#code-and-data-directory-map)
for directory ownership and lifecycle.

------------------------------------------------------------------------

## Source-Controlled Core

The primary source-controlled research stack consists of:

``` text
devnet_menu.py
devnet_cfg.py
devnet_base.py
devnet_sld.py
devnetDC_sld.py
devnet_doe.py
devnet_stress.py

devnet_load_plot.py
devnet_lmp_plot.py
devnet_line_plot.py
devnet_sys_plot.py
devnet_pjm_ne_lmp_plot.py
devnet_pub_figs.py

lib/
devnet_config/
devnet-stress-vectors/
demo/
```

The separation is intentional:

-   Python files implement the modeling and analysis workflow.
-   `devnet_config/` contains user-editable model inputs.
-   `devnet-stress-vectors/` contains research experiment definitions
    and curated analysis inputs.
-   `demo/` provides a presentation-oriented interface to the same
    modeling engine.
-   `lib/` contains shared non-interactive stress and reporting logic.

------------------------------------------------------------------------

## Runtime and Generated Directories

The following directories are generated during normal operation and are
not the authoritative source definition of the model:

``` text
devnet-sld/
devnetDC-sld/
pub_figs/
plots/
logs/
demo/demo_out/
lib/__pycache__/
```

### `devnet-sld/` and `devnetDC-sld/`

Generated baseline and datacenter-enabled networks typically contain:

``` text
<selected-devnet>/
├── *.csv
├── plots/
├── logs/
└── stress_out/
```

### `stress_out/`

`devnet_stress.py` writes committed OPF results into the selected DevNet
build:

``` text
stress_out/
├── c1_*.csv
├── c1_*.json
├── c1_dashboard.md
├── c2_*.csv
├── c2_*.json
├── c2_dashboard.md
├── commit_counter.txt
├── index.html
└── _preview/
```

Committed results may include objective, total system load, generator
dispatch, bus net import/export, nodal LMP, and transmission line
loading.

### `pub_figs/`

`devnet_pub_figs.py` generates publication artifacts into the active publication root:

- Standard DevNet workflow: `pypsa-zn/pub_figs/`
- Journal workflow: `<journal-root>/pub_figs/`

The directory is created only after user confirmation.

Publication Figures and Tables are driven by:

``` text
./devnet-stress-vectors/devnetDC_sysdsg.xlsx
```

The workbook defines active/inactive Scenarios, Events, Commit IDs,
Event timing, Scenario-specific `index.html` sources, Figure/Table
artifacts, artifact numbers, Event grouping, and output filename
suffixes.

`devnet_pub_figs.py` acts as a generic parser and renderer rather than
hard-coding publication Figure numbers or Scenario identities.

------------------------------------------------------------------------

## Configuration

Run:

``` bash
python devnet_cfg.py
```

to create or update:

``` text
devnet_config/
├── devnet_buses.csv
├── devnet_lines.csv
├── devnet_assets.csv
├── devnet_dc.csv
└── devnet_carriers.csv
```

These files define the six-bus topology, line capacities, generation
capacity, regional load, generator marginal cost, datacenter
association, datacenter load, BYOG capacity, BYOG marginal cost, and
PyPSA carriers.

### Reference DevNet Configuration

`devnet_config/*.csv` files are user-editable runtime inputs generated by:

```bash
python devnet_cfg.py
````

Because these files may be modified locally during research, a known-good reference
configuration is retained under:

```text
devnet-reference-runs/devnet_config_ref/
```

The reference set provides baseline examples for:

```text
devnet_assets.csv
devnet_buses.csv
devnet_carriers.csv
devnet_dc.csv
devnet_lines.csv
```

Use these files for comparison, recovery, regression checks, or as a starting point
when recreating `devnet_config/`.

Rows below the marker:

```text
# Previous Values
```

are retained for documentation/history only and are not processed by the DevNet build
workflow. Active configuration values must remain above the `# Previous Values` row.

------------------------------------------------------------------------

## Building DevNet

### Baseline DevNet

``` bash
python devnet_sld.py
```

Output: `./devnet-sld/`

### Datacenter BYOG DevNet

``` bash
python devnetDC_sld.py
```

Output: `./devnetDC-sld/`

The datacenter model represents explicit datacenter demand together with
configurable BYOG capacity and marginal cost.

------------------------------------------------------------------------

## Stress Testing and OPF Results

Run:

``` bash
python devnet_stress.py
```

`devnet_stress.py` is the interactive researcher shell. Shared
non-interactive simulation and reporting logic resides in:

``` text
lib/devnet_stress_lib.py
```

The validated stress workflow supports:

-   Regional load scaling: `k_load`.
-   Transmission capacity reduction: `k_line`.
-   Generation capacity derating/outage: `k_gen`.
-   Generator marginal-cost changes: `mc_bus`.
-   Selectable LMP reporting bus: `lmp_bus`.
-   Datacenter load override: `dc_p_set`.
-   Datacenter BYOG capacity override: `dc_p_nom`.
-   Datacenter BYOG marginal-cost override: `byog_mc`.

Datacenter demand is independently controllable and is not silently
multiplied by regional `k_load` stress.

### Preview and Commit

A researcher can preview an experiment before committing it. Committed
runs receive sequential IDs (`c1`, `c2`, `c3`, ...), linking experiment
definitions to solved OPF results.

For detailed execution flow, see `devnet_callstack.md`.

> **Note:** The currently validated research workflow primarily uses the
> `baseline` and `single` stress scenarios. The `sweep_line` workflow is
> retained for future review and is not part of the current validated
> experiment set.

------------------------------------------------------------------------

## Diagnostic Plots

The basic plotting scripts provide diagnostic and exploratory
visualization:

``` text
devnet_load_plot.py
devnet_lmp_plot.py
devnet_line_plot.py
devnet_sys_plot.py
devnet_pjm_ne_lmp_plot.py
```

Some legacy/reference plotting workflows consume curated workbooks under
`devnet-stress-vectors/`, including `devnet_plots.xlsx`,
`devnet_load_tc.xlsx`, `devnet_lmp_tc.xlsx`, and `devnet_line_tc.xlsx`.

------------------------------------------------------------------------

## Publication Figure Workflow

Run:

``` bash
python devnet_pub_figs.py
```

or select the publication-figure option from `devnet_menu.py`. The workflow is driven by `devnet-stress-vectors/devnetDC_sysdsg.xlsx`.

### Experiment Design Workbook

`devnetDC_sysdsg.xlsx` is the primary researcher-facing workbook for defining
DevNetDC experiments and publication artifacts. It is maintained under:

```text
./devnet-stress-vectors/devnetDC_sysdsg.xlsx
````

The workbook contains a **`UsageGuide`** worksheet documenting its structure,
configuration conventions, Scenario activation rules, Event definitions,
Commit-ID mapping, Event Driver conventions, and Figure/Table artifact generation.

Researchers extending the experiment set should review the `UsageGuide` sheet
before adding or modifying Scenarios, Events, or publication artifacts.

Refer:

[UsageGuide — `devnetDC_sysdsg.xlsx`](./devnet-stress-vectors/devnetDC_sysdsg.xlsx)

``` text
Scenario
   ↓
Event definitions
   ↓
Commit IDs
   ↓
OPF results in index.html
   ↓
Artifact definitions
   ↓
Publication Figure / Table
```

Publication chronology Figures can show:

-   Objective / system feasibility.
-   Total system load.
-   Datacenter `p_set`.
-   Datacenter BYOG `p_nom`.
-   Experiment Event Drivers.

Infeasible operating intervals are explicitly identified in the
Objective panel.

Event Driver convention:

-   Grid/system failure, outage, constraint, deration, or congestion →
    **dark red**.
-   Datacenter mitigation/support actions → **blue**.

Generated publication artifacts are written to `./pub_figs/`.

### Journal Publication — Frozen Research Snapshot

`devnet_pub_figs.py` supports two publication workflows:

- **DevNet workflow:** Uses the active `pypsa-zn` experiment workbook and committed stress results.
- **Journal workflow:** Uses a separately maintained, frozen research snapshot under a user-specified journal publication directory.

The journal workflow preserves the experimental data, Commit IDs, numerical results, and publication definitions independently of ongoing `pypsa-zn` development.

#### Journal Directory Structure

The researcher must maintain:

```text
<journal-root>/
├── devnet-stress-vectors/
│   └── devnetDC_sysdsg.xlsx
├── devnetDC-sld/
│   ├── *.csv
│   ├── plots/
│   ├── logs/
│   └── stress_out/
│       ├── index.html
│       └── committed experiment results
└── pub_figs/
    ├── fig*.png
    └── table*.png
```

The complete `devnetDC-sld/` directory should be preserved from the validated research environment. The minimum result file required by the current publication renderer is `devnetDC-sld/stress_out/index.html`.

The journal-specific `devnetDC_sysdsg.xlsx` must correspond to the frozen experimental results.

**Important:** Neither the journal workbook nor the DevNetDC results snapshot is automatically regenerated, cloned, or overwritten.

#### Running Journal Publication

From the `pypsa-zn` repository root:

```powershell
python devnet_pub_figs.py
```

The script prompts:

```text
Journal publication target? (Y/N)
        ↓
YES                         NO
 ↓                           ↓
Enter journal directory     Standard DevNet workflow
 ↓
Validate journal snapshot
 ↓
Validate devnetDC_sysdsg.xlsx
 ↓
Select embedded numbering preference
 ↓
Select publication Figures / Tables
 ↓
Generate PNGs in <journal-root>/pub_figs/
```

For journal publication, the researcher supplies the journal directory path. No journal directory is hard-coded in the renderer.

If the journal results snapshot or workbook is missing, the script reports the required path and exits without generating publication artifacts.

When launched through `devnet_menu.py`, control returns to the menu after the script exits.

#### Path Resolution

The workbook is expected at:

```text
<journal-root>/devnet-stress-vectors/devnetDC_sysdsg.xlsx
```

The publication root is derived from the workbook location:

```python
project_root = workbook_path.parent.parent
```

Workbook result paths beginning with `~/` or `~\` resolve relative to this root.

Example:

```text
~\devnetDC-sld\stress_out\:index.html
```

resolves to:

```text
<journal-root>/devnetDC-sld/stress_out/index.html
```

The `--html` override is disabled in journal mode to prevent publication artifacts from accidentally using transient experimental results outside the frozen snapshot.

The standard DevNet workflow continues to resolve paths relative to the `pypsa-zn` repository.

#### Figure and Table Numbering

Publication artifact metadata is defined in the `devnetDC_dsg` worksheet of `devnetDC_sysdsg.xlsx`.

| XLSX column | Publication metadata |
|---|---|
| C | Event grouping |
| D | Artifact type: `Fig` or `Table` |
| E | Figure/Table number |
| F | Output filename suffix |

The renderer generates filenames using:

```text
fig<Number>_<Suffix>.png
table<Number>_<Suffix>.png
```

For example:

```text
fig3_Equilibrium_State.png
table3_Equilibrium_State.png
```

The filename suffix is normalized by replacing non-alphanumeric characters, except underscores, with underscores.

**Journal publication numbering option:**

```text
Embed Figure/Table numbers in journal PNGs? [Y/N, default N]
```

- **Y:** Include `Figure N.` or `Table N.` in the embedded graphical title.
- **N:** Retain the descriptive Scenario title without the Figure/Table number.
- **Standard DevNet workflow:** Embedded numbering remains enabled.

The XLSX artifact number and generated PNG filename remain unchanged regardless of the embedded numbering preference.

For IEEE journal submissions, selecting **N** avoids duplicate numbering when Pandoc/XeLaTeX generates Figure/Table captions in the manuscript.

#### Research Reproducibility

Journal publication regeneration must preserve:

- Original experiment configuration and numerical results.
- Scenario and Event definitions.
- Commit IDs and corresponding committed OPF results.
- Scenario-specific `stress_out/index.html` references.
- Frozen `devnetDC-sld/` experimental artifacts.

Publication Figure/Table numbering and graphical presentation may be updated independently without rerunning or modifying the underlying experiments.

The publication renderer remains maintained in `pypsa-zn`; each journal project retains its own validated research inputs and generated publication artifacts.

------------------------------------------------------------------------

## ERCOT Texas7k — PSO Modeling and Design of Experiments

The ERCOT Texas7k integration extends `pypsa-zn` with a separate
Polaris PSO/AIMMS optimization route for larger-network datacenter
and BYOG studies.

Unlike the six-bus PyPSA DevNet, ERCOT7k uses the separately
licensed Polaris PSO engine with AIMMS/CPLEX.

### Research Workflow

```text
ERCOT7k Baseline PSO Optimization
               ↓
       Node Screening / Ranking
               ↓
       Geographic Visualization
               ↓
       Candidate Node Selection
               ↓
       Datacenter / BYOG Configuration
               ↓
       Derived-Case Construction
               ↓
       Derived-Case PSO Optimization
               ↓
       Baseline / Derived Analysis
```

The baseline network under `ercot7k/` remains immutable.

Researchers configure screening criteria and datacenter/BYOG
experiments through CSV files rather than modifying the
baseline network directly.

### ERCOT7k PSO Menu

Launch:

```powershell
python devnet_menu.py
```

Select:

```text
3) Datacenter case
   → 2) PSO: ERCOT Texas7k
```

The PSO submenu provides:

```text
1) Run Baseline (ercot7k_pso.py)
2) Screen / Rank ERCOT7k Nodes (ercot7k_node_screen.py)
3) Plot Ranked ERCOT7k Nodes (geo-plots/ercot7k_node_map.py)
4) Configure Derived Case (ercot7k_build.py)
5) Build Derived Case (ercot7k_build.py / ercot7k_case.py)
6) Run Derived Case (ercot7k_pso.py)
7) Compare Baseline vs Derived Case [PENDING]
0) Back to main menu
```

### Key Research Artifacts

| Artifact | Purpose |
|---|---|
| `ercot7k/` | Immutable baseline PSO network inputs |
| `ercot7k_config/ercot7k_node_filters.csv` | Researcher-controlled node screening |
| `ercot7k-runs/<run>/ercot7k_node_ranked.csv` | Ranked candidate nodes |
| `ercot7k_geo/texas7k_bus_coords.csv` | Geographic node reference |
| `geo-plots/ercot7k_node_map.html` | Interactive geographic visualization |
| `ercot7k_config/ercot7k_dc.csv` | Datacenter load and BYOG configuration |
| `ercot7k_config/ercot7k_stress.csv` | Grid-stress configuration |
| `ercot7k-derived/` | Generated datacenter/stress case layers |
| `ercot7k-runs/` | PSO optimization results |

Node screening currently supports `max_spread`, `mean_spread`,
and `stress_hours` ranking metrics.

These are LMP-separation screening indicators, not independent
proof of transmission congestion or datacenter deliverability.

### PSO/AIMMS Prerequisites

The ERCOT7k optimization route requires:

- A separately installed and licensed AIMMS environment.
- Polaris PSO and its corresponding license.
- The `aimmspy` Python package.
- A dedicated `.venv-pso` Python environment.
- A machine-specific `pso.local.toml` configuration.

The PSO environment must remain separate from the PyPSA environment.

Run the environment preflight before optimization:

```powershell
python pso_preflight.py
```

For installation, Windows 11 path conventions, configuration
precedence, baseline execution, screening calculations,
geospatial architecture, derived-case construction, and
experimental reproducibility, refer to:

**[PyPSA-ZN-ERCOT7K — Modeling and Design Guide](./PyPSA-ZN-ERCOT7K.md)**

### License Boundary

Polaris PSO, AIMMS, CPLEX, their licenses, and proprietary
documentation are not distributed through this repository.

The Apache-2.0 license applies only to the appropriately
licensed ZeroNode source code and documentation.

------------------------------------------------------------------------

## Environment/Codebase Sanity Tests

These tests validate a fresh `pypsa-zn` clone, PSO configuration precedence, ERCOT7k baseline integrity, and derived-case builder availability **without launching AIMMS/CPLEX**.

Run from the `pypsa-zn` repository root using PowerShell.

### Git Working Tree Integrity

```powershell
git status -sb
git diff --check
```

`git diff --check` checks uncommitted changes for whitespace errors. It does not validate Python syntax or program behavior.

**Expected:** No whitespace errors.

### PSO Configuration Precedence

Verify that `DEVNET_PSO_CASE` overrides the `case` setting in `pso.local.toml`.

```powershell
$env:DEVNET_PSO_CASE = "ercot7k/texas7k.csv"

python -c "import os, pso_config; pso_config.load_config(); print('Selected case:', os.environ.get('DEVNET_PSO_CASE'))"

Remove-Item Env:\DEVNET_PSO_CASE -ErrorAction SilentlyContinue
```

**Expected:**

```text
Selected case: ercot7k/texas7k.csv
```

The environment override is temporary and does not modify `pso.local.toml`.

### ERCOT7k Baseline Case Integrity

```powershell
python ercot7k_case.py verify ercot7k
```

**Expected:** The verification report completes with zero warnings and zero errors.

Validated baseline example:

```text
OK=6  SKIP=13  WARNING=0  ERROR=0
```

`SKIP` results are expected for checks that apply only to derived-case layers, manifests, or datacenter/BYOG injectors.

The exact counts may vary with the ERCOT7k case version.

### ERCOT7k Derived-Case Builder

Verify that the builder CLI is available:

```powershell
python ercot7k_build.py --help
```

**Expected:** Usage information includes:

```text
--init
--show-config
--help
```

Review existing configuration inputs:

```powershell
python ercot7k_build.py --show-config
```

**Expected:**

- If `ercot7k_config/` exists, the builder displays the active datacenter and stress configuration rows.
- On a fresh clone, the builder may report `AMW-ERR: config folder not found`. This is expected before initialization and does not indicate a code regression.

Initialize the configuration templates:

```powershell
python ercot7k_build.py --init
```

Review and edit the generated CSVs before building a derived case.

**Note:** The builder initializes its logging infrastructure even when invoked with `--help`. This does not create a derived-case layer.

### Validation Scope

These sanity tests confirm:

- Git working-tree whitespace integrity.
- PSO configuration environment-variable precedence.
- ERCOT7k baseline input consistency.
- Derived-case builder CLI availability.
- Configuration template accessibility.

They do **not** execute PSO optimization or validate numerical results.

Additional ERCOT7k regression validation includes:

- `pso_preflight.py` — PSO interpreter, project and dependency checks.
- `ercot7k_node_screen.py` — nodal ranking and geographic mapping.
- `geo-plots/ercot7k_node_map.py` — standalone HTML generation.
- `ercot7k_case.py` — derived-case referential integrity.
- `devnet_menu.py` — end-to-end workflow dispatch.

The detailed validation methodology and expected artifacts are
documented in
[ERCOT7k Sanity and Regression Tests](./PyPSA-ZN-ERCOT7K.md#sanity-and-regression-tests).

For AIMMS interpreter, `aimmspy`, licensing, and PSO project setup, see [ERCOT7k Modeling and Design Guide](./PyPSA-ZN-ERCOT7K.md).

------------------------------------------------------------------------

## PSO/AIMMS Troubleshooting

Check `pso.local.toml` first when the PSO route cannot locate:

* `PSO.aimms`.
* The AIMMS installation.
* The `aimmspy` Python interpreter.
* The ERCOT Texas7k case.
* The AIMMS/PSO license.

On Windows 11, confirm all configured paths use **forward slashes**.

**PSO uses CPLEX as its optimization solver:**

The message:

```text
Unable to load IBM CPLEX library. Exiting...
```

has been observed as a **false warning in the validated integration** when the subsequent PSO solve continues successfully. **Do not terminate the run based on this message alone.** 

Allow the runner to continue and use the final solve/result verification to determine whether the run succeeded.


If the runner reports:

```text
ASR-ERR:
```

Use the displayed error, `aimms.err`, and the PSO debug log to identify the
underlying configuration or solve problem. `ercot7k_pso.py` surfaces these logs
when the run fails. 

For complete PSO environment setup and execution guidance, see
[PyPSA-ZN-ERCOT7K.md](./PyPSA-ZN-ERCOT7K.md).

For node-screening, geographic visualization, and derived-case
workflow issues, use the corresponding sections of the design guide.

For PSO installation, licensing, or AIMMS/CPLEX configuration issues, contact the Polaris development team.

------------------------------------------------------------------------

## Reference Snapshots for Developers

Validated historical builds are retained under:

``` text
devnet-reference-runs/
```

Examples include:

``` text
devnet-sld-20Mar2026/
devnetDC-sld-15Apr2026/
devnetDC-sld-04Aug2026/
devnet_config-04Aug2026/
```

These are frozen reference snapshots rather than active runtime builds.
They support regression comparison, historical traceability, research
replication, developer sanity checks, and review of generated PyPSA
network structure.

New working networks should be generated through the current source
workflow rather than by modifying these snapshots.

------------------------------------------------------------------------

## Demonstration Framework

A presentation-oriented demonstration subsystem is provided under
`./demo/`:

``` text
demo/
├── README.md
├── pypsa_zn_demo.py
├── demo_presets.json
├── pypsa-zn-dep.lst
├── pypsa_zn_demo.html
├── pypsa_zn_demo_land.html
├── assets/
└── plots/
```

The demo uses the same DevNet modeling engine as the research workflow.
It is not a separate power-system model.

Both the research shell and demonstration framework reuse:

``` text
lib/devnet_stress_lib.py
```

### Building a Custom Presentation Wrapper

Researchers can use `demo/` as the computational backend for their own
conference, classroom, laboratory, or stakeholder presentation.

A custom presentation wrapper can:

-   Present its own landing page.
-   Define its own narrative/storyboard.
-   Select predefined DevNet experiments.
-   Invoke `pypsa_zn_demo.py`.
-   Display generated scenario results.
-   Reuse or replace the supplied HTML presentation pages.
-   Add organization-specific branding outside the modeling engine.

Recommended separation:

``` text
Presentation / kiosk wrapper
          ↓
demo/pypsa_zn_demo.py
          ↓
demo_presets.json
          ↓
lib/devnet_stress_lib.py
          ↓
PyPSA DevNet
```

This allows researchers to build a custom presentation experience
without forking or rewriting the underlying DevNet OPF implementation.

See `demo/README.md` for demonstration-specific operation and
configuration.

------------------------------------------------------------------------

## Reference Research Artifacts

`devnet-stress-vectors/` contains selected research inputs and
historical artifacts used to reproduce or document earlier DevNet
experiments. These may include stress-case definitions, curated plotting
workbooks, reference stress reports, network images, and
experiment-design workbooks.

The current publication workflow uses `devnetDC_sysdsg.xlsx` as the
experiment/publication definition, while associated solved results are
obtained from the Scenario-specific committed `stress_out/index.html`.

------------------------------------------------------------------------

## Design Principles

-   **Determinism** --- explicit configuration and reproducible
    experiments.
-   **Interpretability** --- small network with transparent physical
    behavior.
-   **Causal traceability** --- perturbation → dispatch → constraint →
    system response.
-   **Shared modeling logic** --- research and demo workflows use the
    same stress engine.
-   **Separation of source and generated artifacts**.
-   **Publication reproducibility** --- Figures trace back to explicit
    Events and Commit IDs.
-   **Scalability** --- experimental methods can be transferred to
    larger PyPSA networks.

------------------------------------------------------------------------

## Environment and Dependencies

The workflow has been primarily developed and tested on:

* Windows 11 Pro x64.
* Python 3.13.
* HiGHS through the PyPSA optimization interface.

Preliminary Linux validation has also been performed on:

* Ubuntu 22.04 LTS (x86_64).

  * Preliminary validation only.
  * Full replication runs pending.

Primary Python dependencies include PyPSA, pandas, numpy, matplotlib, openpyxl, scipy, networkx, and HiGHS / `highspy`.

The PyPSA DevNet workflow uses the active Python interpreter. The PSO ERCOT Texas7k workflow requires a separate `.venv-pso` environment containing `aimmspy`, configured through `pso.local.toml`.

See [ERCOT7k Modeling and Design Guide](./PyPSA-ZN-ERCOT7K.md) for installation and configuration.

### Tested Python Environment

The PyPSA DevNet workflow has been validated on Windows 11
using Python 3.13.

The active Python interpreter can be identified using:

```powershell
python -c "import sys; print(sys.executable)"
```

A project-local virtual environment is optional for PyPSA DevNet.
The PSO route requires its own dedicated .venv-pso environment.

### Optional Clean-Slate Virtual Environment

Researchers who prefer an isolated Python environment can create one from the `pypsa-zn` repository directory:

```powershell
python -m venv pypsa-zn-env
```

This creates:

```text
pypsa-zn/
└── pypsa-zn-env/
    ├── Scripts/
    ├── Lib/
    └── pyvenv.cfg
```

Activate it in Windows PowerShell:

```powershell
.\pypsa-zn-env\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
pypsa-zn-env\Scripts\activate
```

Linux/macOS:

```bash
source pypsa-zn-env/bin/activate
```

Install the primary dependencies into the activated environment:

```powershell
python -m pip install --upgrade pip
python -m pip install pypsa numpy pandas matplotlib scipy networkx openpyxl
```

The virtual environment directory should remain a **local runtime environment** and should not be committed to the repository.

### Capture the Tested Environment Dependency List

The demo workflow includes a dependency snapshot:

``` text
demo/pypsa-zn-dep.lst
```

The supplied dependency list uses the human-readable `Package / Version`
format produced by `pip list`. From the active environment, generate or
refresh it in PowerShell with:

``` powershell
python -m pip list | Out-File -Encoding utf8 .\demo\pypsa-zn-dep.lst
```

For a standard requirements-style package snapshot instead:

``` powershell
python -m pip freeze | Out-File -Encoding utf8 .\demo\requirements-freeze.txt
```

------------------------------------------------------------------------

## Release Diligence

Before publishing or pushing a release:

-   Confirm SPDX/license headers.
-   Confirm `LICENSE`, `NOTICE`, and third-party notices.
-   Confirm no credentials, private data, or machine-specific paths are
    committed.
-   Confirm generated runtime/cache directories are excluded through
    `.gitignore`.
-   Confirm intentional reference snapshots are clearly identified.
-   Confirm README workflow matches `devnet_menu.py`.
-   Confirm `PyPSA-ZN-ERCOT7K.md` matches the implemented PSO submenu.
-   Verify ERCOT7k node screening and geographic plot generation.
-   Confirm the baseline input directory remains unchanged.
-   Confirm machine-specific `pso.local.toml` and PSO licenses are excluded.
-   Confirm generated ERCOT7k runs, derived cases, and HTML artifacts
    follow the intended Git tracking policy.
-   Run the complete validated workflow:

``` text
devnet_cfg.py
      ↓
devnet_sld.py
      ↓
devnetDC_sld.py
      ↓
devnet_stress.py
      ↓
diagnostic / publication plots
```

------------------------------------------------------------------------

## Research Use

The platform supports controlled investigation of how datacenter demand,
load flexibility, and BYOG interact with grid feasibility, generation
adequacy, transmission reliability, transmission congestion, dispatch,
system operating cost, and nodal LMP formation.

The intent is not to reproduce a specific ISO/RTO network. DevNet
provides a controlled experimental environment in which causal
mechanisms can be isolated before applying the methodology to larger and
more complex networks.

------------------------------------------------------------------------

## Status

-   Stable validated `baseline` / `single` research workflow.
-   Reproducible DevNet and DevNetDC builds.
-   Shared research/demo stress engine.
-   XLSX-driven publication Figure/Table workflow.
-   Actively used for datacenter BYOG grid research.

------------------------------------------------------------------------

## Next Steps

-   Repository release tagging and continued cleanup.
-   Automated regression test harness.
-   Post-processing and hypothesis-test modules.
-   Scaling bridge to larger PyPSA network models.
-   Continued development of research and presentation workflows.

------------------------------------------------------------------------

## AI Assistance

This work benefited from the use of ChatGPT (OpenAI) as a productivity
aid for code organization, documentation, workflow development, and
presentation support.

All modeling assumptions, experiments, results, validation, and
interpretation remain the responsibility of the authors.

------------------------------------------------------------------------

## License and Attribution

### PSO / AIMMS Integration

The Apache-2.0 license for `pypsa-zn` applies to the ZeroNode source code
distributed under that license. The optional PSO engine route integrates with
software and licenses obtained separately from Polaris Systems Optimization,
AIMMS, and their applicable third-party components.

The repository does not grant rights to PSO, AIMMS, CPLEX, proprietary PSO
documentation, or associated license files. Users of the PSO route are
responsible for obtaining the required software and licenses from their
respective providers.

See:

-   `LICENSE`
-   `NOTICE`
-   `THIRD_PARTY_LICENSES.md`
-   `CONTRIBUTING.md`
-   `CLA.md`

for licensing, attribution, contribution, and third-party dependency
information.
