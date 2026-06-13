#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 ZeroNode
#
# Licensed under the Apache License, Version 2.0

# devnet_stress.py
#
# Interactive researcher shell for DevNet stress testing.
#
# Core solve/output/dashboard functions are delegated to:
#   lib/devnet_stress_lib.py
#
# ------------------------------------------------------------------------------

import os
import io
import sys
import json
import logging
import argparse
from datetime import datetime

import pypsa

# ------------------------------------------------------------------------------
#   Resolve paths next to this script
# ------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import devnet_stress_lib as dsl

TS = datetime.now().strftime("%Y%m%d-%H%M%S")

SECTION_SEPARATOR = dsl.SECTION_SEPARATOR
SUBSECTION_SEPARATOR = dsl.SUBSECTION_SEPARATOR

print(SECTION_SEPARATOR)
print("PyPSA DevNet Asymptote finder Script...\n")

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt):
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")


# ------------------------------------------------------------------------------
# Menu & Configuration Helpers
# - build_argparser()
# - build_args_catalog()
# - capture_catalog_lines()
# - print_two_columns()
# - prompt_custom_*()
# - configure_args_menu()
# Handles user interaction:
# - scenario selection
# - parameter configuration
# - custom overrides
# Drives interactive research workflow
# ------------------------------------------------------------------------------
def build_argparser(devnet_bld_path: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="baseline", choices=["baseline", "single", "sweep_line"])
    p.add_argument("--solver", default="highs")

    p.add_argument("--outdir", default=os.path.join(devnet_bld_path, "stress_out"))

    p.add_argument("--k_load", default="{}", help='JSON dict: {"BUS1": 1.2, "BUS3": 1.5}')
    p.add_argument("--k_line", default="{}", help='JSON dict: {"LINE1": 0.8, "LINE2": 0.6}')
    p.add_argument("--mc_bus", default="{}", help='JSON dict: {"BUS2": 50, "BUS5": 120}')
    p.add_argument("--mc_mode", default="set", choices=["set", "add"])

    p.add_argument(
        "--byog_mc",
        type=float,
        default=None,
        help="Override datacenter BYOG marginal cost (USD/MWh). Default=None uses loads.csv value",
    )

    p.add_argument("--line", default="", help="Line name for sweep_line scenario.")
    p.add_argument("--kmin", type=float, default=1.0)
    p.add_argument("--kmax", type=float, default=0.2)
    p.add_argument("--kstep", type=float, default=-0.1)
    p.add_argument("--dc_p_set", type=float, default=None, help="Override DC load (MW)")
    p.add_argument("--dc_p_nom", type=float, default=None, help="Override DC BYOG capacity (MW)")

    return p


def build_args_catalog(devnet: pypsa.Network) -> dict[str, list[str]]:
    bus0 = devnet.buses.index[0] if len(devnet.buses) else "BUS0"
    line0 = devnet.lines.index[0] if len(devnet.lines) else "LINE0"

    dc_csv = dsl.resolve_dc_csv_values(devnet)

    return {
        "scenario": ["baseline", "single", "sweep_line"],
        "mc_mode": ["set", "add"],
        "k_load": [
            "{}",
            json.dumps({bus0: 1.2}),
            json.dumps({bus0: 1.5}),
            json.dumps({b: 1.2 for b in devnet.buses.index}) if len(devnet.buses) else "{}",
            "__CUSTOM__",
        ],
        "k_line": [
            "{}",
            json.dumps({line0: 0.8}),
            json.dumps({line0: 0.6}),
            json.dumps({line0: 0.5}),
            "__CUSTOM__",
        ],
        "mc_bus": [
            "{}",
            json.dumps({bus0: 70}),
            json.dumps({bus0: 100}),
            "__CUSTOM__",
        ],
        "line": (list(devnet.lines.index[:6]) if len(devnet.lines) else [""]) + ["<manual>"],
        "kmin": ["1.0", "0.9", "0.8"],
        "kmax": ["0.5", "0.4", "0.3", "0.2"],
        "kstep": ["-0.1", "-0.05", "-0.02"],
        "byog_mc": [f"CSV Preset = {dc_csv['byog_mc']}", 45.0, 50.0, 60.0, "__CUSTOM__"],
        "dc_p_set": [f"CSV Preset = {dc_csv['p_set']}", 1000.0, 2000.0, "__CUSTOM__"],
        "dc_p_nom": [f"CSV Preset = {dc_csv['p_nom']}", 1000.0, 2000.0, "__CUSTOM__"],
    }


