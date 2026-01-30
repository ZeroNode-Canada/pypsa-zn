# devnet call stack
Call trace of the the devnet network modelling and analysis stack

---

# Table of Contents
- [devnet call stack](#devnet-call-stack)
- [Table of Contents](#table-of-contents)
- [devnet call stack](#devnet-call-stack-1)
  - [devnet\_stress.py function list](#devnet_stresspy-function-list)
  - [devnet\_stress.py call stack map](#devnet_stresspy-call-stack-map)
    - [Entry branch: `main()`](#entry-branch-main)
    - [Interactive branch: `researcher_loop()` (R/C/Q loop)](#interactive-branch-researcher_loop-rcq-loop)
    - [Commit branch: `researcher_loop()` when user selects `C`](#commit-branch-researcher_loop-when-user-selects-c)
    - [HTML/reporting branch: `update_index_html(outdir)`](#htmlreporting-branch-update_index_htmloutdir)
    - [Lower-level “compute primitives” (used by solve paths)](#lower-level-compute-primitives-used-by-solve-paths)
- [Reference](#reference)

---

# devnet call stack
Call trace of the the devnet network modelling and analysis stack

## devnet_stress.py function list

- def confirm(prompt)
- def solve_with_duals(...)
- def apply_load_multipliers(...)
- def apply_corridor_reducers(...)
- def apply_gen_marginal_cost_by_bus(...)
- def add_datacenter_site(...)
- def collect_results(...)
- def write_outputs(...)
- def parse_json_dict(...)
- def run_single(...)
- def run_sweep_line(...)
- def build_argparser(...)
- def _pick_from_menu(...)
- def build_args_catalog(...)
- def devnet_base_params(...)
- def build_sanity_panel_lines(...)
- def capture_catalog_lines(...)
- def print_two_columns(...)
- def prompt_custom_k_load(...)
- def prompt_custom_k_line(...)
- def prompt_custom_mc_bus(...)
- def configure_args_menu(...)
- def _dashboard_from_single(...)
- def _dashboard_from_sweep(...)
- def dashboard_text(...)
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
├─ capture_catalog_lines(catalog)
├─ build_sanity_panel_lines(devnet)
├─ print_two_columns(left, right, ...)
├─ update_index_html(outdir)          # initial HTML bootstrap (pre-commit)
└─ researcher_loop(devnet, args, catalog)

---

### Interactive branch: `researcher_loop()` (R/C/Q loop)
researcher_loop(devnet, args, catalog)
├─ configure_args_menu(devnet, args)
│  ├─ build_args_catalog(devnet)
│  ├─ _pick_from_menu(title, options, default_idx)
│  ├─ prompt_custom_k_load(devnet)     # when k_load == "__CUSTOM__"
│  ├─ prompt_custom_k_line(devnet)     # when k_line == "__CUSTOM__"
│  ├─ prompt_custom_mc_bus(devnet)     # when mc_bus == "__CUSTOM__"
│  └─ confirm("...")                   # any Y/N confirmations inside prompts
│
├─ run_preview(devnet, args)
│  ├─ run_single(devnet, args, tag="preview_*")         # baseline/single
│  │  ├─ parse_json_dict(args.k_load)
│  │  ├─ parse_json_dict(args.k_line)
│  │  ├─ parse_json_dict(args.mc_bus)
│  │  ├─ apply_load_multipliers(n, k_load_dict)
│  │  ├─ apply_corridor_reducers(n, k_line_dict)
│  │  ├─ apply_gen_marginal_cost_by_bus(n, mc_bus_dict, mode=args.mc_mode)
│  │  ├─ add_datacenter_site(n, **dc_site_dict)         # if args.dc_site
│  │  ├─ solve_with_duals(n, solver=args.solver)
│  │  ├─ collect_results(n)
│  │  └─ write_outputs(Path(args.outdir), tag, results)
│  │
│  └─ run_sweep_line(devnet, args, file_prefix="")      # sweep_line
│     ├─ apply_load_multipliers(..., parse_json_dict(args.k_load))
│     ├─ apply_corridor_reducers(..., {args.line: k})
│     ├─ apply_gen_marginal_cost_by_bus(..., parse_json_dict(args.mc_bus), mode=args.mc_mode)
│     ├─ add_datacenter_site(...)                       # if args.dc_site
│     ├─ solve_with_duals(...)
│     └─ collect_results(...)                           # per-k (no per-k artifacts)
│
├─ _dashboard_from_single(res)        # when preview kind == single
├─ _dashboard_from_sweep(df)          # when preview kind == sweep
└─ print_dashboard(args, mode="PREVIEW", dash)
   └─ dashboard_text(args, mode, dash)

---

### Commit branch: `researcher_loop()` when user selects `C`
researcher_loop(...)  [cmd == "c"]
├─ _next_commit_id(outdir)                 # monotonic commit id via commit_counter.txt
├─ run_single(..., tag=f"cN_{scenario}")   OR   run_sweep_line(..., file_prefix="cN_")
│  └─ (same compute chain as preview for each scenario type)
├─ _dashboard_from_single(...)             OR   _dashboard_from_sweep(...)
├─ print_dashboard(args, mode=f"COMMIT::cN", dash)
│  └─ dashboard_text(args, mode, dash)
├─ write_commit_dashboard_md(outdir, commit_id, dash_txt)
├─ update_index_html(outdir)               # regenerates index.html from commit artifacts
└─ Refresh UX after commit:
   ├─ build_args_catalog(devnet)
   ├─ capture_catalog_lines(catalog)
   ├─ build_sanity_panel_lines(devnet)
   └─ print_two_columns(left, right, ...)

---

### HTML/reporting branch: `update_index_html(outdir)`
update_index_html(outdir)
├─ (scans stress_out/ for commit artifacts: cN_*.csv, cN_dashboard.md)
├─ (internal) _read_commit_metrics(cN)      # parses dashboard + objective CSV fallback
└─ (generates index.html)
   ├─ embeds Commit Summary table
   ├─ embeds per-commit dashboards (from cN_dashboard.md)
   ├─ lists per-commit CSV artifacts (as text)
   └─ embeds right panel (static):
      ├─ SLD image: ../plots/devnet-sld.png
      └─ sanity panel text derived from build_sanity_panel_lines(devnet)

---

### Lower-level “compute primitives” (used by solve paths)
solve_with_duals(n, solver)
└─ n.optimize(solver_name=solver, assign_all_duals=True)

apply_load_multipliers(n, k_load_dict)
apply_corridor_reducers(n, k_line_dict)
apply_gen_marginal_cost_by_bus(n, mc_bus_dict, mode)
add_datacenter_site(n, ...)
collect_results(n)
write_outputs(outdir, tag, results)
parse_json_dict(s)

run_single(n0, args, tag)
└─ deepcopy(n0) → apply_* → optional add_datacenter_site → solve_with_duals → collect_results → write_outputs

run_sweep_line(n0, args, file_prefix)
└─ loops k_line values → apply_* → solve_with_duals → collect_results → writes sweep_line_summary.csv

---

# Reference
- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15-zeronode-ca/c/68d4302d-a6ec-8333-a0de-f3cfba0f2f26)  

- chatGPT: Zeronode.ca > PyPSA overview::  
  [PyPSA Ramp & Dev2](https://chatgpt.com/g/g-p-6857abd95a648191886783a41ba46a15-zeronode-ca/c/69680406-a7c8-8328-95d8-08889046f1b2)  

---

*Prepared collaboratively with ChatGPT-5, December 2025*  
