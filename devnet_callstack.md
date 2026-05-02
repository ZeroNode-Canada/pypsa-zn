# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 ZeroNode
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# devnet_callstack.md
# ------------------------------------------------------------------------------

# devnet call stack
Call trace of the devnet network modelling and analysis stack

---

# Table of Contents
- [SPDX-License-Identifier: Apache-2.0](#spdx-license-identifier-apache-20)
- [](#)
- [Copyright 2025 ZeroNode](#copyright-2025-zeronode)
- [](#-1)
- [Licensed under the Apache License, Version 2.0 (the "License");](#licensed-under-the-apache-license-version-20-the-license)
- [you may not use this file except in compliance with the License.](#you-may-not-use-this-file-except-in-compliance-with-the-license)
- [You may obtain a copy of the License at](#you-may-obtain-a-copy-of-the-license-at)
- [](#-2)
- [http://www.apache.org/licenses/LICENSE-2.0](#httpwwwapacheorglicenseslicense-20)
- [](#-3)
- [Unless required by applicable law or agreed to in writing, software](#unless-required-by-applicable-law-or-agreed-to-in-writing-software)
- [distributed under the License is distributed on an "AS IS" BASIS,](#distributed-under-the-license-is-distributed-on-an-as-is-basis)
- [WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.](#without-warranties-or-conditions-of-any-kind-either-express-or-implied)
- [See the License for the specific language governing permissions and](#see-the-license-for-the-specific-language-governing-permissions-and)
- [limitations under the License.](#limitations-under-the-license)
- [devnet\_callstack.md](#devnet_callstackmd)
- [------------------------------------------------------------------------------](#------------------------------------------------------------------------------)
- [devnet call stack](#devnet-call-stack)
- [Table of Contents](#table-of-contents)
- [devnet call stack](#devnet-call-stack-1)
  - [devnet\_stress.py function list](#devnet_stresspy-function-list)
  - [devnet\_stress.py call stack map](#devnet_stresspy-call-stack-map)
    - [Entry branch: `main()`](#entry-branch-main)
    - [Interactive branch: `researcher_loop()` (R/C/Q loop)](#interactive-branch-researcher_loop-rcq-loop)
    - [Commit branch: `researcher_loop()` when user selects `C`](#commit-branch-researcher_loop-when-user-selects-c)
    - [HTML/reporting branch: `update_index_html(outdir, devnet)`](#htmlreporting-branch-update_index_htmloutdir-devnet)
    - [Lower-level compute primitives](#lower-level-compute-primitives)
- [Reference](#reference)

---

# devnet call stack
Call trace of the devnet network modelling and analysis stack

## devnet_stress.py function list

- def confirm(prompt)
- def solve_with_duals(...)
- def apply_load_multipliers(...)
- def apply_corridor_reducers(...)
- def apply_gen_marginal_cost_by_bus(...)
- def resolve_dc_csv_values(...)
- def collect_results(...)
- def write_outputs(...)
- def parse_json_dict(...)
- def resolve_byog_mc(...)
- def run_single(...)
- def run_sweep_line(...)
- def build_argparser(...)
- def build_args_catalog(...)
- def capture_catalog_lines(...)
- def print_two_columns(...)
- def prompt_custom_k_load(...)
- def prompt_custom_k_line(...)
- def prompt_custom_mc_bus(...)
- def _pick_from_menu(...)
- def configure_args_menu(...)
- def _dashboard_from_single(...)
- def _dashboard_from_sweep(...)
- def dashboard_text(...)
- def devnet_base_params(...)
- def build_sanity_panel_lines(...)
- def write_commit_dashboard_md(...)
- def update_index_html(...)
- def print_dashboard(...)
- def run_preview(...)
- def _next_commit_id(...)
- def researcher_loop(...)
- def main()

---

## devnet_stress.py call stack map

### Entry branch: `main()`
main()
├─ build_argparser(DEVNET_BLD_PATH)
│  └─ (argparse .parse_args() in main)
├─ build_args_catalog(devnet)
│  └─ resolve_dc_csv_values(devnet)
├─ capture_catalog_lines(catalog)
├─ build_sanity_panel_lines(devnet)
│  └─ devnet_base_params(devnet)
├─ print_two_columns(left, right, ...)
├─ update_index_html(args.outdir, devnet)      # initial HTML bootstrap
└─ researcher_loop(devnet, args, catalog)

---

### Interactive branch: `researcher_loop()` (R/C/Q loop)
researcher_loop(devnet, args, catalog)
├─ configure_args_menu(devnet, args)
│  ├─ build_args_catalog(devnet)
│  │  └─ resolve_dc_csv_values(devnet)
│  ├─ _pick_from_menu(title, options, default_idx)
│  ├─ prompt_custom_k_load(devnet)             # when k_load == "__CUSTOM__"
│  ├─ prompt_custom_k_line(devnet)             # when k_line == "__CUSTOM__"
│  ├─ prompt_custom_mc_bus(devnet)             # when mc_bus == "__CUSTOM__"
│  └─ sets:
│     ├─ scenario
│     ├─ mc_mode
│     ├─ k_load
│     ├─ k_line
│     ├─ mc_bus
│     ├─ byog_mc
│     ├─ dc_p_set
│     ├─ dc_p_nom
│     ├─ line
│     ├─ kmin
│     ├─ kmax
│     └─ kstep
│
├─ run_preview(devnet, args)
│  ├─ run_single(devnet, args, tag="preview_*")         # baseline/single
│  │  ├─ parse_json_dict(args.k_load)
│  │  ├─ parse_json_dict(args.k_line)
│  │  ├─ parse_json_dict(args.mc_bus)
│  │  ├─ apply_load_multipliers(n, k_load_dict)
│  │  ├─ apply_corridor_reducers(n, k_line_dict)
│  │  ├─ apply_gen_marginal_cost_by_bus(n, mc_bus_dict, mode=args.mc_mode)
│  │  ├─ resolve_byog_mc(n, args)                       # devnetDC-sld only
│  │  ├─ solve_with_duals(n, solver=args.solver)
│  │  ├─ collect_results(n)
│  │  └─ write_outputs(Path(args.outdir), tag, results)
│  │
│  └─ run_sweep_line(devnet, args, file_prefix="")      # sweep_line
│     ├─ loop over k values
│     ├─ apply_load_multipliers(..., parse_json_dict(args.k_load))
│     ├─ apply_corridor_reducers(..., {args.line: k})
│     ├─ apply_gen_marginal_cost_by_bus(..., parse_json_dict(args.mc_bus), mode=args.mc_mode)
│     ├─ resolve_byog_mc(n, args)                       # devnetDC-sld only
│     ├─ solve_with_duals(...)
│     ├─ collect_results(...)
│     └─ write sweep_line_summary.csv
│
├─ _dashboard_from_single(res)              # when preview kind == single
├─ _dashboard_from_sweep(df)                # when preview kind == sweep
└─ print_dashboard(args, mode="PREVIEW", dash)
   └─ dashboard_text(args, mode, dash)
      └─ resolve_dc_csv_values(devnet)

---

### Commit branch: `researcher_loop()` when user selects `C`
researcher_loop(...)  [cmd == "c"]
├─ _next_commit_id(outdir)
├─ run_single(..., tag=f"cN_{scenario}")   OR   run_sweep_line(..., file_prefix="cN_")
│  └─ (same compute chain as preview)
├─ _dashboard_from_single(...)             OR   _dashboard_from_sweep(...)
├─ print_dashboard(args, mode=f"COMMIT::cN", dash)
│  └─ dashboard_text(args, mode, dash)
├─ write_commit_dashboard_md(outdir, commit_id, dash_txt)
├─ update_index_html(args.outdir, devnet)
└─ Refresh UX after commit:
   ├─ build_args_catalog(devnet)
   │  └─ resolve_dc_csv_values(devnet)
   ├─ capture_catalog_lines(catalog)
   ├─ build_sanity_panel_lines(devnet)
   │  └─ devnet_base_params(devnet)
   └─ print_two_columns(left, right, ...)

---

### HTML/reporting branch: `update_index_html(outdir, devnet)`
update_index_html(outdir, devnet)
├─ scans stress_out/ for commit artifacts: cN_*.csv, cN_dashboard.md
├─ (internal) _read_commit_metrics(cN)
└─ generates index.html
   ├─ embeds Commit Summary table
   ├─ embeds per-commit dashboards (from cN_dashboard.md)
   ├─ lists per-commit CSV artifacts
   └─ embeds right panel:
      ├─ SLD image:
      │  ├─ ../plots/devnetDC-sld.png   # if DEVNET_NAME == "devnetDC-sld"
      │  └─ ../plots/devnet.png         # otherwise
      └─ sanity panel text from build_sanity_panel_lines(devnet)

---

### Lower-level compute primitives

solve_with_duals(n, solver)
└─ n.optimize(solver_name=solver, assign_all_duals=True)

apply_load_multipliers(n, k_load_dict)
apply_corridor_reducers(n, k_line_dict)
apply_gen_marginal_cost_by_bus(n, mc_bus_dict, mode)
resolve_dc_csv_values(devnet)
collect_results(n)
write_outputs(outdir, tag, results)
parse_json_dict(s)
resolve_byog_mc(n, args)

run_single(n0, args, tag)
└─ deepcopy(n0)
   ├─ apply_load_multipliers
   ├─ apply_corridor_reducers
   ├─ apply_gen_marginal_cost_by_bus
   ├─ optional DC BYOG generator add (devnetDC-sld only)
   ├─ solve_with_duals
   ├─ collect_results
   └─ write_outputs

run_sweep_line(n0, args, file_prefix)
└─ loops k_line values
   ├─ apply_*
   ├─ optional DC BYOG generator add (devnetDC-sld only)
   ├─ solve_with_duals
   ├─ collect_results
   └─ writes sweep_line_summary.csv

---

# Reference
- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15-zeronode-ca/c/68d4302d-a6ec-8333-a0de-f3cfba0f2f26)

- chatGPT: Zeronode.ca > PyPSA Ramp & Dev2::  
  [PyPSA Ramp & Dev2](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15-zeronode-ca/c/69680406-a7c8-8328-95d8-08889046f1b2)

- chatGPT: Zeronode.ca > PyPSA Ramp & Dev3::  
  [PyPSA Ramp & Dev3](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15/c/6972f266-e858-832e-b4d8-ec7ed137bbfc)  

- chatGPT: Zeronode.ca > PyPSA Ramp & Dev4::  
  [PyPSA Ramp & Dev4](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15/c/697a6437-af9c-8320-aa69-6b42cc0cb940)  

- chatGPT: Zeronode.ca > PyPSA Ramp & Dev5::  
  [PyPSA Ramp & Dev5](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15/c/69d2fe05-9dc8-83e8-9ee5-76de3843ca5c)  

---

*Prepared collaboratively with ChatGPT-5, April 2026*