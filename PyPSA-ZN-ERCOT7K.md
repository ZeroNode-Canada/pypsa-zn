SPDX-License-Identifier: Apache-2.0  
Copyright 2026 ZeroNode

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at:

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

The Apache-2.0 license applies to ZeroNode source code and documentation
as described in the repository LICENSE and NOTICE files. Polaris PSO,
AIMMS, CPLEX, and their proprietary documentation and licenses are
separately governed by their respective owners.

---

# PyPSA-ZN — ERCOT Texas7k Modeling and Design Guide

## Design Scope

This document describes the architecture, configuration, execution,
experimental design, node screening, and geographic visualization
of the ERCOT Texas7k integration within pypsa-zn.

It serves as both:

- A researcher-facing guide for reproducible datacenter/BYOG experiments.
- A developer reference for extending the workflow to other regional
  transmission networks, including PJM and MISO.

The ERCOT7k optimization route uses Polaris PSO/AIMMS/CPLEX rather
than the PyPSA solver. The two modeling engines remain independent.

---

This researcher guide complements [README.md](./README.md). The ERCOT7k route in `pypsa-zn` uses separately installed/licensed Polaris PSO, AIMMS and CPLEX, **not** PyPSA. The Texas7k grid is **synthetic**, not actual ERCOT operational data. Proprietary PSO software and documentation are not distributed in this repository.

## Table of Contents