def capture_catalog_lines(catalog: dict[str, list[str]]) -> list[str]:
    out = []
    out.append(SECTION_SEPARATOR.rstrip("\n"))
    out.append("Configurable args + menu values (catalog)")
    out.append(SUBSECTION_SEPARATOR.rstrip("\n"))

    col1 = 12
    col2 = 92

    def clip(s: str, n: int) -> str:
        s = str(s)
        return s if len(s) <= n else s[: n - 3] + "..."

    header = f"{'arg':<{col1}} | {'menu values':<{col2}}"
    out.append(header)
    out.append("-" * len(header))

    for arg, opts in catalog.items():
        if arg in ("k_load", "k_line"):
            out.append(f"{arg:<{col1}} | {opts[0]}")
            for o in opts[1:]:
                out.append(f"{'':<{col1}} | {o}")
            continue

        joined = " ; ".join([clip(o, 60) for o in opts])
        out.append(f"{arg:<{col1}} | {clip(joined, col2)}")

    out.append(SECTION_SEPARATOR.rstrip("\n"))
    return out


def print_two_columns(left: list[str], right: list[str], left_width: int = 95, gap: int = 4) -> None:
    n = max(len(left), len(right))
    left_pad = " " * gap

    values_start = None
    for ln in left:
        if " | " in ln and ln.strip().startswith("arg"):
            values_start = ln.find(" | ") + 3
            break
    if values_start is None:
        values_start = 0

    def _wrap_with_indent(s: str, width: int, indent: int) -> list[str]:
        s = s or ""
        if len(s) <= width:
            return [s]
        first = s[:width]
        rest = s[width:]
        chunks = [first]
        while rest:
            chunk = (" " * indent) + rest[: max(0, width - indent)]
            rest = rest[max(0, width - indent):]
            chunks.append(chunk)
        return chunks

    for i in range(n):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""

        l_chunks = _wrap_with_indent(l, left_width, values_start)

        print(f"{l_chunks[0]:<{left_width}}{left_pad}{r}")

        for extra in l_chunks[1:]:
            print(f"{extra:<{left_width}}{left_pad}")


def prompt_custom_k_load(devnet: pypsa.Network) -> dict[str, float]:
    print("\nCustom k_load (per-bus load multiplier). Enter multiplier. Default=1.0\n")
    out = {}
    for b in devnet.buses.index:
        s = input(f"  {b} [default=1.0]: ").strip()
        if not s:
            continue
        try:
            v = float(s)
            if v <= 0:
                print("    Invalid; must be > 0. Skipped.")
                continue
            if v != 1.0:
                out[b] = v
        except Exception:
            print("    Invalid number. Skipped.")
    return out


def prompt_custom_k_line(devnet: pypsa.Network) -> dict[str, float]:
    print("\nCustom k_line (per-line derating). Enter derating factor. Default=1.0\n")
    out = {}
    for ln in devnet.lines.index:
        s = input(f"  {ln} [default=1.0]: ").strip()
        if not s:
            continue
        try:
            v = float(s)
            if v <= 0 or v > 1.0:
                print("    Invalid; must be in (0,1]. Skipped.")
                continue
            if v != 1.0:
                out[ln] = v
        except Exception:
            print("    Invalid number. Skipped.")
    return out


def prompt_custom_mc_bus(devnet: pypsa.Network) -> dict[str, float]:
    print("\nCustom mc_bus. Enter USD/MWh. Blank = no change.\n")
    out = {}
    for b in devnet.buses.index:
        s = input(f"  {b} [blank=no change]: ").strip()
        if not s:
            continue
        try:
            out[b] = float(s)
        except Exception:
            print("    Invalid number. Skipped.")
    return out


