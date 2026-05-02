# DevNet Stress Vectors — Reference Outputs

This directory contains **reference output artifacts** generated from DevNet stress runs.

These files are provided to:
- enable **deterministic replication** of plots
- support **review, validation, and publication workflows**
- avoid requiring users to re-run full stress experiments

---

## Contents

Typical files in this directory include:

- `devnet_plots.xlsx`  
  Consolidated workbook used by plotting scripts

- `DevNet Stress Report_*.html`  
  Snapshot of interactive stress report (`index.html`)

- `devnet_stress_tc.md`  
  Documented test cases used to generate reference outputs

- Derived artifacts:
  - `.csv` (metrics, LMP, loading)
  - `.png` (plots)
  - `.json` (optional summaries)

---

## Important note (licensing)

These files are:

- **Generated outputs**, not source code  
- **Not covered under the repository’s open-source license**  
- Provided for **reference and reproducibility only**

No SPDX headers are included in these files.

---

## Relationship to plotting scripts

The following scripts consume inputs from this directory:

- `devnet_load_plot.py`
- `devnet_lmp_plot.py`
- `devnet_line_plot.py`

These scripts:
- read from `devnet_plots.xlsx`
- do **not directly parse `stress_out/` outputs**

---

## Updating these artifacts

To regenerate or update:

1. Run:
```bash
   python devnet_stress.py
```

2. Extract relevant cases from:

```text
   ./<devnet>/stress_out/index.html
```

3. Update:

```text
   devnet_plots.xlsx
```

4. Re-run plot scripts

---

## Design intent

This separation ensures:

* reproducibility across environments
* stable inputs for plotting and reporting
* clean separation between:

  * **model code**
  * **experiment outputs**

---