- [PyPSA-ZN — ERCOT Texas7k Modeling and Design Guide](#pypsa-zn--ercot-texas7k-modeling-and-design-guide)
  - [Design Scope](#design-scope)
  - [Table of Contents](#table-of-contents)
  - [Workflow](#workflow)
  - [Environment and setup](#environment-and-setup)
  - [Code and data directory map](#code-and-data-directory-map)
    - [Directory evolution](#directory-evolution)
  - [Baseline optimization](#baseline-optimization)
  - [Node screening and ranking](#node-screening-and-ranking)
    - [Screening parameters](#screening-parameters)
    - [Calculation basis](#calculation-basis)
    - [Node Screening Design Principles](#node-screening-design-principles)
      - [Design Objectives](#design-objectives)
      - [Screening Input and Output Architecture](#screening-input-and-output-architecture)
      - [Screening and Ranking Metrics](#screening-and-ranking-metrics)
      - [Filter Application](#filter-application)
      - [Temporal Resolution](#temporal-resolution)
      - [Scientific Interpretation](#scientific-interpretation)
      - [Extensibility](#extensibility)
    - [PSO Result Schema Inspection](#pso-result-schema-inspection)
      - [Expected Source Fields](#expected-source-fields)
      - [Extension Checklist](#extension-checklist)
  - [Geospatial visualization](#geospatial-visualization)
    - [Geospatial Design Architecture](#geospatial-design-architecture)
      - [Design Objectives](#design-objectives-1)
      - [Current Implementation — Python + Plotly](#current-implementation--python--plotly)
      - [Why Plotly?](#why-plotly)
    - [Geospatial Directory Structure](#geospatial-directory-structure)
      - [Current Validated Structure](#current-validated-structure)
      - [Optional Future React/Vite Architecture](#optional-future-reactvite-architecture)
    - [Standalone Map Sanity Test](#standalone-map-sanity-test)
    - [ZeroNode Choropleth Architecture Reference](#zeronode-choropleth-architecture-reference)
      - [Source Components](#source-components)
      - [Reusable Design Concepts](#reusable-design-concepts)
      - [Choropleth Versus Ranked-Node Maps](#choropleth-versus-ranked-node-maps)
    - [Scalability to Other Grid Regions](#scalability-to-other-grid-regions)
      - [Proposed Data Contract](#proposed-data-contract)
      - [Transmission Line Overlay — Proposed](#transmission-line-overlay--proposed)
  - [Derived datacenter and grid-stress cases](#derived-datacenter-and-grid-stress-cases)
    - [Datacenter configuration — `ercot7k_config/ercot7k_dc.csv`](#datacenter-configuration--ercot7k_configercot7k_dccsv)
    - [Stress configuration — `ercot7k_config/ercot7k_stress.csv`](#stress-configuration--ercot7k_configercot7k_stresscsv)
  - [Experiment design and reproducibility](#experiment-design-and-reproducibility)
  - [Sanity and regression tests](#sanity-and-regression-tests)
  - [Known limitations and planned extensions](#known-limitations-and-planned-extensions)
  - [License and attribution](#license-and-attribution)

---

## Workflow

Run `python devnet_menu.py`, then select **3) Datacenter case → 2) PSO ERCOT Texas7k**.

```text
1) Run Baseline (ercot7k_pso.py)
2) Screen / Rank ERCOT7k Nodes (ercot7k_node_screen.py)
3) Plot Ranked ERCOT7k Nodes (geo-plots/ercot7k_node_map.py)
4) Configure Derived Case (ercot7k_build.py --init / --show-config)
5) Build Derived Case (ercot7k_build.py / ercot7k_case.py)
6) Run Derived Case (ercot7k_pso.py)
7) Compare Baseline vs Derived Case (ercot7k_results.py) [PENDING]
0) Back to main menu
```

```text
ercot7k/ baseline → ercot7k_pso.py → ercot7k-runs/<baseline>/results/
                                           ↓
                  ercot7k_node_screen.py ← node_filters.csv + geo CSV
                                           ↓
                              ercot7k_node_ranked.csv
                                           ↓
                         geo-plots/ercot7k_node_map.py
                                           ↓
                              ercot7k_node_map.html
                                           ↓
                              Researcher selects node
                                           ↓
                  ercot7k_build.py --init / --show-config
                                           ↓
                         ercot7k_config/{dc,stress}.csv
                                           ↓
                     ercot7k_build.py → ercot7k_case.py
                                           ↓
                             ercot7k-derived/<case>/
                                           ↓
                                ercot7k_pso.py
                                           ↓
                           ercot7k-runs/<derived>/results/
                                           ↓
                              Comparison [PENDING]
```

**Baseline optimization does not require the derived-case builder.** Screening and plotting reuse solved results and do not invoke AIMMS/CPLEX.

## Environment and setup

Validated environment: Windows 11, Python 3.13, AIMMS 26.1.x and `aimmspy 26.1.8.3`. Maintain a dedicated PSO virtual environment separate from PyPSA:

```powershell
python -m venv .venv-pso
.\.venv-pso\Scripts\python.exe -m pip install --upgrade pip
.\.venv-pso\Scripts\python.exe -m pip install aimmspy
Copy-Item pso.local.toml.example pso.local.toml
```

Set **absolute paths with forward slashes** in `pso.local.toml`:

```toml
project = "C:/path/to/PSO/PSO.aimms"
python = "C:/path/to/pypsa-zn/.venv-pso/Scripts/python.exe"
```

Check configuration and dependencies:

```powershell
python pso_config.py
python pso_preflight.py
```

Follow the scripts’ corrective prompts for missing TOML, invalid interpreter, PSO project or `aimmspy`. `DEVNET_PSO_CASE` and `DEVNET_PSO_PYTHON` environment variables override the corresponding TOML entries. Never commit `pso.local.toml` or `.venv-pso/`. Install Plotly into the Python interpreter used for geographic plotting with `python -m pip install plotly`. For detailed licensing and setup see [README — PSO/AIMMS Environment Dependencies](./README.md#psoaimms-environment-dependencies).

## Code and data directory map

| File/directory | Function |
|---|---|
| `ercot7k/` | Immutable baseline PSO input tables (`texas7k.csv`, `texas7k_*.csv`) |
| `ercot7k_pso.py` | AIMMS/CPLEX baseline or derived optimization; writes `ercot7k-runs/` |
| `pso_config.py`, `pso_preflight.py` | Configuration, interpreter and license/project checks |
| `ercot7k-runs/` | Run-specific `results/`, logs, ranked node outputs |
| `ercot7k_node_screen.py` | Stream PSO prices, screen and rank nodes |
| `ercot7k_config/ercot7k_node_filters.csv` | Researcher-editable screening thresholds and ranking metric |
| `ercot7k_geo/texas7k_bus_coords.csv` | `enode,busnum,lat,lon,zone` reference |
| `geo-plots/ercot7k_node_map.py` | Standalone interactive Plotly HTML generator |
| `ercot7k_build.py` | Initialize/review config; interactive derived-case builder |
| `ercot7k_case.py` | Apply/validate case changes and write manifest |
| `ercot7k_config/ercot7k_dc.csv` | Datacenter node, MW, BYOG parameters |
| `ercot7k_config/ercot7k_stress.csv` | Grid stress lever/target/mode/value |
| `ercot7k-derived/` | Derived input tables and `pso_case_manifest.json` |
| `ercot7k_results.py` | Existing results inspection; comparison integration pending |
| `ercot7k_sweep.py` | Multi-case stress automation; menu integration pending |
| `devnet_menu.py` | Unified workflow dispatcher |

### Directory evolution

- **Fresh clone:** Scripts, `ercot7k/`, `ercot7k_geo/`, injector templates, TOML example; create local `.venv-pso/` and TOML.
- **Baseline solve:** `ercot7k-runs/<baseline>/results/results_*.csv` and logs. Validated run name: `ercot7k-run`.
- **Screening:** `ercot7k-runs/<run>/ercot7k_node_ranked.csv`.
- **Map:** `geo-plots/ercot7k_node_map.html`.
- **Builder `--init`:** `ercot7k_config/ercot7k_dc.csv` and `ercot7k_stress.csv` plus logs.
- **Derived build:** `ercot7k-derived/<case>/` with PSO input tables and `pso_case_manifest.json`.
- **Derived solve:** A separate `ercot7k-runs/<derived-run>/results/` directory.

Names depend on user selections. Generated run directories are not necessarily tracked by Git.

## Baseline optimization

```powershell
python ercot7k_pso.py
```

Or select **Run Baseline** in the PSO menu. Confirm the case is `ercot7k/texas7k.csv`. Preserve a named baseline result set. This is a **multi-cycle, multi-interval** optimization, not a single snapshot. One validated baseline reported **221 optimal solves**; this is an observed run count, not a universal constant.

## Node screening and ranking

```powershell
python ercot7k_node_screen.py --run ercot7k-run
python ercot7k_node_screen.py -h
```

Options include `--run`/`--results`, `--filters`, `--geo`, `--model`, `--out`, `--yes`. The interactive workflow displays filter path, parameter table and calculation basis; supports confirming/changing paths, **external** CSV editing and reloading, and canceling. `--yes` skips interaction.

### Screening parameters

Default: `ercot7k_config/ercot7k_node_filters.csv`.

| Parameter | Interpretation |
|---|---|
| `cycle`, `scenario` | PSO cycle/scenario, e.g. `RT`, `ScnRT` |
| `ranking_metric` | `max_spread`, `mean_spread`, `stress_hours` |
| `spread_threshold` | Absolute LMP separation threshold, USD/MWh |
| `min_stress_hours` | Minimum qualifying duration/count |
| `min_lmp`, `max_lmp` | Nodal price bounds, USD/MWh |
| `min_load_mw` | Reserved nodal load filter; source mapping pending |
| `min_voltage_kv` | Reserved voltage filter; source mapping pending |
| `top_n` | Maximum shortlist size |

Validated example: `RT/ScnRT`, `max_spread`, threshold `10` USD/MWh, `top_n=50`. These are researcher-editable parameters. Do not assume reserved filters are implemented until validated.

### Calculation basis

`results_PC_Nd.csv` supplies `cyc,scn,nd,int,LMP` (and `EnrgPrice,FlowPrice,LossPrice`); `results_ED_Ara.csv` supplies `cyc,scn,ara,int,BalancePrice`.

```text
signed_spread = nodal LMP - area BalancePrice
absolute_spread = abs(signed_spread)
max_spread = max(absolute_spread)
mean_spread = mean(absolute_spread)
stress_hours = qualifying interval count/duration above spread_threshold
```

**Interval caution:** An interval is not automatically an hour. Confirm model interval duration and screener diagnostics before interpreting `stress_hours` as elapsed hours. The validated screening reported 168 area intervals and warned to confirm hourly resolution.

**Scientific caution:** LMP separation is a **screening indicator**, not proof of congestion, binding transmission constraints or datacenter deliverability. For congestion attribution, inspect `FlowPrice` and `results_PN_Pth.csv` binding-path outputs.

Output: `ercot7k-runs/<run>/ercot7k_node_ranked.csv` with ranked metrics and geographic `lat`, `lon`, `zone` where mapped. Validated sample: 7,132 observed node identifiers and 50 ranked nodes; observed identifiers need not equal nominal bus count. Screening does not require another PSO solve.


### Node Screening Design Principles

The node-screening subsystem separates the computational assessment
of candidate nodes from the visualization and subsequent datacenter
scenario construction.

#### Design Objectives

- Screen thousands of nodes without repeatedly invoking PSO.
- Keep researcher-selected thresholds separate from calculated metrics.
- Support repeatable screening against preserved baseline results.
- Retain signed LMP separation for engineering interpretation.
- Rank nodes using configurable metrics.
- Preserve geographic coordinates for visualization.
- Allow reuse with other ISO/RTO network datasets.

#### Screening Input and Output Architecture

| File | Role | Ownership |
|---|---|---|
| `results_PC_Nd.csv` | Nodal LMP and price components | PSO-generated |
| `results_ED_Ara.csv` | Area reference prices | PSO-generated |
| `results_PN_Pth.csv` | Transmission path flows and constraints | PSO-generated |
| `ercot7k_node_filters.csv` | Screening criteria and ranking selector | Researcher-editable |
| `texas7k_bus_coords.csv` | Node coordinates and zone | Geographic reference |
| `ercot7k_node_ranked.csv` | Ranked candidate nodes and metrics | Screener-generated |

The filter CSV is the researcher-facing configuration interface.
The ranked CSV is the durable analytical artifact.

#### Screening and Ranking Metrics

For node n and interval t:

    spread(n,t) = LMP(n,t) - BalancePrice(t)

    abs_spread(n,t) = abs(spread(n,t))

Ranking options:

| Metric | Calculation | Engineering interpretation |
|---|---|---|
| `max_spread` | Maximum absolute spread | Largest observed nodal price separation |
| `mean_spread` | Mean absolute spread | Average magnitude of price separation |
| `stress_hours` | Count/duration exceeding threshold | Persistence of elevated price separation |

The signed spread should remain available for distinguishing
positive and negative price separation.

Positive separation may indicate relatively expensive incremental
grid supply at a node. Negative separation may indicate relatively
inexpensive supply or export constraints.

Neither sign independently establishes transmission congestion.

#### Filter Application

- Select PSO cycle and scenario.
- Join nodal LMP records with the corresponding area reference price.
- Calculate signed and absolute spreads.
- Accumulate node-level statistics over selected intervals.
- Apply configured price and stress-duration thresholds.
- Sort using the selected `ranking_metric`.
- Retain up to `top_n` qualifying nodes.
- Join geographic coordinates where available.
- Write the ranked CSV.

`min_load_mw` and `min_voltage_kv` are reserved filters.
They must not be treated as operational until their source
mappings and filtering behavior are implemented and validated.

#### Temporal Resolution

The `int` field identifies a PSO reporting interval.

The number of qualifying intervals is not necessarily the
number of elapsed hours.

For non-hourly data:

    stress_hours = qualifying_intervals * interval_duration_hours

Interval duration must be established from the model's
time configuration. Until verified, report qualifying intervals
without claiming equivalent elapsed hours.

#### Scientific Interpretation

The screening metric identifies candidate nodes for further study.

It does not independently establish:

- Binding transmission constraints.
- Incremental datacenter deliverability.
- Available interconnection capacity.
- Resource adequacy.
- Feasibility of a proposed datacenter load.

For deeper analysis, use:

- `results_PC_Nd.csv` — `FlowPrice`, `EnrgPrice`, `LossPrice`.
- `results_PN_Pth.csv` — flow, limits, binding status, shadow prices.
- Derived-case PSO optimization — actual network response to added load.

#### Extensibility

For PJM, MISO or other regional models, retain the screening
algorithm while replacing the input adapters:

- Nodal price file and node identifier mapping.
- Area/zonal reference price mapping.
- Cycle/scenario and time-interval interpretation.
- Geographic node coordinates.
- Optional load and voltage metadata.

Keep the normalized screening CSV interface independent
of the underlying solver's native result-file naming.


### PSO Result Schema Inspection

Before extending screening to a new PSO case or another ISO/RTO,
inspect the actual input/output CSV schemas rather than assuming
field names or interval conventions.

Run these read-only PowerShell commands from the repository root:

```powershell
# Replace with the selected baseline run directory.
$results = ".\ercot7k-runs\ercot7k-run\results"

"--- Nodal prices: results_PC_Nd.csv ---"
Get-Content "$results\results_PC_Nd.csv" -TotalCount 3

"--- Area prices: results_ED_Ara.csv ---"
Get-Content "$results\results_ED_Ara.csv" -TotalCount 3

"--- Transmission paths: results_PN_Pth.csv ---"
Get-Content "$results\results_PN_Pth.csv" -TotalCount 3

"--- Geographic coordinates ---"
Get-Content ".\ercot7k_geo\texas7k_bus_coords.csv" -TotalCount 3
```

#### Expected Source Fields

| File | Required fields | Purpose |
|---|---|---|
| `results_PC_Nd.csv` | `cyc,scn,nd,int,LMP` | Nodal price observations |
| `results_ED_Ara.csv` | `cyc,scn,ara,int,BalancePrice` | Area reference prices |
| `results_PN_Pth.csv` | `cyc,scn,pth,int,Mw,Min,Max,Binding,SP` | Transmission constraint analysis |
| `texas7k_bus_coords.csv` | `enode,busnum,lat,lon,zone` | Geographic node mapping |

PSO files may prefix the first header with `//`, such as `//cyc`.

The screening adapter must account for this convention.

#### Extension Checklist

- Confirm node identifiers match across results and geographic data.
- Confirm reference-price mapping for single-area or multi-area cases.
- Confirm cycle/scenario selection.
- Confirm interval duration and time-zone interpretation.
- Confirm units of LMP, power flow and shadow prices.
- Confirm whether nodal load and voltage metadata are available.
- Validate calculated metrics against selected raw result rows.

These checks establish the input contract before extending the
screening implementation to another grid model.

---

## Geospatial visualization

```powershell
python geo-plots/ercot7k_node_map.py
```

Example with explicit parameters:

```powershell
python geo-plots/ercot7k_node_map.py --input ercot7k-runs/ercot7k-run/ercot7k_node_ranked.csv --output geo-plots/ercot7k_node_map.html --metric max_spread
```

Open the generated HTML directly in Chrome. It is **self-contained**, with hover, pan and zoom; no web server, Folium, Leaflet, React/Vite or ZeroNode website integration. Default color metric: `max_spread`. Other supported generation-time metrics: `mean_spread`, `stress_hours`. An **in-browser** metric selector is pending. The validated Texas-focused view includes neighboring states; it is not a Texas-only outline. The plot is of **screened nodes, not a full grid-congestion heatmap**. Transmission line overlay is pending.


### Geospatial Design Architecture

The geospatial subsystem is intentionally separated from PSO
optimization and the live ZeroNode website.

#### Design Objectives

- Generate interactive regional maps from solved network results.
- Keep geographic visualization independent of optimization.
- Support pan, zoom, hover and metric-based marker coloring.
- Produce standalone HTML artifacts for local viewing.
- Avoid requiring a web server or GIS installation.
- Support future regional networks through reusable data interfaces.

#### Current Implementation — Python + Plotly

```text
ercot7k-runs/<run>/
    ercot7k_node_ranked.csv
             |
             v
geo-plots/ercot7k_node_map.py
             |
             v
geo-plots/ercot7k_node_map.html
             |
             v
Local browser — interactive map
```

The map generator reads ranked-node data directly from CSV.

It uses Plotly `Scattergeo` for geographic markers and includes
Plotly.js in the generated HTML.

No Folium, Leaflet, React, Vite, Node.js or local HTTP server
is required for this implementation.

#### Why Plotly?

Plotly supports:

- Geographic scatter plots.
- Numeric color scales.
- Interactive hover information.
- Geographic zoom and pan.
- Self-contained HTML generation.
- Multiple geographic data traces.

Folium/Leaflet would become relevant if the visualization later
requires detailed GIS layers, geographic tile maps, extensive
network overlays or satellite imagery.

The initial ERCOT7k requirements do not justify that complexity.

### Geospatial Directory Structure

#### Current Validated Structure

```text
pypsa-zn/
|
├── ercot7k_geo/
│   └── texas7k_bus_coords.csv
|
├── ercot7k-runs/
│   └── ercot7k-run/
│       └── ercot7k_node_ranked.csv
|
└── geo-plots/
    ├── ercot7k_node_map.py
    └── ercot7k_node_map.html
```

`ercot7k_geo/` contains geographic reference data.

`geo-plots/` contains visualization source code and generated
presentation artifacts.

#### Optional Future React/Vite Architecture

The following is a reference architecture derived from the
separate ZeroNode U.S. geospatial plotting project.

It is NOT required by the current ERCOT7k implementation.

```text
geo-plots/
├── README.md
├── package.json
├── src/
│   ├── App.jsx
│   └── embed.jsx
├── public/
│   └── ercot7k_node_ranked.json
├── dist/
└── vite.config.js
```

The React/Vite architecture should be introduced only when
additional visualization requirements justify it.

The existing Python generator remains the validated default.

### Standalone Map Sanity Test

Run from the repository root:

```powershell
python -c "import plotly.graph_objects as go; go.Figure(go.Scattergeo(lat=[31],lon=[-99],mode='markers')).write_html('geo-plots/plotly_test.html',include_plotlyjs=True)"
```

Open:

```text
geo-plots/plotly_test.html
```

Expected: A world map with one marker in Texas.

This test isolates Plotly geographic rendering from ERCOT7k
screening data, metric coloring and map configuration.

Then generate the actual ERCOT7k map:

```powershell
python geo-plots/ercot7k_node_map.py
```

Expected output:

```text
geo-plots/ercot7k_node_map.html
```

The current validated Texas-focused map uses Plotly geographic
scope and projection settings. It displays neighboring states
for geographic context.

The map represents ranked nodes, not a complete transmission
network or a comprehensive congestion heatmap.

### ZeroNode Choropleth Architecture Reference

The earlier ZeroNode U.S. geospatial plotting application
provides a useful architectural reference.

It is maintained separately from pypsa-zn.

#### Source Components

| File | Purpose |
|---|---|
| `src/App.jsx` | React/Plotly visualization logic, state overlays, tooltips and color scales |
| `src/embed.jsx` | Mounts the React application into a host HTML element |
| `package.json` | JavaScript dependencies and development/build commands |
| `vite.config.js` | Configures the standalone IIFE JavaScript bundle |
| `public/us_state_overlay_data.json` | U.S. state-level geographic overlay data |
| `dist/zeronode-map.iife.js` | Generated browser-consumable application bundle |
| `us-geospatial-plots.html` | Host-page integration wrapper |

#### Reusable Design Concepts

- Separate geographic data from rendering logic.
- Use Plotly geographic traces for choropleths and node markers.
- Keep hover and color-scale behavior data-driven.
- Validate matching lengths and identifiers across plotted datasets.
- Maintain one source of visualization logic.
- Isolate generated bundles from editable source code.

The ZeroNode implementation uses `src/App.jsx` as the
primary visualization source and `src/embed.jsx` as the
mounting entry point.

Its Vite build generates a browser-consumable IIFE bundle.

These techniques may be reused for future regional dashboards,
but the existing ZeroNode website code must remain independent
of pypsa-zn.

#### Choropleth Versus Ranked-Node Maps

| Visualization | Geographic unit | Typical metric |
|---|---|---|
| U.S. choropleth | State polygons | State-level demand, generation or prices |
| ERCOT7k node map | Electrical node coordinates | LMP spread and stress duration |
| Future network overlay | Transmission branches | Connectivity, loading or voltage |
| Future regional comparison | ISO/RTO geography | Aggregated regional metrics |

Choropleths and node maps serve different analytical purposes.

The ERCOT7k node map should not be represented as a
state-level choropleth or a full network congestion map.

### Scalability to Other Grid Regions

The long-term objective is a reusable geospatial visualization
interface for regional electricity-grid models.

#### Proposed Data Contract

```text
Regional network results
          |
          v
Normalized node metrics CSV
          |
          v
Node identifier + latitude/longitude
          |
          v
Reusable geographic renderer
          |
          v
Standalone regional HTML map
```

Recommended normalized fields:

| Field | Purpose |
|---|---|
| `node` | Unique electrical node identifier |
| `lat`, `lon` | Geographic coordinates |
| `zone` | Region or zone identifier |
| `max_spread` | Maximum absolute LMP separation |
| `mean_spread` | Mean absolute LMP separation |
| `stress_hours` | Qualifying stress duration |
| `rank` | Screening rank |

For PJM, MISO or another ISO/RTO, replace the data adapters
and geographic inputs while retaining the rendering concepts.

Future extensions may include:

- Regional map selection.
- In-browser metric switching.
- Transmission line overlays.
- Voltage-class filters.
- Node selection linked to scenario configuration.
- Multiple result layers and scenario comparisons.

#### Transmission Line Overlay — Proposed

```text
Network branch connectivity
          +
Bus coordinates
          +
Ranked nodes
          |
          v
Select connected branches
          |
          v
One-hop / two-hop network overlay
          |
          v
Interactive regional map
```

The initial implementation should display only branches
connected to screened nodes.

Transmission connectivity, branch endpoints and voltage
metadata must be verified from the regional network input files
before implementation.

This is a planned extension, not a validated capability.

---

## Derived datacenter and grid-stress cases

```powershell
python ercot7k_build.py --init
python ercot7k_build.py --show-config
python ercot7k_build.py
```

`--init` generates config CSVs and displays initialized settings. **Review/backup edits before rerunning `--init`, which may reset templates.** Without initialized configuration, the builder guides the user to initialize. `--show-config` displays active rows. A normal build prompts for parent case and layer.

### Datacenter configuration — `ercot7k_config/ercot7k_dc.csv`

| Field | Meaning |
|---|---|
| `dc_name` | Datacenter/experiment identifier |
| `node` | Electrical node identifier |
| `p_set_mw` | Datacenter load, MW |
| `byog_p_nom_mw` | BYOG nominal MW |
| `byog_max_mw` | BYOG maximum MW |
| `byog_mc` | BYOG marginal cost, USD/MWh |
| `load_shape` | Demand shape, e.g. `flat` |

Illustrative validated config: `DC1`, `N210144`, 1,000 MW load, 500 MW BYOG nominal/max, `byog_mc=65`, `flat`. This is **not** a recommended node or cost benchmark.

### Stress configuration — `ercot7k_config/ercot7k_stress.csv`

| Field | Meaning |
|---|---|
| `lever` | Grid stress type, e.g. `k_load` |
| `target` | Target selection, where applicable |
| `mode` | Modification method, e.g. `scale` |
| `value` | Applied value, e.g. `1.2` |

The builder delegates to `ercot7k_case.py`, validates and writes a new case and manifest under `ercot7k-derived/`. **Building does not execute PSO.** Derived layers are **write-once**; reusing parent and `dc_name` may collide with an existing directory even if other values change. Use unique names such as `DC_HEWITT` or `DC_WHITNEY` for separate experiments. To solve, choose **Run Derived Case** and select the case; the menu passes case selection without manual TOML editing.

---

## Experiment design and reproducibility

| Stage | Researcher input | Artifact |
|---|---|---|
| Baseline | PSO case and run name | Baseline results |
| Screening | Cycle, scenario, filters, ranking | Ranked CSV + saved filters |
| Geographic plot | Coordinates and metric | Standalone HTML |
| Datacenter | Node, load, BYOG MW/cost | Derived case + manifest |
| Stress | Lever, target, mode, value | Derived case + manifest |
| Optimization | Case/run selection | Separate solved results |
| Comparison | Matched baseline/derived cycles and intervals | Menu integration **pending** |

Preserve immutable baseline, distinct experiment names, filter settings, manifests and run artifacts. Compare matched cycles/scenarios/intervals. `ercot7k_sweep.py` exists but is not yet part of the validated interactive workflow.

---

## Sanity and regression tests

Run from repository root in PowerShell:

```powershell
git status -sb
git diff --check
python -m py_compile devnet_menu.py ercot7k_node_screen.py geo-plots/ercot7k_node_map.py
$env:DEVNET_PSO_CASE = "ercot7k/texas7k.csv"
python -c "import os, pso_config; pso_config.load_config(); print('Selected case:', os.environ.get('DEVNET_PSO_CASE'))"
Remove-Item Env:\DEVNET_PSO_CASE -ErrorAction SilentlyContinue
python ercot7k_case.py verify ercot7k
python ercot7k_build.py --help
python ercot7k_build.py --show-config
```

Expected case override: `Selected case: ercot7k/texas7k.csv`. Validated baseline check: `OK=6 SKIP=13 WARNING=0 ERROR=0` (counts may vary). On a fresh clone, `--show-config` may report missing configuration; run `--init`. `git diff --check` checks whitespace, **not** Python correctness. These tests do **not** run AIMMS/CPLEX. See [README sanity tests](./README.md#environmentcodebase-sanity-tests) and [troubleshooting](./README.md#psoaimms-troubleshooting).

---

## Known limitations and planned extensions

- Price separation is not a comprehensive congestion or deliverability assessment; validate against `FlowPrice` and binding paths.
- Confirm time interval duration before labeling counts as hours.
- Implement actual nodal-load and voltage-level screening filters.
- Add an in-browser ranking metric selector and optionally refine the Texas-only viewport.
- Add 1–2-hop transmission line overlays using verified branch connectivity and voltage data.
- Integrate baseline-versus-derived comparison and automated `ercot7k_sweep.py` workflow into the menu.
- Complete end-to-end regression and reproducible scenario provenance checks.

---

## License and attribution

ZeroNode code follows repository [LICENSE](./LICENSE), [NOTICE](./NOTICE) and [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md). The repository license does not grant rights to Polaris PSO, AIMMS, CPLEX, their licenses or proprietary documentation. See [README — License and Attribution](./README.md#license-and-attribution).
