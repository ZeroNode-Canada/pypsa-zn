SPDX-License-Identifier: Apache-2.0
Copyright 2026 ZeroNode

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

See the License for the specific language governing permissions and
limitations under the License.

README.md

This document describes the PyPSA-ZN demonstration subsystem located under:

    ./demo/

The demonstration subsystem reuses the DevNet modeling engine implemented in:

    ../lib/devnet_stress_lib.py

and is licensed under the same Apache License, Version 2.0 as the parent repository.

------------------------------------------------------------------------------

# Table of Contents
- [Table of Contents](#table-of-contents)
- [PyPSA-ZN Demo Framework](#pypsa-zn-demo-framework)
  - [Overview](#overview)
- [Design Philosophy](#design-philosophy)
- [Demo Architecture](#demo-architecture)
- [Directory Structure](#directory-structure)
- [Relationship to DevNet](#relationship-to-devnet)
- [Runtime Workflow](#runtime-workflow)
- [Option 1 — Interactive Demo Landing Page](#option-1--interactive-demo-landing-page)
- [Option 2 — CLI Researcher Mode](#option-2--cli-researcher-mode)
- [Option 3 — Build Master CSVs](#option-3--build-master-csvs)
- [Option 4 — Generate Story Plots](#option-4--generate-story-plots)
- [Option 5 — Refresh Story Plots in Dashboard](#option-5--refresh-story-plots-in-dashboard)
- [Demo Presets](#demo-presets)
- [Runtime Artifacts](#runtime-artifacts)
- [Master CSV Workflow](#master-csv-workflow)
- [Story Plot Workflow](#story-plot-workflow)
- [HTML Templates](#html-templates)
- [Demo HTTP Server](#demo-http-server)
- [BYOG Demonstration Logic](#byog-demonstration-logic)
  - [Purpose of the Demonstration](#purpose-of-the-demonstration)
  - [Demonstration Hypothesis](#demonstration-hypothesis)
  - [BYOG Competes Narrative](#byog-competes-narrative)
  - [BYOG Complements Narrative](#byog-complements-narrative)
  - [Story Plot Philosophy](#story-plot-philosophy)
  - [Relationship to ZeroNode Storyboard](#relationship-to-zeronode-storyboard)
  - [Generic Demonstration Workflow](#generic-demonstration-workflow)
- [Troubleshooting](#troubleshooting)
  - [Missing preset](#missing-preset)
  - [Missing dashboard template](#missing-dashboard-template)
  - [Missing landing template](#missing-landing-template)
  - [Missing story plots](#missing-story-plots)
  - [Missing master CSVs](#missing-master-csvs)
  - [Browser cannot connect](#browser-cannot-connect)

---

# PyPSA-ZN Demo Framework

## Overview

The `pypsa-zn/demo/` subsystem provides a kiosk-ready demonstration environment built on top of the PyPSA-ZN DevNet modeling framework.

The demo environment serves two purposes:

* Present ZeroNode's Datacenter BYOG concepts to external audiences.
* Provide a lightweight researcher workflow for scenario execution, result collection, and story plot generation.

The demo framework is intentionally separated from the developer workflow implemented in:

```text
devnet_stress.py
```

while reusing the same modeling engine implemented in:

```text
lib/devnet_stress_lib.py
```

The result is a presentation-friendly front-end with a stable developer back-end.

---


# Design Philosophy

The demo framework is intentionally lightweight.

```text
devnet_stress.py
```

remains the researcher environment.

```text
pypsa_zn_demo.py
```

remains the presentation environment.

Both share:

```text
lib/devnet_stress_lib.py
```

ensuring a single modeling implementation and eliminating divergence between research and demonstration results.

---

# Demo Architecture

```text
pypsa_zn_demo.py
        |
        +-- Interactive Landing Page
        |
        +-- CLI Researcher Mode
        |
        +-- Master CSV Builder
        |
        +-- Story Plot Generator
        |
        +-- Dashboard Plot Refresher
        |
        +-- HTTP Demo Server
                |
                +-- pypsa_zn_demo_land.html
                |
                +-- pypsa_zn_demo.html
```

Model execution is delegated to:

```text
lib/devnet_stress_lib.py
```

which is shared with:

```text
devnet_stress.py
```

---

# Directory Structure

```text
demo/
│
├── demo_presets.json
│
├── pypsa_zn_demo.py
│
├── pypsa_zn_demo_land.html
│
├── pypsa_zn_demo.html
│
├── assets/
│   ├── demo_dashboard.html
│   ├── demo_landing.html
│   └── ZeroNodeTM-logo.png
│
├── demo_out/
│
├── plots/
│   ├── byog_competes.csv
│   ├── byog_competes_cost.png
│   ├── byog_competes_profit.png
│   ├── byog_complements.csv
│   ├── byog_complements_cost.png
│   └── byog_complements_lmp.png
│
└── plots - Copy/
    ├── byog_competes.csv
    └── byog_complements.csv
```

---

# Relationship to DevNet

The demo framework does not implement a separate modeling engine.

All power system simulation logic originates from:

```text
lib/devnet_stress_lib.py
```

The demo framework simply:

```text
Load Preset
        ↓
Build Runtime Arguments
        ↓
Call run_commit()
        ↓
Generate Dashboard
        ↓
Generate Story Data
```

Developer workflow:

```text
devnet_stress.py
```

Demo workflow:

```text
pypsa_zn_demo.py
```

Both ultimately execute:

```text
lib/devnet_stress_lib.py
```

---

# Runtime Workflow

Launch:

```cmd
C> python pypsa_zn_demo.py
```

Menu:

```text
Select Demo Mode:

  1) Interactive Demo Landing Page
  2) CLI Researcher / Preset Mode
  3) Build Master CSVs
  4) Generate Story Plots
  5) Refresh Story Plots in Dashboard
  0) Exit
```

---

# Option 1 — Interactive Demo Landing Page

Purpose:

```text
ESIG kiosk
Conference demonstrations
Executive presentations
```

Workflow:

```text
Start HTTP Server
        ↓
Generate Landing Page
        ↓
Open Browser
        ↓
Scenario Selection
        ↓
Execute Scenario
        ↓
Display Dashboard
```

Launches:

```text
http://localhost:8000/pypsa_zn_demo_land.html
```

The server remains active until:

```text
CTRL+C
```

---

# Option 2 — CLI Researcher Mode

Purpose:

```text
Developer workflow
Scenario testing
Model validation
```

Workflow:

```text
Select artifact handling
        ↓
Enumerate presets
        ↓
Execute selected preset
        ↓
Generate dashboard
        ↓
Append runtime CSV
```

Artifact modes:

```text
1) Accumulate demo_out artifacts
2) Purge demo_out and start fresh
```

---

# Option 3 — Build Master CSVs

Purpose:

Generate authoritative scenario datasets used for story plot generation.

Before execution:

```text
plots/byog_competes.csv
plots/byog_complements.csv
```

are deleted.

Then:

```text
MASTER_CSV_MODE = True
```

is enabled.

The interactive workflow is then used to selectively execute scenarios.

Each scenario updates:

```text
plots/byog_competes.csv
plots/byog_complements.csv
```

with the latest result.

These become the golden datasets used for plotting.

---

# Option 4 — Generate Story Plots

Purpose:

Generate presentation graphics from the master CSVs.

Inputs:

```text
plots/byog_competes.csv
plots/byog_complements.csv
```

Outputs:

```text
byog_competes_cost.png

byog_competes_profit.png

byog_complements_lmp.png

byog_complements_cost.png
```

Generated into:

```text
demo/plots/
```

---

# Option 5 — Refresh Story Plots in Dashboard

Purpose:

Refresh dashboard references without rerunning simulations.

Updates:

```text
pypsa_zn_demo.html
```

using:

```text
assets/demo_dashboard.html
```

as source.

Used after:

```text
Generate Story Plots
```

to update dashboard visualizations.

---

# Demo Presets

Presets are defined in:

```text
demo_presets.json
```

Families:

```text
byog_competes_case*
```

Represents:

```text
BYOG competes with grid generation
ρ → ∞
```

and:

```text
byog_complements_case*
```

Represents:

```text
BYOG complements grid supply
ρ ≈ 1
```

Each preset provides:

```text
k_load
byog_mc
dc_p_nom
dc_p_set
optional mc_bus overrides
```

---

# Runtime Artifacts

Generated dashboard:

```text
pypsa_zn_demo.html
```

Generated landing page:

```text
pypsa_zn_demo_land.html
```

Runtime CSVs:

```text
demo_out/byog_competes.csv

demo_out/byog_complements.csv
```

These are regenerated frequently and are not considered authoritative.

---

# Master CSV Workflow

Authoritative CSVs:

```text
plots/byog_competes.csv

plots/byog_complements.csv
```

Columns:

```text
scenario
case
k_load
byog_mc
dc_p_nom
objective
dc_dispatch_mw
lmp_spread
```

Used exclusively for:

```text
Story plots
Conference material
Presentation graphics
```

---

# Story Plot Workflow

Build:

```text
Option 3
```

to create:

```text
Master CSVs
```

Then:

```text
Option 4
```

to create:

```text
Story plots
```

Then:

```text
Option 5
```

to update:

```text
Dashboard references
```

Workflow:

```text
Master CSVs
        ↓
Story Plots
        ↓
Dashboard Refresh
```

---

# HTML Templates

Landing page source:

```text
assets/demo_landing.html
```

Generated output:

```text
pypsa_zn_demo_land.html
```

Dashboard source:

```text
assets/demo_dashboard.html
```

Generated output:

```text
pypsa_zn_demo.html
```

Templates are regenerated automatically.

Manual edits should generally be applied to:

```text
assets/
```

not generated files.

---

# Demo HTTP Server

Default:

```text
localhost:8000
```

Serves:

```text
pypsa_zn_demo_land.html

pypsa_zn_demo.html

devnetDC-sld/
```

Additional endpoints:

```text
/heartbeat

/devnet_base_params

/run?preset=<preset>
```

---


# BYOG Demonstration Logic

## Purpose of the Demonstration

The objective of the ZeroNode demonstration is not to prove annual system outcomes.

The DevNet scenarios represent:

```text
Representative Market States
```

rather than:

```text
Annual Production Simulations
```

Each scenario should be interpreted as a single representative market interval occurring during periods of scarcity, congestion, or elevated locational marginal prices.

Examples include:

```text
10 hours/year
20 hours/year
50 hours/year
```

rather than all 8,760 hours of annual operation.

This distinction is important because the demonstration is intended to explore how datacenter-owned generation resources may influence grid outcomes during a relatively small number of critical system conditions.

---

## Demonstration Hypothesis

The core hypothesis behind the ZeroNode BYOG framework is:

```text
Datacenter BYOG does not need to operate
8,760 hours/year.
```

Instead:

```text
Datacenter BYOG may only need to operate
during a relatively small number of
scarcity hours, congestion hours, or
high-LMP hours
```

to materially alter market outcomes.

The demonstration explores whether participation during these limited periods can:

* Restore system feasibility
* Reduce congestion
* Reduce locational price separation
* Improve transmission utilization
* Create economic value for datacenter operators

---

## BYOG Competes Narrative

The BYOG Competes scenario family explores conditions where:

```text
Grid Generation
        versus
Datacenter BYOG
```

compete to serve load.

Primary questions:

```text
Can BYOG restore feasibility?

Can BYOG create economic value?
```

Primary story plots:

```text
BYOG Competes :: System Cost

BYOG Competes :: Profit Proxy
```

Interpretation:

```text
Infeasible
        ↓
Feasible
        ↓
Economically Viable
```

---

## BYOG Complements Narrative

The BYOG Complements scenario family explores conditions where:

```text
Grid Generation
        plus
Datacenter BYOG
```

work together to serve demand.

Primary questions:

```text
Can BYOG reduce congestion?

Can BYOG reduce LMP spread?
```

Primary story plots:

```text
BYOG Complements :: LMP Spread

BYOG Complements :: System Cost
```

Interpretation:

```text
Congested
        ↓
Less Congested
        ↓
Improved Market Efficiency
```

---

## Story Plot Philosophy

The demonstration intentionally focuses on four presentation plots:

```text
BYOG Competes
    System Cost
    Profit Proxy

BYOG Complements
    LMP Spread
    System Cost
```

These plots directly align with the two scenario families and provide a concise explanation of:

```text
Scarcity Mitigation

Congestion Mitigation
```

without requiring visitors to understand the underlying optimization model.

---

## Relationship to ZeroNode Storyboard

The demonstration is the final stage of the ZeroNode storyboard:

```text
Grid Events
        ↓
Datacenter Growth
        ↓
National Implications
        ↓
DevNet Architecture
        ↓
ZeroNode Hypothesis
        ↓
Live Demonstration
```

The storyboard establishes:

```text
Problem
        ↓
Scale
        ↓
Framework
        ↓
Hypothesis
```

The live demonstration provides:

```text
Evidence
```

supporting that hypothesis.

## Generic Demonstration Workflow

The demonstration framework is designed to support a wide range of presentation environments including:

```text
Conference kiosks

Executive briefings

Customer demonstrations

Workshops

Training sessions
```

The recommended presentation flow is:

```text
Problem
        ↓
Scale
        ↓
Framework
        ↓
Hypothesis
        ↓
Evidence
```

The demonstration framework itself provides only:

```text
Scenario Execution

Dashboard Generation

Story Plot Generation

Interactive Exploration
```

Presentation-specific storyboards, kiosk flows, conference assets, and website integrations are intentionally maintained outside the PyPSA-ZN repository.

This separation ensures:

```text
Reusable open-source code

Conference-independent operation

Clean research workflows

Portable demonstrations
```

The demonstration engine therefore remains focused on:

```text
Model Execution
        ↓
Scenario Evaluation
        ↓
Result Visualization
```

while presentation workflows remain external consumers of the generated artifacts.

---

# Troubleshooting

## Missing preset

```text
ERROR: Unknown preset
```

Verify:

```text
demo_presets.json
```

contains the preset name.

---

## Missing dashboard template

Verify:

```text
assets/demo_dashboard.html
```

exists.

---

## Missing landing template

Verify:

```text
assets/demo_landing.html
```

exists.

---

## Missing story plots

Run:

```text
Option 4
```

before:

```text
Option 5
```

---

## Missing master CSVs

Run:

```text
Option 3
```

before:

```text
Option 4
```

---

## Browser cannot connect

Verify:

```text
Option 1
```

is running and:

```text
localhost:8000
```

is reachable.