def _pick_from_menu(title: str, options: list[str], default_idx: int = 0) -> str:
    opt_range = ",".join(str(i) for i in range(1, len(options) + 1))
    prompt = f"{title}[{opt_range}] <Enter selection> (default={default_idx + 1}): "
    s = input(prompt).strip()

    if not s:
        return options[default_idx]

    try:
        k = int(s)
        if 1 <= k <= len(options):
            return options[k - 1]
    except Exception:
        pass

    print("Invalid selection; using default.")
    return options[default_idx]


def configure_args_menu(devnet: pypsa.Network, args: argparse.Namespace) -> argparse.Namespace:
    print("\nSelection arg configuration values:\n")

    catalog = build_args_catalog(devnet)

    opts = catalog["scenario"]
    args.scenario = _pick_from_menu(
        "Scenario",
        opts,
        default_idx=opts.index(args.scenario) if args.scenario in opts else 0,
    )

    opts = catalog["mc_mode"]
    args.mc_mode = _pick_from_menu(
        "Generator marginal cost mode (mc_mode)",
        opts,
        default_idx=opts.index(args.mc_mode) if args.mc_mode in opts else 0,
    )

    opts = catalog["k_load"]
    sel_load = _pick_from_menu(
        "Per-bus load multiplier preset (k_load)",
        opts,
        default_idx=opts.index(args.k_load) if args.k_load in opts else 0,
    )

    if sel_load == "__CUSTOM__":
        custom_load = prompt_custom_k_load(devnet)
        args.k_load = json.dumps(custom_load) if custom_load else "{}"
        if custom_load:
            print("\nCustom k_load set:")
            for b, v in custom_load.items():
                print(f"  {b}: {v}")
    else:
        args.k_load = sel_load

    opts = catalog["k_line"]
    sel = _pick_from_menu(
        "Per-line capacity reducer preset (k_line)",
        opts,
        default_idx=opts.index(args.k_line) if args.k_line in opts else 0,
    )

    if sel == "__CUSTOM__":
        custom = prompt_custom_k_line(devnet)
        args.k_line = json.dumps(custom) if custom else "{}"
        if custom:
            print("\nCustom k_line set:")
            for ln, v in custom.items():
                print(f"  {ln}: {v}")
    else:
        args.k_line = sel

    opts = catalog["mc_bus"]
    sel_mc = _pick_from_menu(
        "Per-bus generator marginal cost preset (mc_bus)",
        opts,
        default_idx=opts.index(args.mc_bus) if args.mc_bus in opts else 0,
    )

    if sel_mc == "__CUSTOM__":
        custom_mc = prompt_custom_mc_bus(devnet)
        args.mc_bus = json.dumps(custom_mc) if custom_mc else "{}"
        if custom_mc:
            print("\nCustom mc_bus set:")
            for b, v in custom_mc.items():
                print(f"  {b}: {v}")
    else:
        args.mc_bus = sel_mc

    opts = catalog.get("byog_mc", ["CSV_PRESET"])
    choice = _pick_from_menu(
        "Datacenter BYOG marginal cost override (CSV Preset = use loads.csv)",
        opts,
        default_idx=0,
    )
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.byog_mc = None
    elif choice == "__CUSTOM__":
        args.byog_mc = float(input("Enter custom BYOG MC (USD/MWh): ").strip())
    else:
        args.byog_mc = float(choice)

    opts = catalog.get("dc_p_set", ["CSV Preset"])
    choice = _pick_from_menu("Datacenter load override (MW)", opts, default_idx=0)
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.dc_p_set = None
    elif choice == "__CUSTOM__":
        args.dc_p_set = float(input("Enter DC load (MW): ").strip())
    else:
        args.dc_p_set = float(choice)

    opts = catalog.get("dc_p_nom", ["CSV Preset"])
    choice = _pick_from_menu("Datacenter BYOG capacity override (MW)", opts, default_idx=0)
    if isinstance(choice, str) and choice.startswith("CSV Preset"):
        args.dc_p_nom = None
    elif choice == "__CUSTOM__":
        args.dc_p_nom = float(input("Enter BYOG capacity (MW): ").strip())
    else:
        args.dc_p_nom = float(choice)

    if args.scenario == "sweep_line":
        opts = catalog["line"]
        chosen = _pick_from_menu("Sweep target line (line)", opts, default_idx=0)
        if chosen == "<manual>":
            args.line = input("line <manual>: ").strip()
        else:
            args.line = chosen

        opts = catalog["kmin"]
        args.kmin = float(_pick_from_menu("kmin", opts, default_idx=0))

        opts = catalog["kmax"]
        args.kmax = float(_pick_from_menu("kmax", opts, default_idx=len(opts) - 1))

        opts = catalog["kstep"]
        args.kstep = float(_pick_from_menu("kstep", opts, default_idx=0))

    else:
        args.line = ""
        args.kmin, args.kmax, args.kstep = 1.0, 0.2, -0.1

    ordered_keys = [
        "scenario",
        "mc_mode",
        "k_load",
        "k_line",
        "mc_bus",
        "line",
        "kmin",
        "kmax",
        "kstep",
        "byog_mc",
        "dc_p_set",
        "dc_p_nom",
    ]

    print("\nASR-DBG::Configured args (menu):")
    for k in ordered_keys:
        if hasattr(args, k):
            print(f"\t\t{k:12s} = {getattr(args, k)}")

    input("\nARGS OK? Press Enter to run...\n")
    return args


