# Devnet Stress Test Vectors
DevNet Stress Test Vector: Structure, design and implementation

---

# Table of Contents
- [Devnet Stress Test Vectors](#devnet-stress-test-vectors)
- [Table of Contents](#table-of-contents)
- [Devnet Stress Test Vectors](#devnet-stress-test-vectors-1)
  - [DevNet Stress Vectors::Configurable Args \& Menu Values](#devnet-stress-vectorsconfigurable-args--menu-values)
  - [DevNet number of buses](#devnet-number-of-buses)
  - [System-Wide Adequacy Check](#system-wide-adequacy-check)
  - [Per-Bus Balance (Local Surplus / Deficit)](#per-bus-balance-local-surplus--deficit)
  - [Generator Marginal Cost](#generator-marginal-cost)
  - [DevNet Stress Test Cases](#devnet-stress-test-cases)
    - [DevNet Stress Test::Local-Supply Dominated::Test Case 1](#devnet-stress-testlocal-supply-dominatedtest-case-1)
      - [Local-Supply Dominated::Test Case 1 A: Conditions](#local-supply-dominatedtest-case-1-a-conditions)
      - [Local-Supply Dominated::Test Case 1 A: Expected Results](#local-supply-dominatedtest-case-1-a-expected-results)
      - [Local-Supply Dominated::Test Case 1 A: Results](#local-supply-dominatedtest-case-1-a-results)
      - [Local-Supply Dominated::Test Case 1 B: Conditions](#local-supply-dominatedtest-case-1-b-conditions)
      - [Local-Supply Dominated::Test Case 1 B: Expected Results](#local-supply-dominatedtest-case-1-b-expected-results)
      - [Local-Supply Dominated::Test Case 1 B: Results](#local-supply-dominatedtest-case-1-b-results)
    - [DevNet Stress Test::Local-Supply Dominated::Test Case 1 C](#devnet-stress-testlocal-supply-dominatedtest-case-1-c)
      - [Local-Supply Dominated::Test Case 1 C: Conditions](#local-supply-dominatedtest-case-1-c-conditions)
      - [Local-Supply Dominated::Test Case 1 C: Expected Results](#local-supply-dominatedtest-case-1-c-expected-results)
        - [DevNet Stress Test::Local-Supply Dominated:Test Case 1 C: Results](#devnet-stress-testlocal-supply-dominatedtest-case-1-c-results)
    - [DevNet Stress Test::Topology-Constrained::Test Case 2](#devnet-stress-testtopology-constrainedtest-case-2)
      - [Topology-Constrained::Test Case 2 A: Conditions](#topology-constrainedtest-case-2-a-conditions)
      - [Topology-Constrained::Test Case 2 A: Expected Results](#topology-constrainedtest-case-2-a-expected-results)
      - [Topology-Constrained::Test Case 2 A: Results](#topology-constrainedtest-case-2-a-results)
      - [Topology-Constrained::Test Case 2 B: Conditions](#topology-constrainedtest-case-2-b-conditions)
      - [Topology-Constrained::Test Case 2 B: Expected Results](#topology-constrainedtest-case-2-b-expected-results)
      - [Topology-Constrained::Test Case 2 B: Results](#topology-constrainedtest-case-2-b-results)
        - [ASR-DASH — Commit `c3` (single): Run Configuration](#asr-dash--commit-c3-single-run-configuration)
        - [Explanation: Near-Binding Count (`near_bind_ct`) = 6](#explanation-near-binding-count-near_bind_ct--6)
    - [DevNet Stress Test::Transmission Line capacity deration::Test Case 2 C](#devnet-stress-testtransmission-line-capacity-derationtest-case-2-c)
      - [Topology-Constrained::Test Case 2 C: Conditions](#topology-constrainedtest-case-2-c-conditions)
      - [Topology-Constrained::Test Case 2 C: Expected Results](#topology-constrainedtest-case-2-c-expected-results)
        - [DevNet Stress Test::Transmission Line capacity deration:Test Case 2 C: Results](#devnet-stress-testtransmission-line-capacity-derationtest-case-2-c-results)
    - [DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 3](#devnet-stress-testlmp-spread-lmp_spreadtest-case-3)
      - [LMP Spread (`lmp_spread`)::Test Case 3 A: Conditions](#lmp-spread-lmp_spreadtest-case-3-a-conditions)
      - [LMP Spread (`lmp_spread`)::Test Case 3 A: Expected Results](#lmp-spread-lmp_spreadtest-case-3-a-expected-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 A: Results](#lmp-spread-lmp_spreadtest-case-3-a-results)
        - [ASR-DASH — Commit `c4` (single): Run Configuration](#asr-dash--commit-c4-single-run-configuration)
        - [DC OPF power balance equation evaluation](#dc-opf-power-balance-equation-evaluation)
      - [LMP Spread (`lmp_spread`)::Test Case 3 B: Conditions](#lmp-spread-lmp_spreadtest-case-3-b-conditions)
      - [LMP Spread (`lmp_spread`)::Test Case 3 B: Expected Results](#lmp-spread-lmp_spreadtest-case-3-b-expected-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 B: Results](#lmp-spread-lmp_spreadtest-case-3-b-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 C: Conditions](#lmp-spread-lmp_spreadtest-case-3-c-conditions)
      - [LMP Spread (`lmp_spread`)::Test Case 3 C: Expected Results](#lmp-spread-lmp_spreadtest-case-3-c-expected-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 C: Results](#lmp-spread-lmp_spreadtest-case-3-c-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 D: Conditions](#lmp-spread-lmp_spreadtest-case-3-d-conditions)
      - [LMP Spread (`lmp_spread`)::Test Case 3 D: Expected Results](#lmp-spread-lmp_spreadtest-case-3-d-expected-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 D: Results](#lmp-spread-lmp_spreadtest-case-3-d-results)
      - [LMP Spread (`lmp_spread`)::Test Case 3 E: Conditions](#lmp-spread-lmp_spreadtest-case-3-e-conditions)
      - [LMP Spread (`lmp_spread`)::Test Case 3 E: Expected Results](#lmp-spread-lmp_spreadtest-case-3-e-expected-results)
        - [Explantion: LMP\_Spread trigger with Scarcity pricing](#explantion-lmp_spread-trigger-with-scarcity-pricing)
      - [LMP Spread (`lmp_spread`)::Test Case 3 E: Results](#lmp-spread-lmp_spreadtest-case-3-e-results)
        - [ASR-DASH — Commit `c8` (single): Run Configuration](#asr-dash--commit-c8-single-run-configuration)
        - [Explanation: Operating Cost with LMP Spread](#explanation-operating-cost-with-lmp-spread)
        - [DC OPF power balance equation evaluation \[TBC\]](#dc-opf-power-balance-equation-evaluation-tbc)
    - [DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Plan](#devnet-stress-testlmp-spread-lmp_spreadtest-plan)
      - [DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 4](#devnet-stress-testlmp-spread-lmp_spreadtest-case-4)
        - [DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 4: Results](#devnet-stress-testlmp-spread-lmp_spreadtest-case-4-results)
- [Reference](#reference)


---

# Devnet Stress Test Vectors
DevNet Stress Test Vector: Structure, design and implementation

## DevNet Stress Vectors::Configurable Args & Menu Values

| arg       | menu values |
|-----------|-------------|
| **scenario** | `baseline` ; `single` ; `sweep_line` |
| **mc_mode** | `set` ; `add` |
| **k_load** | `{}` |
|  | `{"WECC_NW": 1.2}` |
|  | `{"WECC_NW": 1.5}` |
|  | `{"WECC_NW": 1.2, "WECC_SW": 1.2, "SPP_MISO": 1.2, "PJM_NE": 1.2, "SERC_SE": 1.2, "ERCOT": 1.2}` |
|  | `__CUSTOM__` |
| **k_line** | `{}` |
|  | `{"L_WECC_NW_WECC_SW": 0.8}` |
|  | `{"L_WECC_NW_WECC_SW": 0.6}` |
|  | `{"L_WECC_NW_WECC_SW": 0.5}` |
|  | `__CUSTOM__` |
| **mc_bus** | `{}` ; `{"WECC_NW": 70}` ; `{"WECC_NW": 100}` |
| **dc_site** | `{"site_name": "DC1", "grid_bus": "WECC_NW", "p_dc_mw": 2000.0, "byog_frac": 0.0, "byog_mc": 80.0}` |
|  | `{"site_name": "DC1", "grid_bus": "WECC_NW", "p_dc_mw": 2000.0, "byog_frac": 0.5, "byog_mc": 80.0}` |
| **line** | `L_WECC_NW_WECC_SW` ; `L_WECC_SW_SPP_MISO` ; `L_SPP_MISO_ERCOT` ; `L_SPP_MISO_PJM_NE` ; `L_PJM_NE_SERC_SE` ; `L_SERC_SE_ERCOT` |
| **kmin** | `1.0` ; `0.9` ; `0.8` |
| **kmax** | `0.5` ; `0.4` ; `0.3` ; `0.2` |
| **kstep** | `-0.1` ; `-0.05` ; `-0.02` |

---

## DevNet number of buses
**ASR- TODO>>DONE:** Echo[Console + index.html] number of buses  
$Buses_N = 6$

---

## System-Wide Adequacy Check

- **Σ p_nom (generation)** = **48,000.0 MW**  
- **Σ p_set (load)** = **30,000.0 MW**  
- **Adequate?** = **YES**

---

## Per-Bus Balance (Local Surplus / Deficit)

**Definition**

$
\text{surplus} = \sum p_{nom}(\text{gen@bus}) - \sum p_{set}(\text{load@bus})
$

| Bus        | Gen (MW) | Load (MW) | Surplus (MW) | Status |
|------------|----------|-----------|--------------|--------|
| WECC_NW    | 8000.0 | 5000.0 | 3000.0 | EXPORT |
| WECC_SW    | 8000.0 | 5000.0 | 3000.0 | EXPORT |
| SPP_MISO   | 8000.0 | 5000.0 | 3000.0 | EXPORT |
| PJM_NE     | 8000.0 | 5000.0 | 3000.0 | EXPORT |
| SERC_SE    | 8000.0 | 5000.0 | 3000.0 | EXPORT |
| ERCOT      | 8000.0 | 5000.0 | 3000.0 | EXPORT |

---

## Generator Marginal Cost
**ASR- TODO>>DONE:** Echo[Console + index.html] marginal generator cost, line s_nom  
$c_g = marginal cost (USD/MWh) = 50.00$  
$line_{snom} = 5,000\text{ MW}$  

---

## DevNet Stress Test Cases
**Refer:**  
- [PyPSA_dev.md::PyPSA "USA-lite" network: Datacenter BYOG Modelling- Stress & Asymptote find](../../../EnergySystemAnalysis-%20PyPSA/PyPSA_dev.md)
- [DevNet Stress Report_4.html](./DevNet%20Stress%20Report_4.html)

### DevNet Stress Test::Local-Supply Dominated::Test Case 1
**Local-Supply Dominated Regime:**
- High system load (e.g. all buses ×1.5)
- No line derating
- Each bus serves load locally
- Minimal inter-bus flows

Result:
- `max_loading_pu` **drops** (e.g. ~0.25)
- Grid becomes *structurally irrelevant*

**Per-bus load multiplier preset (k_load):**  
$Bus_{Load} >= Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Bus_{Load} = 5000.0 MW$  
$Bus_{LoadStressFactor} =  Bus_{Load}/Bus_{GenCap} = 1.6$

#### Local-Supply Dominated::Test Case 1 A: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} =  Bus_{Load}/Bus_{GenCap} = 1.6$
$Bus_{Load} = 8000.0 MW$  
$Total System Load = Buses_N * Bus_{Load} = 6 * 8000 = 48,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

#### Local-Supply Dominated::Test Case 1 A: Expected Results
$Operating Cost = \{Total System Load * c_g\} = \{Buses_N * Bus_{Load} * c_g\}$  
$= \{6 * 8000 * 50\} = USD\text{ 2,400,000}$  

#### Local-Supply Dominated::Test Case 1 A: Results

**Output Path:** `./stress_out/Commit C1`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c1     | single   | 2.400e+06       | 0.000      | 0.000             | 0                        | 

---

#### Local-Supply Dominated::Test Case 1 B: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} >  Bus_{Load}/Bus_{GenCap} = 2.0$
$Bus_{Load} = 10,000.0 MW$  
$Total System Load = Buses_N * Bus_{Load} = 6 * 10000 = 60,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

#### Local-Supply Dominated::Test Case 1 B: Expected Results
$Total System Load > Total Generation Capacity$  
$= 60,000\text{ MW} > 48,000\text{ MW}$  
**Infeasible Objective...**  
$Operating Cost = \{Total System Load * c_g\} = \{Buses_N * Bus_{Load} * c_g\}$  
$= \{6 * 10000 * 50\} = USD\text{ 2,400,000}$  

#### Local-Supply Dominated::Test Case 1 B: Results

**Output Path:** `./stress_out/Commit C4`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c4     | single   | nan       | nan      | nan             | 0                        | 

**ASR- TODO>>DONE:** Check/Fix:  
The Commit C4 gets overwritten i.e. when a commit is nan, it is overwritten.  

---

### DevNet Stress Test::Local-Supply Dominated::Test Case 1 C
Refer:  
- [DevNet Stress Report_5.html](./DevNet%20Stress%20Report_5.html)  
- Commit ID: [11,... 16]

**Objective: Scale System load from default 1.0 > 2.0 (infeasible objective) and observe system operational costs- objective function**
**Per-bus load multiplier preset (k_load):**  
$Bus_{Load} >= Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Bus_{Load} = 5000.0 MW$  
$Bus_{LoadStressFactor} =  Bus_{Load}/Bus_{GenCap} = 1.6$

#### Local-Supply Dominated::Test Case 1 C: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} =  Bus_{Load}/Bus_{GenCap} =$ {  
  1.0  
  1.2  
  1.4  
  1.6  
  1.8  
  2.0  
}  
$Bus_{Load} =$ {  
  1.0 * 5000 = 5000.0 MW  
  1.2 * 5000 = 6000.0 MW  
  1.4 * 5000 = 7000.0 MW  
  1.6 * 5000 = 8000.0 MW  
  1.8 * 5000 = 9500.0 MW  
  2.0 * 5000 = 10000.0 MW  
}    
$Total System Load = Buses_N * Bus_{Load} =$ {  
  6 * 5000 = 30000.0 MW  
  6 * 6000 = 36000.0 MW  
  6 * 7000 = 42000.0 MW  
  6 * 8000 = 48000.0 MW  
  6 * 9000 = 54000.0 MW   **Infeasible Objective...**  
  6 * 10000 = 60000.0 MW   **Infeasible Objective...**  
}  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

#### Local-Supply Dominated::Test Case 1 C: Expected Results
$Operating Cost = \{Total System Load * c_g\}\equiv$ {  
  30000 * 50 = 1,500,000 $  
  36000 * 50 = 1,800,000 $  
  42000 * 50 = 2,100,000 $  
  48000 * 50 = 2,400,000 $  
  54000 * 50 = 2,700,000 $  
  60000 * 50 = 3,000,000 $  
}  

##### DevNet Stress Test::Local-Supply Dominated:Test Case 1 C: Results
**Refer:** [devnet_plots.xlsx:DevNet_load<>SystemCost](devnet_plots.xlsx)  

---

### DevNet Stress Test::Topology-Constrained::Test Case 2
**Topology-Constrained Regime:**
- Same high load
- Strong line derating (e.g. all lines ×0.3 or ×0.1)

Result:
- Even small balancing flows saturate reduced capacities
- `max_loading_pu → 1.0`

Interpretation:
> Line saturation here reflects **topological choking**, not increased demand.

#### Topology-Constrained::Test Case 2 A: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} =  Bus_{Load}/Bus_{GenCap} = 1.6$
$Bus_{Load} = 8000.0 MW$  
$Total System Load = Buses_N * Bus_{Load} = 6 * 8000 = 48,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.1, "L_WECC_SW_SPP_MISO": 0.1, "L_SPP_MISO_ERCOT": 0.1,  
    "L_SPP_MISO_PJM_NE": 0.1, "L_PJM_NE_SERC_SE": 0.1, "L_SERC_SE_ERCOT": 0.1  
        }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.1 * 5000 = 500\text{ MW}$  

#### Topology-Constrained::Test Case 2 A: Expected Results
$Operating Cost = \{Total System Load * c_g\} = \{Buses_N * Bus_{Load} * c_g\}$  
$= \{6 * 8000 * 50\} = USD\text{ 2,400,000}$  

#### Topology-Constrained::Test Case 2 A: Results

**Output Path:** `./stress_out/Commit C2`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c2     | single   | 2.400e+06       | 0.000      | 0.000             | 0                        | 0                   |

---

#### Topology-Constrained::Test Case 2 B: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} = Bus_{Load}/Bus_{GenCap} = 1.0\text{ default}$  
$Bus_{Load} = 5000.0 MW$  
$Total System Load = Buses_N * Bus_{Load} = 6 * 5000 = 30,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.1, "L_WECC_SW_SPP_MISO": 0.1, "L_SPP_MISO_ERCOT": 0.1,  
    "L_SPP_MISO_PJM_NE": 0.1, "L_PJM_NE_SERC_SE": 0.1, "L_SERC_SE_ERCOT": 0.1  
        }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.1 * 5000 = 500\text{ MW}$  

#### Topology-Constrained::Test Case 2 B: Expected Results
$Operating Cost = \{Total System Load * c_g\} = \{Buses_N * Bus_{Load} * c_g\}$  
$= \{6 * 5000 * 50\} = USD\text{ 1,500,000}$  

#### Topology-Constrained::Test Case 2 B: Results

**Output Path:** `./stress_out/Commit C3`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c3     | single   | 1.500e+06       | 0.000      | 0.000             | 6                        | 

---

##### ASR-DASH — Commit `c3` (single): Run Configuration

| Parameter | Value                                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| scenario  | single                                                                                                                                                      |
| mc_mode   | set                                                                                                                                                         |
| line      | -                                                                                                                                                           |
| k_load    | `{}`                                                                                                                                                        |
| k_line    | `{"L_WECC_NW_WECC_SW": 0.1, "L_WECC_SW_SPP_MISO": 0.1, "L_SPP_MISO_ERCOT": 0.1, "L_SPP_MISO_PJM_NE": 0.1, "L_PJM_NE_SERC_SE": 0.1, "L_SERC_SE_ERCOT": 0.1}` |
| mc_bus    | `{}`                                                                                                                                                        |
| dc_site   | N                                                                                                                                                           |

**Results Summary:**

| Metric                                | Value                     |
| ------------------------------------- | ------------------------- |
| Objective (USD)                       | 1.500e+06                 |
| LMP Spread (USD/MWh)                  | 0.000                     |
| Max LMP                               | 50.000 @ WECC_NW          |
| Max Line Loading (p.u.)               | 1.000 @ L_WECC_NW_WECC_SW |
| Near-binding Constraints (≥0.95 p.u.) | 6                         |

**Most Stressed Lines:**

| Line               | Loading (p.u.) |
| ------------------ | -------------- |
| L_WECC_NW_WECC_SW  | 1.00           |
| L_WECC_SW_SPP_MISO | 1.00           |
| L_SPP_MISO_ERCOT   | 1.00           |

---

**ASR- TODO>>DONE:** Explain the Near-Binding Count (`near_bind_ct`) = 6  
##### Explanation: Near-Binding Count (`near_bind_ct`) = 6  
Given:  
k_line= {  
    "L_WECC_NW_WECC_SW": 0.1, "L_WECC_SW_SPP_MISO": 0.1, "L_WECC_SW_SPP_MISO": 0.1,  
    "L_SPP_MISO_PJM_NE": 0.1, "L_PJM_NE_SERC_SE": 0.1, "L_SERC_SE_ERCOT": 0.1  
        }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.1 * 5000 = 500\text{ MW}$  

$Lines_{effective}$ [  
    L_WECC_NW_WECC_SW, L_WECC_SW_SPP_MISO, L_WECC_SW_SPP_MISO, 
    L_SPP_MISO_PJM_NE, L_PJM_NE_SERC_SE, L_SERC_SE_ERCOT
    ] 

**Key Points:**
* `near_bind_ct` **is not** the count of lines with *small effective capacity* relative to load.
* `near_bind_ct` counts **lines whose actual loading ≥ 0.95 p.u.** *in the solved DC OPF result*.
* ✅ **After** the DC OPF solves each of the **6 lines** ends up with:
  * $\frac{|F_{\text{line}}|}{s_{\text{nom, effective}}} \ge 0.95$
* ✅ Therefore `near_bind_ct = 6`
* Near-binding lines are those whose **post-solution loading ≥ 0.95 p.u.**, not those merely configured with low `k_line`.

---

### DevNet Stress Test::Transmission Line capacity deration::Test Case 2 C
Refer:  
- [DevNet Stress Report_5.html](./DevNet%20Stress%20Report_5.html)  
- Commit ID: [17,... 22]

**Objective: Derate transmission line capacities incrementally from default 1.0 > 0.1 and observe effect on near binding constraint count (near_bind_ct), max_loading_pu, LMP Spread and system operational costs- objective function**

#### Topology-Constrained::Test Case 2 C: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  
$Bus_{LoadStressFactor} = Bus_{Load}/Bus_{GenCap} = 1.0\text{ default}$  
$Bus_{Load} = 5000.0 MW$  
$Total System Load = Buses_N * Bus_{Load} = 6 * 5000 = 30,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {  
    "L_WECC_NW_WECC_SW": 1.0, "L_WECC_SW_SPP_MISO": 1.0, "L_SPP_MISO_ERCOT": 1.0,  
    "L_SPP_MISO_PJM_NE": 1.0, "L_PJM_NE_SERC_SE": 1.0, "L_SERC_SE_ERCOT": 1.0  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 1.0 * 5000 = 5000\text{ MW}$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.8, "L_WECC_SW_SPP_MISO": 0.8, "L_SPP_MISO_ERCOT": 0.8,  
    "L_SPP_MISO_PJM_NE": 0.8, "L_PJM_NE_SERC_SE": 0.8, "L_SERC_SE_ERCOT": 0.8  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.8 * 5000 = 4000\text{ MW}$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.6, "L_WECC_SW_SPP_MISO": 0.6, "L_SPP_MISO_ERCOT": 0.6,  
    "L_SPP_MISO_PJM_NE": 0.6, "L_PJM_NE_SERC_SE": 0.6, "L_SERC_SE_ERCOT": 0.6  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.6 * 5000 = 3000\text{ MW}$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.4, "L_WECC_SW_SPP_MISO": 0.4, "L_SPP_MISO_ERCOT": 0.4,  
    "L_SPP_MISO_PJM_NE": 0.4, "L_PJM_NE_SERC_SE": 0.4, "L_SERC_SE_ERCOT": 0.4  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.4 * 5000 = 2000\text{ MW}$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.2, "L_WECC_SW_SPP_MISO": 0.2, "L_SPP_MISO_ERCOT": 0.2,  
    "L_SPP_MISO_PJM_NE": 0.2, "L_PJM_NE_SERC_SE": 0.2, "L_SERC_SE_ERCOT": 0.2  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.2 * 5000 = 1000\text{ MW}$  

k_line= {  
    "L_WECC_NW_WECC_SW": 0.1, "L_WECC_SW_SPP_MISO": 0.1, "L_SPP_MISO_ERCOT": 0.1,  
    "L_SPP_MISO_PJM_NE": 0.1, "L_PJM_NE_SERC_SE": 0.1, "L_SERC_SE_ERCOT": 0.1  
     }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.1 * 5000 = 500\text{ MW}$  

#### Topology-Constrained::Test Case 2 C: Expected Results
$Operating Cost = \{Total System Load * c_g\} = \{Buses_N * Bus_{Load} * c_g\}$  
$= \{6 * 5000 * 50\} = USD\text{ 1,500,000}$  

##### DevNet Stress Test::Transmission Line capacity deration:Test Case 2 C: Results
**Refer:** [devnet_plots.xlsx:DevNet_line<>near_bind_ct](devnet_plots.xlsx)  

---

### DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 3
*Definition:**
For buses \( i \):

$
\text{LMP}_i = \lambda_i
$

$
\text{lmp\_spread} = \max_i(\lambda_i) - \min_i(\lambda_i)
$

**Congestion ≠ LMP Separation:**
For LMPs to separate, **both** must occur:
- a bus **cannot meet its load locally**, and
- imports to that bus are **constrained**

#### LMP Spread (`lmp_spread`)::Test Case 3 A: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  

$WECC_NW_{LoadStressFactor} = WECC_NW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_NW_{Load} = 5000.0\text{ MW}$  

$WECC_SW_{LoadStressFactor} = WECC_SW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_SW_{Load} = 5000.0\text{ MW}$  

$SPP_MISO_{LoadStressFactor} = SPP_MISO_{Load}/Bus_{GenCap} = 1.0$  
$SPP_MISO_{Load} = 5000.0\text{ MW}$  

$PJM_NE_{LoadStressFactor} = PJM_NE_{Load}/Bus_{GenCap} = 2.0$  
$PJM_NE_{Load} = 10000.0\text{ MW}$  

$SERC_SE_{LoadStressFactor} = SERC_SE_{Load}/Bus_{GenCap} = 1.0$  
$SERC_SE_{Load} = 5000.0\text{ MW}$  

$ERCOT_{LoadStressFactor} = ERCOT_{Load}/Bus_{GenCap} = 1.0$  
$ERCOT_{Load} = 5000.0\text{ MW}$  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} + $  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}$  
$\}\text{ MW} = $  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

#### LMP Spread (`lmp_spread`)::Test Case 3 A: Expected Results
$Operating Cost = \{Total System Load * c_g\}$  
$=\{35,000 *50\} = USD\text{ 1,750,000}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 A: Results

**Output Path:** `./stress_out/Commit C4`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c4     | single   | 1.750e+06       | 0.000      | 0.000             | 1                        | 

---

##### ASR-DASH — Commit `c4` (single): Run Configuration

| Parameter | Value                                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| scenario  | single                                                                                                                                                      |
| mc_mode   | set                                                                                                                                                         |
| line      | -                                                                                                                                                           |
| k_load    | `{"PJM_NE": 2.0}`                                                                                                                                                        |
| k_line    | `{}` |
| mc_bus    | `{}`                                                                                                                                                        |
| dc_site   | N                                                                                                                                                           |

**Results Summary:**

| Metric                                | Value                     |
| ------------------------------------- | ------------------------- |
| Objective (USD)                       | 1.750e+06                 |
| LMP Spread (USD/MWh)                  | 0.000                     |
| Max LMP                               | 50.000 @ WECC_NW          |
| Max Line Loading (p.u.)               | 1.000 @ L_WECC_NW_WECC_SW |
| Near-binding Constraints (≥0.95 p.u.) | 1                         |

**Most Stressed Lines:**

| Line               | Loading (p.u.) |
| ------------------ | -------------- |
| L_WECC_SW_SPP_MISO | 1.00           |
| L_SPP_MISO_PJM_NE  | 0.85           |
| L_SPP_MISO_ERCOT   | 0.75           |

---

**ASR- TODO>>DONE:**  
##### DC OPF power balance equation evaluation
Write the DC OPF power balance equations for test case 3A from chatGPT discussions  
**Key Observations:**  
* PJM_NE needs **2,000 MW imports** i.e.  
  * $\{PJM\_NE_{imports} =$
  * $\{PJM\_NE_{Load} = 10000.0\text{ MW}\} - \{Bus_{GenPJM_NCap} = 8000.0\text{ MW}\}$
  * $= \{10000 - 8000\} = 2000\text{ MW} = \{PJM\_NE_{imports}$ i.e.
  * $PJM\_NE_{imports} = 2000\text{ MW}$
* Power is routed via **SPP_MISO** since: 
  * SPP_MISO is nodal in most stressed lines:
  * [L_WECC_SW_SPP_MISO, L_SPP_MISO_PJM_NE, L_SPP_MISO_ERCOT]
  * SPP_MISO is acting as a **hub**.
* The solver found a feasible dispatch with following DC OPF power flow:
  * Loading (p.u.):
    * L_SPP_MISO_PJM_NE: 0.85
    * L_SPP_MISO_ERCOT: 0.75
    * L_WECC_SW_SPP_MISO: 1.0
* Only L_WECC_SW_SPP_MISO: 1.0 == near binding, hence: 
  * Near-Binding Count (`near_bind_ct`) = 1

**Key concept 1:** Flows ≠ Net Imports  
In a DC OPF network, line flows are determined by:
- nodal injections
- network topology
- Kirchhoff’s laws

❗ A line’s flow is not equal to: “load deficit of the sink bus”  
Instead:
Line flow = component of the system-wide power redistribution

**Key concept 2:** PyPSA DC OPF Definition:  

$\text{line loading (p.u.)}$  
$= \frac{|\text{power flow on line (MW)}|}{\text{thermal limit of line (MW)}}$  

**Given: Thermal limit of every inter-regional line**  
$s_{nom} = 5000\text{ MW} == F_{SPP_MISO \rightarrow PJM_NE}$  

So:$\text{ line loading (p.u.)}$ for each of the most Stressed Lines:  
[L_SPP_MISO_PJM_NE, L_SPP_MISO_ERCOT, L_WECC_SW_SPP_MISO]:  
L_SPP_MISO_PJM_NE:  
$F_{SPP_MISO \rightarrow PJM_NE}\text{ line loading (p.u.)} = 0.85$  
$= \frac{F^{max}_{SPP_MISO \rightarrow PJM_NE}}{5000}$  
i.e.   
$0.85 * 5000 = F^{max}_{SPP_MISO \rightarrow PJM_NE}$  
$4250 = F^{max}_{SPP_MISO \rightarrow PJM_NE}$  
i.e.  
$F^{max}_{SPP_MISO \rightarrow PJM_NE} = 4250\text{ MW}$  

L_SPP_MISO_ERCOT:  
$F_{SPP_MISO \rightarrow ERCOT}\text{ line loading (p.u.)} = 0.75$  
$= \frac{F^{max}_{SPP_MISO \rightarrow ERCOT}}{5000}$  
i.e.   
$0.75 * 5000 = F^{max}_{SPP_MISO \rightarrow ERCOT}$  
$3750 = F^{max}_{SPP_MISO \rightarrow ERCOT}$  
i.e.  
$F^{max}_{SPP_MISO \rightarrow ERCOT} = 3750\text{ MW}$  

L_WECC_SW_SPP_MISO:  
$F_{WECC_SW \rightarrow SPP_MISO}\text{ line loading (p.u.)} = 1.0$  
$= \frac{F^{max}_{WECC_SW \rightarrow SPP_MISO}}{5000}$  
i.e.   
$1.0 * 5000 = F^{max}_{WECC_SW \rightarrow SPP_MISO}$  
$5000 = F^{max}_{WECC_SW \rightarrow SPP_MISO}$  
i.e.  
$F^{max}_{WECC_SW \rightarrow SPP_MISO} = 5000\text{ MW}$  
i.e.  
* WECC_SW is exporting **at full line capacity**  
---

**DC OPF Power Balance Equations:**  
At **SPP_MISO**, the node balance looks like:  
$\{\sum P_{gen} - \sum P_{load}\} = \{\sum F_{out} - \sum F_{in}\}$  
where:  
*  $\sum P_{gen} = 8000\text{ MW}$
*  $\sum P_{load} = 5000\text{ MW}$
*  $\sum F_{out} =$
   *  $\{\{F_{SPP_MISO \rightarrow PJM_NE} = 4250\} + \{F_{SPP_MISO \rightarrow ERCOT} = 3750\}\}\text{ MW}$
   *  $\{\{4250\} + \{3750\}\} = \{8000\}\text{ MW}$
*  $\sum F_{in} = F_{WECC_SW \rightarrow SPP_MISO} = 5000\text{ MW}$

Balanced DC OPF @ **SPP_MISO**:  
$\{8000 - 5000\} = \{8000 - 5000\} == \{3000\} = \{3000\}$  

**Tabulating SPP_MISO outbound flows:**

| Destination       | Flow (MW)   | p.u.     |
| ----------------- | ----------- | -------- |
| PJM_NE            | **4250**    | **0.85** |
| ERCOT             | **3750**    | **0.75** |
| **Total outflow** | **8000 MW** | —        |

**Tabulating SPP_MISO inbound flows:**

| Source                   | Flow (MW)   |
| ------------------------ | ----------- |
| WECC_SW                  | **5000**    |
| Local generation surplus | **~3000**   |
| **Total inflow**         | **8000 MW** |

✔ Power balance satisfied
✔ No violations
✔ Numbers now reconcile

---

At **PJM_NE**, the node balance looks like:  
$\{\sum P_{gen} - \sum P_{load}\} = \{\sum F_{out} - \sum F_{in}\}$  
where:  
*  $\sum P_{gen} = 8000\text{ MW}$
*  $\sum P_{load} = 10000\text{ MW}$
*  $\sum F_{in} = F_{SPP_MISO \rightarrow PJM_NE} = 4250\text{ MW}$
*  **Note:**
   *  Gross flows satisfy network physics (Kirchhoff + PTDFs)
   *  Given DC OPF needs to balance out at PJM_NE node
   *  **$\sum F_{out}$ needs to be deduced**. Solver output does not explicitly point PJM_NE export
*  $\sum F_{out} = PJM\_NE_{export}\text{ via } F_{PJM_NE \rightarrow SERC_SE} =$
*  $\{4250 - 2000\} = \{2250\}\text{ MW}$

Balanced DC OPF @ **PJM_NE**:  
$\{8000 - 10000\} = \{2250 - 4250\} == \{-2000\} = \{-2000\}$  

where:
Power Transfer Distribution Factor (PTDF) is: Fraction of a 1 MW injection at one bus (and 1 MW withdrawal at another) flows on a given transmission line  

**Power Transfer Distribution Factor (PTDF) Mathematical form:**  
$\text{PTDF}_{\ell,(i\rightarrow j)} = \frac{\Delta F_\ell}{\Delta P_{i\rightarrow j}}$
* $(\Delta P_{i\rightarrow j} = 1\ \text{MW}) \text{ (inject at *i*, withdraw at *j*)}$
* $(\Delta F_\ell) = \text{resulting change in flow on line ℓ (MW)}$

So if:
* PTDF = **0.30** → 0.3 MW flows on that line
* PTDF = **−0.20** → 0.2 MW flows in the opposite direction
* PTDF = **0** → that transaction doesn’t use that line

PTDF effect on LMPs:  
* In DC OPF, **price differences come from binding constraints weighted by PTDFs**:
  * $\text{LMP}_i - \text{LMP}_j = $
  * $\sum_{\ell \in \text{binding lines}} (\lambda_\ell \times \text{PTDF}_{\ell,(i\rightarrow j)})$

where: 
* $(\lambda_\ell)$: shadow price of line ℓ (non-zero only if binding)
* If PTDF = 0 → that line doesn’t affect the price difference between those buses

PTDF Intuition: 
* Think of PTDF as a **routing percentage**
* The grid spreads power over *many* paths
* PTDF tells you **how much of “your” MW uses each path**

---

**Key takeaway (lock this in):**  
> **Congestion creates LMP spread only when a binding line has a non-zero PTDF between two buses *and* the marginal costs differ across that cut.**

---

#### LMP Spread (`lmp_spread`)::Test Case 3 B: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  

$WECC_NW_{LoadStressFactor} = WECC_NW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_NW_{Load} = 5000.0\text{ MW}$  

$WECC_SW_{LoadStressFactor} = WECC_SW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_SW_{Load} = 5000.0\text{ MW}$  

$SPP_MISO_{LoadStressFactor} = SPP_MISO_{Load}/Bus_{GenCap} = 1.0$  
$SPP_MISO_{Load} = 5000.0\text{ MW}$  

$PJM_NE_{LoadStressFactor} = PJM_NE_{Load}/Bus_{GenCap} = 2.0$  
$PJM_NE_{Load} = 10000.0\text{ MW}$  

$SERC_SE_{LoadStressFactor} = SERC_SE_{Load}/Bus_{GenCap} = 1.0$  
$SERC_SE_{Load} = 5000.0\text{ MW}$  

$ERCOT_{LoadStressFactor} = ERCOT_{Load}/Bus_{GenCap} = 1.0$  
$ERCOT_{Load} = 5000.0\text{ MW}$  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} + $  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}$  
$\}\text{ MW} = $  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {"L_SPP_MISO_PJM_NE": 0.9}  
$\text{L\_SPP\_MISO\_PJM\_NE} = 0.9 * \{line_{snom} = 5,000\} = 4,500\text{ MW}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 B: Expected Results
$Operating Cost = \{Total System Load * c_g\}$  
$=\{35,000 *50\} = USD\text{ 1,750,000}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 B: Results

**Output Path:** `./stress_out/Commit C5`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c5     | single   | 1.750e+06       | 0.000      | 0.000             | 1                        | 

---

#### LMP Spread (`lmp_spread`)::Test Case 3 C: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  

$WECC_NW_{LoadStressFactor} = WECC_NW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_NW_{Load} = 5000.0\text{ MW}$  

$WECC_SW_{LoadStressFactor} = WECC_SW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_SW_{Load} = 5000.0\text{ MW}$  

$SPP_MISO_{LoadStressFactor} = SPP_MISO_{Load}/Bus_{GenCap} = 1.0$  
$SPP_MISO_{Load} = 5000.0\text{ MW}$  

$PJM_NE_{LoadStressFactor} = PJM_NE_{Load}/Bus_{GenCap} = 2.0$  
$PJM_NE_{Load} = 10000.0\text{ MW}$  

$SERC_SE_{LoadStressFactor} = SERC_SE_{Load}/Bus_{GenCap} = 1.0$  
$SERC_SE_{Load} = 5000.0\text{ MW}$  

$ERCOT_{LoadStressFactor} = ERCOT_{Load}/Bus_{GenCap} = 1.0$  
$ERCOT_{Load} = 5000.0\text{ MW}$  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} + $  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}$  
$\}\text{ MW} = $  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {"L_SPP_MISO_PJM_NE": 0.8}  
$\text{L\_SPP\_MISO\_PJM\_NE} = 0.8 * \{line_{snom} = 5,000\} = 4,000\text{ MW}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 C: Expected Results
$Operating Cost = \{Total System Load * c_g\}$  
$=\{35,000 *50\} = USD\text{ 1,750,000}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 C: Results

**Output Path:** `./stress_out/Commit C6`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c6     | single   | 1.750e+06       | 0.000      | 0.000             | 2                        | 

---

#### LMP Spread (`lmp_spread`)::Test Case 3 D: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  

$WECC_NW_{LoadStressFactor} = WECC_NW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_NW_{Load} = 5000.0\text{ MW}$  

$WECC_SW_{LoadStressFactor} = WECC_SW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_SW_{Load} = 5000.0\text{ MW}$  

$SPP_MISO_{LoadStressFactor} = SPP_MISO_{Load}/Bus_{GenCap} = 1.0$  
$SPP_MISO_{Load} = 5000.0\text{ MW}$  

$PJM_NE_{LoadStressFactor} = PJM_NE_{Load}/Bus_{GenCap} = 2.0$  
$PJM_NE_{Load} = 10000.0\text{ MW}$  

$SERC_SE_{LoadStressFactor} = SERC_SE_{Load}/Bus_{GenCap} = 1.0$  
$SERC_SE_{Load} = 5000.0\text{ MW}$  

$ERCOT_{LoadStressFactor} = ERCOT_{Load}/Bus_{GenCap} = 1.0$  
$ERCOT_{Load} = 5000.0\text{ MW}$  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} + $  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}$  
$\}\text{ MW} = $  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {  
    "L_WECC_NW_WECC_SW": 1.0, "L_WECC_SW_SPP_MISO": 1.0, "L_SPP_MISO_ERCOT": 0.8,  
    "L_SPP_MISO_PJM_NE": 0.8, "L_PJM_NE_SERC_SE": 0.8, "L_SERC_SE_ERCOT": 0.8  
        }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.8 * 5,000 = 4,000\text{ MW}$ 

#### LMP Spread (`lmp_spread`)::Test Case 3 D: Expected Results
$Operating Cost = \{Total System Load * c_g\}$  
$=\{35,000 *50\} = USD\text{ 1,750,000}$  

#### LMP Spread (`lmp_spread`)::Test Case 3 D: Results

**Output Path:** `./stress_out/Commit C7`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c7     | single   | 1.750e+06       | 0.000      | 0.000             | 3                        | 

---

#### LMP Spread (`lmp_spread`)::Test Case 3 E: Conditions
$Bus_{Load} = Bus_{GenCap}$  
$Bus_{GenCap} = 8000.0 MW$  
$Total Generation Capacity = Buses_N * Bus_{GenCap} = 6 * 8000 = 48,000\text{ MW}$  

$WECC_NW_{LoadStressFactor} = WECC_NW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_NW_{Load} = 5000.0\text{ MW}$  

$WECC_SW_{LoadStressFactor} = WECC_SW_{Load}/Bus_{GenCap} = 1.0$  
$WECC_SW_{Load} = 5000.0\text{ MW}$  

$SPP_MISO_{LoadStressFactor} = SPP_MISO_{Load}/Bus_{GenCap} = 1.0$  
$SPP_MISO_{Load} = 5000.0\text{ MW}$  

$PJM_NE_{LoadStressFactor} = PJM_NE_{Load}/Bus_{GenCap} = 2.0$  
$PJM_NE_{Load} = 10000.0\text{ MW}$  

$SERC_SE_{LoadStressFactor} = SERC_SE_{Load}/Bus_{GenCap} = 1.0$  
$SERC_SE_{Load} = 5000.0\text{ MW}$  

$ERCOT_{LoadStressFactor} = ERCOT_{Load}/Bus_{GenCap} = 1.0$  
$ERCOT_{Load} = 5000.0\text{ MW}$  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} +$  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}$  
$\}\text{ MW} =$  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$line_{snom} = 5,000\text{ MW}$  
$c_g = marginal cost (USD/MWh) = 50.00$  

k_line= {  
    "L_WECC_NW_WECC_SW": 1.0, "L_WECC_SW_SPP_MISO": 1.0, "L_SPP_MISO_ERCOT": 0.8,  
    "L_SPP_MISO_PJM_NE": 0.8, "L_PJM_NE_SERC_SE": 0.8, "L_SERC_SE_ERCOT": 0.8  
        }  
$line_{snom} = 5000$  
$line_{effectiveCap} = 0.8 * 5,000 = 4,000\text{ MW}$ 

mc_bus = {
  "PJM_NE": 55.0,
  "SPP_MISO": 50.0
}

**ASR- Note:** Optiona mc_bus values to trigger LMP_Spread 
mc_bus = {
  "WECC_NW": 40.0,
  "WECC_SW": 45.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 70.0,
  "SERC_SE": 55.0,
  "ERCOT": 60.0
}

#### LMP Spread (`lmp_spread`)::Test Case 3 E: Expected Results
$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} +$  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}\}\text{ MW} =$  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

Marginal Cost $(c_g)/bus$ = {  
$\{WECC_NW_{cg} = 50\} + \{WECC_SW_{cg} = 50\} + \{SPP_MISO_{cg} = 50\} +$  
$\{PJM_NE_{cg} = 55\} + \{SERC_SE_{cg} = 50 \} + \{ERCOT_{cg} = 50\}$  
}  

$Operating Cost = \{$  
$\{50 * 5000\} + \{50 * 5000\} + \{50 * 5000\} +$  
$\{55 * 10000\} + \{50 * 5000\} + \{50 * 5000\}\} =$  
$= USD\text{ 1,800,000}$  

**ASR- TODO>>DONE:**  
##### Explantion: LMP_Spread trigger with Scarcity pricing 
**LMP Spread Triggers:**
For LMPs to separate, both the must occur:
* A bus **cannot meet its load locally**, and
* Imports to that bus are **constrained**
* DC OPF Core rule on import constraints:
  * LMP separation only occurs when a constraint is binding on the marginal supply path
  * Congestion alone does NOT create LMP spread
  * Congestion + heterogeneous marginal costs does
* Asymmetric marginal generation cost across the bus
  * Uniform $c_g = 50\ \text{USD/MWh at all buses}$ will not trigger LMP spread
* **Note:** While Congestion redistributes *flows*
  * Marginal supply cost remains the same
  * $\boxed{\text{LMP}_i = 50\ \forall i}$
  * ➡️ **No LMP spread is mathematically possible in this scenario**

**Key Point:**
* In a DC OPF, congestion creates price separation only when it forces a bus to use a higher-cost marginal resource.
* With uniform marginal costs, LMP spread is mathematically impossible — no matter how congested the network is.

#### LMP Spread (`lmp_spread`)::Test Case 3 E: Results

**Output Path:** `./stress_out/Commit C8`

| Commit | Scenario | Objective (USD) | LMP Spread | Max Loading (p.u.) | Near-Binding Constraints | k (First Near-Bind) |
|--------|----------|-----------------|------------|-------------------|--------------------------|---------------------|
| c8     | single   | 1.760e+06       | 5.000      | 0.000             | 3                        | 

---

##### ASR-DASH — Commit `c8` (single): Run Configuration

| Parameter | Value                                                                                                                                                       |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| scenario  | single                                                                                                                                                      |
| mc_mode   | set                                                                                                                                                         |
| line      | -                                                                                                                                                           |
| k_load    | `{"PJM_NE": 2.0}`                                                                                                                                                        |
| k_line    | `{"L_SPP_MISO_ERCOT": 0.8, "L_SPP_MISO_PJM_NE": 0.8, "L_PJM_NE_SERC_SE": 0.8, "L_SERC_SE_ERCOT": 0.8}` |
| mc_bus    | `{"SPP_MISO": 50.0, "PJM_NE": 55.0}`                                                                                                                                                        |
| dc_site   | N                                                                                                                                                           |

**Results Summary:**

| Metric                                | Value                     |
| ------------------------------------- | ------------------------- |
| Objective (USD)                       | 1.760e+06                 |
| LMP Spread (USD/MWh)                  | 5.000                     |
| Max LMP                               | 50.000 @ WECC_NW          |
| Max Line Loading (p.u.)               | 1.000 @ L_WECC_NW_WECC_SW |
| Near-binding Constraints (≥0.95 p.u.) | 3                         |

**Most Stressed Lines:**

| Line               | Loading (p.u.) |
| ------------------ | -------------- |
| L_WECC_SW_SPP_MISO | 1.00           |
| L_SPP_MISO_PJM_NE  | 1.00           |
| L_PJM_NE_SERC_SE   | 1.00           |

---

**ASR- TODO>>DONE:**  
Compute/Check Objective value of 1.760e+06  

##### Explanation: Operating Cost with LMP Spread
Calculated value from above:  $Operating Cost = \{$  
$\{50 * 5000\} + \{50 * 5000\} + \{50 * 5000\} +$  
$\{55 * 10000\} + \{50 * 5000\} + \{50 * 5000\}\} =$  
$= USD\text{ 1,800,000}$  

DC OPF Solver: Objective = 1.760e+06 i.e. 1,760,000 (USD) 

**Issue:**  
* **Wrong Formulation:** Operating cost = Σ (bus load × bus marginal cost)  
* **DC OPF Formulation:** Objective = Σ (generator dispatch × generator marginal cost)  
i.e.:  
* ❌ load × price
  But:
* ✅ generation × marginal cost

* \$40k discrepancy comes from
  * PJM_NE **does not generate 10,000 MW**
  * PJM_NE generates only 2,000 MW at its higher marginal cost
  * The remaining 8,000 MW of PJM_NE load is imported from $50/MWh generators

**Generation actually dispatched:**
* WECC_NW / WECC_SW / SPP_MISO / SERC_SE / ERCOT
  → supply 33,000 MW at $50/MWh  
* PJM_NE
  → supplies 2,000 MW at $55/MWh  

$Total System Load = \{$  
$WECC_NW_{Load} + WECC_SW_{Load} + SPP_MISO_{Load} +$  
$PJM_NE_{Load} + SERC_SE_{Load} + ERCOT_{Load}\}\text{ MW} =$  
$\{5000.0 + 5000.0 + 5000.0 + 10000.0 + 5000.0 + 5000.0\}$  
$35,000\text{ MW}$  

$PJM_NE_{Load} = 2000\text{ MW}$ :: Load suplied at Premium generation cost $55    
Non Premium Load = $\{35,000 - 2000\} = 33,000\text{ MW}$ :: Load suplied at standard generation cost $50  
Operating cost of Premium Load: $OPCost_{PL} = \{55 * 2000\} = \$110,000$  
Operating cost of Non Premium Load: $OPCost_{NPL} = \{50 * 33000\} = \$1,650,000$  
$OPCost_{PL} + OPCost_{NPL} = 110,000 + 1,650,000 = \$1,760,000$  

##### DC OPF power balance equation evaluation [TBC]
DC OPF power balance equations for test case 3 E w/ solver feasible DC OPF power flow:
  * Loading (p.u.):
    * L_WECC_SW_SPP_MISO: 1.0
    * L_SPP_MISO_PJM_NE: 1.0
    * L_PJM_NE_SERC_SE: 1.0

**Key concept 2:** PyPSA DC OPF Definition:  
$\text{line loading (p.u.)}$  
$= \frac{|\text{power flow on line (MW)}|}{\text{thermal limit of line (MW)}}$  

**Given: Thermal limit of every inter-regional line**  
$line_{snom} = 5,000\text{ MW}$  

So:$\text{ line loading (p.u.)}$ for each of the most Stressed Lines:  
[L_WECC_SW_SPP_MISO, L_SPP_MISO_PJM_NE, L_PJM_NE_SERC_SE]:
L_WECC_SW_SPP_MISO:
$F_{WECC_SW \rightarrow SPP_MISO}\text{ line loading (p.u.)} = 1.0$  
$= \frac{F^{max}_{WECC_SW \rightarrow SPP_MISO}}{5000}$  
i.e.   
$1.0 * 5000 = F^{max}_{WECC_SW \rightarrow SPP_MISO}$  
$5000 = F^{max}_{WECC_SW \rightarrow SPP_MISO}$  
i.e.  
$F^{max}_{WECC_SW \rightarrow SPP_MISO} = 5000\text{ MW}$  

L_SPP_MISO_PJM_NE:
$F_{SPP_MISO \rightarrow PJM_NE}\text{ line loading (p.u.)} = 1.0$  
$= \frac{F^{max}_{SPP_MISO \rightarrow PJM_NE}}{5000}$  
i.e.   
$1.0 * 5000 = F^{max}_{SPP_MISO \rightarrow PJM_NE}$  
$5000 = F^{max}_{SPP_MISO \rightarrow PJM_NE}$  
i.e.  
$F^{max}_{SPP_MISO \rightarrow PJM_NE} = 5000\text{ MW}$  

L_PJM_NE_SERC_SE:
$F_{PJM_NE \rightarrow SERC_SE}\text{ line loading (p.u.)} = 1.0$  
$= \frac{F^{max}_{PJM_NE \rightarrow SERC_SE}}{5000}$  
i.e.   
$1.0 * 5000 = F^{max}_{PJM_NE \rightarrow SERC_SE}$  
$5000 = F^{max}_{PJM_NE \rightarrow SERC_SE}$  
i.e.  
$F^{max}_{PJM_NE \rightarrow SERC_SE} = 5000\text{ MW}$  

**DC OPF Power Balance Equations:**  
At **SPP_MISO**, the node balance looks like:  
$\{\sum P_{gen} - \sum P_{load}\} = \{\sum F_{out} - \sum F_{in}\}$  
where:  
*  $\sum P_{gen} = 8000\text{ MW}$
*  $\sum P_{load} = 5000\text{ MW}$
*  $\{\sum P_{gen} - \sum P_{load}\} = 3000$
*  $\sum F_{out} =$
   *  $\{\{F_{SPP_MISO \rightarrow PJM_NE} = (k_line=0.8) * (5000)\} +$
      *  $\{F_{SPP_MISO \rightarrow ERCOT} = (k_line=0.8) * (5000)\}\}\text{ MW}$
   *  $\{\{4000\} + \{4000\}\} = \{8000\}\text{ MW}$
*  $\sum F_{in} = F_{WECC_SW \rightarrow SPP_MISO} = 5000\text{ MW}$
*  $\{\sum F_{out} - \sum F_{in}\} = \{8000 - 5000\} = 3000$

Balanced DC OPF @ **SPP_MISO**:  
$\{8000 - 5000\} = \{8000 - 5000\} == \{3000\} = \{3000\}$  

At **PJM_NE**, the node balance looks like:  
$\{\sum P_{gen} - \sum P_{load}\} = \{\sum F_{out} - \sum F_{in}\}$  
where:  
*  $\sum P_{gen} = 8000\text{ MW}$
*  $\sum P_{load} = 10000\text{ MW}$
*  $\{\sum P_{gen} - \sum P_{load}\} = -2000$
*  $\sum F_{out} =$
   *  $\{F_{PJM_NE \rightarrow SERC_SE} \le (k_line=0.8) * (5000)\}$  
*  $\sum F_{in} = F_{SPP_MISO \rightarrow PJM_NE} = 4000\text{ MW}$
*  **Since:**  
   *  $\{\sum P_{gen} - \sum P_{load}\} = -2000\text{ MW }\And$
   *  $\sum F_{in} = 4000\text{ MW}$
   *  $\sum F_{out} will be 2000\text{ MW}$
*  **Therefore:**
   *  $\{\sum F_{out} - \sum F_{in}\} = \{2000 - 4000\} = -2000$

Balanced DC OPF @ **PJM_NE**:  
$\{8000 - 10000\} = \{2000 - 4000\} == \{-2000\} = \{-2000\}$  

---

**ASR- TODO>>DONE:**  
Extensive probing/testing of DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Cases  
### DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Plan

> Q:  
>   Objective function i.e. operating cost linearly increases with load until such time all the generation capacity on the devnet SLD 6 node bus is unable to meet the total system load.  
>   We can build a linear graph by plotting total system load w/ solver objective function result  

>   Similarly: by de-rating k_line sequentially we can see the near binding constraint count result by the solver change. There is an evident direct correlation.  

>   However with LMP spread, re-verse engineering the DC OPF balance from the solver most >   stressed lines is a lot more complex.  
>   Is this fundamentally because of hte iterative nature of the solver i.e. fundamental to >   Linear Programming?  


**Yes — fundamentally. Pin-point reason:**  

* **Objective vs load** and **near-bind vs k_line** are **direct primal effects** of linear constraints → easy, monotonic, interpretable.
* **LMP spread** is a **dual outcome** (shadow prices) → it emerges from **which constraint is marginal at the optimum**, not just which is most loaded.

**Why this is harder (core point):**
* LMPs come from **Karush–Kuhn–Tucker (KKT) conditions** (duals), not from primal balances alone.
* A line can be **most loaded** yet **price-irrelevant** if its dual = 0.
* Small changes can **swap the active marginal constraint**, causing **non-local price effects**.

**Bottom line for your notes:**
> LMP spread complexity is **not iteration noise**; it is **inherent to LP duality and degeneracy**, where prices depend on *which* constraint is marginal, not *how tight* a constraint looks.

> Ok in the contained 6 node devnet SLD[WECC_NW, WECC_SW, SPP_MISO, PJM_NE, SERC_SE, ERCOT]:  
>   For the same total load w/ PJM_NE 10GW, rest at 5GW, k_line at default 1.0,  is there a systematic way we can vary the mc_bus (per-bus generator marginal cost) keeping generation at PJM_NE at $55 to observe LMP spread effects?

Yes, you can plot per case. For each case you will be able to record and plot:  
- lmp_spread
- max_loading_pu
- top_lines (most stressed lines)

#### DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 4
Refer:  
- [DevNet Stress Report_5.html](./DevNet%20Stress%20Report_5.html)  
- Commit ID: [1,... 10]

**Test Plan cases:**  
1: mc_bus = {
  "WECC_NW": 50.0,
  "WECC_SW": 50.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 60.0,
  "SERC_SE": 50.0,
  "ERCOT": 50.0
}  

2: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 70.0,
  "SPP_MISO": 70.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  $$

3: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 70.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  

4: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 50.0,
  "SPP_MISO": 70.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  

5: mc_bus = {
  "WECC_NW": 50.0,
  "WECC_SW": 70.0,
  "SPP_MISO": 70.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  

6: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 70.0,
  "SPP_MISO": 70.0,
  "PJM_NE": 60.0,
  "SERC_SE": 50.0,
  "ERCOT": 70.0
}  

7: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 70.0,
  "SPP_MISO": 70.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 50.0
}  

8: mc_bus = {
  "WECC_NW": 50.0,
  "WECC_SW": 50.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  

9: mc_bus = {
  "WECC_NW": 70.0,
  "WECC_SW": 50.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 60.0,
  "SERC_SE": 70.0,
  "ERCOT": 70.0
}  

10: mc_bus = {
  "WECC_NW": 50.0,
  "WECC_SW": 50.0,
  "SPP_MISO": 50.0,
  "PJM_NE": 60.0,
  "SERC_SE": 50.0,
  "ERCOT": 70.0
}  

##### DevNet Stress Test::LMP Spread (`lmp_spread`)::Test Case 4: Results
**Refer:** [devnet_plots.xlsx:DevNetGen_mc<>LMP](devnet_plots.xlsx)  

---

# Reference
- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev2](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15-zeronode-ca/c/69680406-a7c8-8328-95d8-08889046f1b2)  

- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev3](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15/c/6972f266-e858-832e-b4d8-ec7ed137bbfc)  

---

*Prepared collaboratively with ChatGPT-5, October 2025*  