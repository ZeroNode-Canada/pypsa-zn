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

------------------------------------------------------------------------

## Workflow

The primary workflow is menu-driven through:

``` bash
python devnet_menu.py
```

``` text
Configure
   ↓
Build DevNet / DevNetDC
   ↓
Stress / Commit OPF results
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
devnet_sld.py / devnetDC_sld.py
      ↓
devnet_stress.py
      ↓
devnet_*_plot.py
      ↓
devnet_pub_figs.py
      ↓
demo/pypsa_zn_demo.py
```

------------------------------------------------------------------------

## Repository Structure

``` text
pypsa-zn/
│
├── README.md
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
├── pso_config.py
├── pso.local.toml.example
├── ercot7k/
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

`devnet_pub_figs.py` generates publication artifacts into:

``` text
./pub_figs/
```

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

------------------------------------------------------------------------

## ERCOT Texas7k PSO Full-Cycle Case (PSO-only track)

A separate, PSO-only track lets you run the public **ERCOT Texas7k** case
(6717 buses, 9140 branches, 634 injectors) full-cycle through PSO, driven
from Python via `aimmspy` and your own AIMMS install/license. It does not
build or touch a PyPSA network, and it does not modify `lib/devnet_stress_lib.py`
or `devnet_stress.py` -- it is a sibling to `devnetDC_sld.py`, not a
replacement.

``` text
ercot7k/                 Texas7k PSO input tables
pso_config.py            pso.local.toml -> DEVNET_PSO_* env defaults
pso.local.toml.example   copy to pso.local.toml and edit
ercot7k_pso.py           the runner (option 3 -> PSO route, in devnet_menu.py)
```

### PSO/AIMMS Environment Dependencies

The PSO ERCOT Texas7k workflow requires:

- A separately installed and licensed AIMMS environment (26.1.x tested).
- The Polaris PSO model project (`PSO.aimms`), obtained separately from Polaris.
- The `aimmspy` Python package.
- A dedicated Python virtual environment (`.venv-pso`).

**Important:** `aimmspy` must remain separate from the PyPSA environment because of incompatible optimization dependencies. Do not install `aimmspy` into the existing PyPSA environment.

#### Create the PSO Virtual Environment

Open PowerShell in the `pypsa-zn` repository root:

```powershell
cd "C:\path\to\your\pypsa-zn"
python -m venv .venv-pso
```

This creates:

```text
pypsa-zn/
├── .venv/           # Optional PyPSA environment
└── .venv-pso/       # PSO/AIMMS Python environment
```

The `.venv-pso` directory is local to the repository and should not be committed to Git.

#### Install aimmspy

From the repository root:

```powershell
.\.venv-pso\Scripts\python.exe -m pip install --upgrade pip
.\.venv-pso\Scripts\python.exe -m pip install aimmspy
```

#### Verify aimmspy Installation

```powershell
.\.venv-pso\Scripts\python.exe -c "import aimmspy; print('aimmspy OK:', aimmspy.__version__)"
```

Example validated output:

```text
aimmspy OK: 26.1.8.3
```

This confirms that `aimmspy` is installed in the dedicated PSO environment.

#### Configure pso.local.toml

Copy the supplied configuration template:

```powershell
Copy-Item pso.local.toml.example pso.local.toml
```

If `pso.local.toml` already exists, retain and edit it rather than overwriting it.

Configure at least the following entries:

```toml
project = "C:/path/to/PSO/PSO.aimms"
python = "C:/path/to/pypsa-zn/.venv-pso/Scripts/python.exe"
```

**Windows path convention:** Use forward slashes (`/`) in the TOML path strings.

The `python` path must point to the `.venv-pso` environment created above, under the actual repository directory.

For example, if the repository is located at:

```text
C:\Development\pypsa-zn
```

then configure:

```toml
python = "C:/Development/pypsa-zn/.venv-pso/Scripts/python.exe"
```

The `project` entry must point to the separately installed Polaris PSO AIMMS project.

Leave `license_url` commented out when using an existing machine-configured AIMMS license.

#### Optional Interpreter Override — PowerShell

The PSO runner reads the configured `python` entry from `pso.local.toml` through `pso_config.py`.

Therefore, the following environment-variable override is **not required** when `pso.local.toml` is correctly configured:

```powershell
$env:DEVNET_PSO_PYTHON = (Resolve-Path ".\.venv-pso\Scripts\python.exe").Path
```

This PowerShell command is useful only for troubleshooting or temporarily overriding the configured PSO interpreter.

An explicitly set `DEVNET_PSO_PYTHON` environment variable takes precedence over the corresponding `pso.local.toml` entry.

#### Verify PSO Execution

From the repository root:

```powershell
python ercot7k_pso.py
```

This directly tests the PSO runner, bypassing `devnet_menu.py`.

A successful run should invoke AIMMS/CPLEX and generate the ERCOT Texas7k optimization results.

#### Run Through DevNet Menu

```powershell
python devnet_menu.py
```

Select:

```text
3) Datacenter case -- choose the engine route
   → PSO route
   → Run the base case, full cycle
```

The menu invokes `ercot7k_pso.py`, which uses the configured `.venv-pso` interpreter for PSO execution.

**Validated configuration:** Windows 11, Python 3.13, `aimmspy 26.1.8.3`, AIMMS 26.1.x, with 221/221 optimal solves in the ERCOT Texas7k full-cycle case.

### Running it

``` bash
python ercot7k_pso.py
```

or from `python devnet_menu.py`, option 3 (Datacenter case) -> PSO route ->
base case; the same option 3 reaches the PyPSA DevNet build, so the two engine
routes sit side by side. The runner prompts for a run name, prints a pre-flight
summary, gates on confirmation, and verifies the result out of
`results_ED_Ara.csv` rather than trusting the return code. Case details,
attribution and known data caveats are in `ercot7k/README.md`.

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

See [PSO/AIMMS Environment Dependencies](#psoaimms-environment-dependencies) for installation and configuration.

### Tested Python Environment

The current DevNet workflow has been validated using the installed Microsoft Store Python 3.13 environment:

```text
Python 3.13

C:\Users\ashok\AppData\Local\Microsoft\WindowsApps\
PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe
```

A project-local Python virtual environment is **not required** to run the currently validated DevNet workflow.

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

See:

-   `LICENSE`
-   `NOTICE`
-   `THIRD_PARTY_LICENSES.md`
-   `CONTRIBUTING.md`
-   `CLA.md`

for licensing, attribution, contribution, and third-party dependency
information.