# ------------------------------------------------------------------------------
#   Dashboard print wrapper
# ------------------------------------------------------------------------------
def print_dashboard(args: argparse.Namespace, mode: str, dash: dict, devnet: pypsa.Network) -> None:
    print(dsl.dashboard_text(args, mode, dash, devnet), end="")


# ------------------------------------------------------------------------------
# Main Execution & Research Loop
# - researcher_loop()
# - main()
# Orchestrates workflow:
# - load network
# - configure scenarios
# - preview runs
# - commit results
# - update dashboards
# Entry point for DevNet stress testing framework
# ------------------------------------------------------------------------------
def researcher_loop(devnet: pypsa.Network, args: argparse.Namespace, catalog: dict[str, list[str]]) -> None:
    """
    R: reselect args + preview
    C: commit current args set
    Q: quit (warn if nothing committed)
    """
    last_committed = False

    while True:
        args = configure_args_menu(devnet, args)

        prev = dsl.run_preview(devnet, args, DEVNET_NAME)

        if prev["kind"] == "single":
            dash = dsl._dashboard_from_single(prev["res"])
            print_dashboard(args, "PREVIEW", dash, devnet)

        elif prev["kind"] == "sweep":
            dash = dsl._dashboard_from_sweep(prev["df"])
            print_dashboard(args, "PREVIEW", dash, devnet)

        cmd = input("R=reselect  C=commit  Q=quit : ").strip().lower()

        if cmd == "r":
            os.system("cls" if os.name == "nt" else "clear")
            catalog = build_args_catalog(devnet)
            left = capture_catalog_lines(catalog)
            right = dsl.build_sanity_panel_lines(devnet)
            print_two_columns(left, right, left_width=95, gap=4)
            continue

        if cmd == "c":
            result = dsl.run_commit(devnet, args, DEVNET_NAME)

            print(result["dashboard_text"], end="")
            print(f"Configuration output committed @:\n\t{args.outdir}\n")
            print(f"Commit id:\t{result['commit_id']}\n")
            print(f"HTML report updated @:\n\t{result['index_path']}\n")

            os.system("cls" if os.name == "nt" else "clear")
            catalog = build_args_catalog(devnet)
            left = capture_catalog_lines(catalog)
            right = dsl.build_sanity_panel_lines(devnet)
            print_two_columns(left, right, left_width=95, gap=4)

            last_committed = True
            continue

        if cmd == "q":
            if not last_committed:
                if not confirm("No COMMIT recorded. Quit anyway?"):
                    continue
            return

        print("Invalid input. Use R, C, or Q.")


def main():
    args = build_argparser(DEVNET_BLD_PATH).parse_args()

    catalog = build_args_catalog(devnet)
    left = capture_catalog_lines(catalog)
    right = dsl.build_sanity_panel_lines(devnet)
    print_two_columns(left, right, left_width=95, gap=4)

    dsl.update_index_html(args.outdir, devnet, DEVNET_NAME)

    input("Press Enter to start arg configuration...\n")

    researcher_loop(devnet, args, catalog)


# ------------------------------------------------------------------------------
#   Select DevNet build
# ------------------------------------------------------------------------------
print("Select DevNet build:")
print("  1) devnet-sld (baseline)")
print("  2) devnetDC-sld (with Datacenter BYOG)")

choice = input("Enter choice [1]: ").strip()

if choice == "2":
    DEVNET_NAME = "devnetDC-sld"
else:
    DEVNET_NAME = "devnet-sld"

print(f"ASR-DBG::Using DEVNET_NAME::\n\t{DEVNET_NAME}\n")

# ------------------------------------------------------------------------------
#   Define DevNet Log & CSV/Excel paths
# ------------------------------------------------------------------------------
DEVNET_BLD_PATH = os.path.join(SCRIPT_DIR, DEVNET_NAME)
DEVNET_BLD_DIR = os.path.basename(DEVNET_BLD_PATH)

print("ASR-DBG::DEVNET_BLD_PATH::\n\t{0}\n".format(DEVNET_BLD_PATH))

if os.path.isdir(DEVNET_BLD_PATH):
    print(f"ASR-DBG: Found DevNet CSV build folder:\n\t{DEVNET_BLD_DIR}")
    if not confirm(f"ASR-DBG: Process existing {DEVNET_BLD_DIR}.\n"):
        print("Manually remove folder and re-run devnet_sld.py. Exiting...")
        print(SECTION_SEPARATOR)
        sys.exit(0)
    else:
        print(f"ASR-DBG: Keeping existing {DEVNET_BLD_PATH}.\n")
else:
    print(f"ASR-DBG: DevNet build folder not found:\n\t{DEVNET_BLD_PATH}\n")
    print("Please run devnet_sld.py to create/export the DevNet CSV folder first. Exiting...")
    print(SECTION_SEPARATOR)
    sys.exit(0)

PLOT_PATH = os.path.join(DEVNET_BLD_PATH, "plots")
PLOT_DIR = os.path.basename(PLOT_PATH)

print("ASR-DBG::PLOT_PATH::\n\t{0}\n".format(PLOT_PATH))

if not os.path.exists(PLOT_PATH):
    os.makedirs(PLOT_PATH)
elif os.path.isdir(PLOT_PATH):
    print(f"ASR-DBG: Found existing plot folder:\n\t{PLOT_DIR}")
    if not confirm(f"ASR-DBG: Keep existing {PLOT_DIR}.\n"):
        print("Manually CLEANUP[REMOVE & RECREATE] folder and re-run script. Exiting...")
        print(SECTION_SEPARATOR)
        sys.exit(0)
    else:
        print(f"ASR-DBG: Keeping existing {PLOT_PATH}.\n")

LOG_PATH = os.path.join(DEVNET_BLD_PATH, "logs")
LOG_DIR = os.path.basename(LOG_PATH)

print("ASR-DBG::LOG_PATH::\n\t{0}\n".format(LOG_PATH))

if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

LOG_NAME = f"{DEVNET_NAME}_{TS}.log"
LOG_PATH = os.path.join(LOG_PATH, LOG_NAME)

print("ASR-DBG::Log file::\n\t{0}\n".format(LOG_NAME))

# ------------------------------------------------------------------------------
#   Logging: Single-writer log
# ------------------------------------------------------------------------------
_log_file_for_prints = open(LOG_PATH, "w", encoding="utf-8")


class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = list(streams)

    def write(self, s):
        for st in list(self.streams):
            try:
                st.write(s)
                st.flush()
            except Exception:
                try:
                    self.streams.remove(st)
                except Exception:
                    pass
        return len(s)

    def flush(self):
        for st in list(self.streams):
            try:
                st.flush()
            except Exception:
                try:
                    self.streams.remove(st)
                except Exception:
                    pass


_orig_stdout, _orig_stderr = sys.stdout, sys.stderr

sys.stdout = Tee(_orig_stdout, _log_file_for_prints)
sys.stderr = Tee(_orig_stderr, _log_file_for_prints)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

print(f"Saving logs to: {LOG_NAME}")

# ------------------------------------------------------------------------------
#   Load DevNet base network: Exported CSVs from devnet_sld.py
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("Load DevNet base network:: Exported CSVs from devnet_sld.py…")

devnet = pypsa.Network(DEVNET_BLD_PATH)

print(f"  Loaded DevNet network from CSVs at:\n\t{DEVNET_BLD_PATH}\n")
print(f"  Network summary:\n{devnet}")

# ------------------------------------------------------------------------------
#   Sanity Report
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Proceed with DevNet Sanity Report\nPress Enter to confirm...")

print("DevNet Sanity Report (CSV-based network)...\n")

print("devenet.generators:\n", devnet.generators[["bus", "p_nom", "marginal_cost"]])
print("\ndevnet.snapshots:\n", devnet.snapshots)

total_gen = float(devnet.generators["p_nom"].sum()) if len(devnet.generators) else 0.0
total_load = float(devnet.loads["p_set"].sum()) if len(devnet.loads) else 0.0

print("\nSystem-wide adequacy check:")
print(f"  Σ p_nom (generation) = {total_gen:,.1f} MW")
print(f"  Σ p_set (load)       = {total_load:,.1f} MW")
print(f"  Adequate?            = {'YES' if total_gen >= total_load else 'NO'}\n")

gen_by_bus = devnet.generators.groupby("bus")["p_nom"].sum() if len(devnet.generators) else None
load_by_bus = devnet.loads.groupby("bus")["p_set"].sum() if len(devnet.loads) else None

print("Per-bus balance (local surplus/deficit):")
print("  surplus = Σ p_nom(gen@bus) - Σ p_set(load@bus)\n")

rows = []
for b in devnet.buses.index:
    g = float(gen_by_bus.get(b, 0.0)) if gen_by_bus is not None else 0.0
    l = float(load_by_bus.get(b, 0.0)) if load_by_bus is not None else 0.0
    rows.append((b, g, l, g - l))

rows_sorted = sorted(rows, key=lambda x: x[3])

for b, g, l, s in rows_sorted:
    status = "EXPORT" if s > 0 else ("BAL" if s == 0 else "IMPORT")
    print(f"  {b:10s}  gen={g:8.1f}  load={l:8.1f}  surplus={s:8.1f}  [{status}]")

print("\n" + SUBSECTION_SEPARATOR)

print("Corridor deliverability check (smallest s_nom lines):\n")

if len(devnet.lines):
    cols = [c for c in ["bus0", "bus1", "s_nom"] if c in devnet.lines.columns]
    bottlenecks = devnet.lines[cols].copy()
    bottlenecks = bottlenecks.sort_values("s_nom", ascending=True)

    N = min(6, len(bottlenecks))
    for line_name, r in bottlenecks.head(N).iterrows():
        print(f"  {line_name:22s}  {r['bus0']:10s} -> {r['bus1']:10s}   s_nom={float(r['s_nom']):,.1f}")
else:
    print("  No lines found in network.")

# ------------------------------------------------------------------------------
#   Invoke DevNet researcher loop
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Proceed with DevNet Asymptote Finder\nPress Enter to confirm...")

print("DevNet Asymptote Finder (CSV-based network)...\n")

if __name__ == "__main__":
    main()

# ------------------------------------------------------------------------------
#   Tear down
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
input("Tear down logging redirection\nPress Enter to confirm...")

sys.stdout = _orig_stdout
sys.stderr = _orig_stderr

_log_file_for_prints.close()

# ------------------------------------------------------------------------------
# END OF devnet_stress.py
# ------------------------------------------------------------------------------
