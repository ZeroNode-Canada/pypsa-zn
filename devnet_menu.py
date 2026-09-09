#!/usr/bin/env python3

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

# devnet_menu.py
# 
# Purpose
#   Command-line wrapper for the Datacenter BYOG DoE workflow. Presents a simple menu
#   that runs the current DevNet scripts in the correct order.
# 
# What it does
#   - Option 1 runs devnet_cfg.py to generate user-editable DevNet CSV templates.
#   - Option 2 runs devnet_sld.py to build the baseline USA-lite 6-bus DevNet SLD from CSV config.
#   - Option 3 runs devnetDC_sld.py to build the Datacenter BYOG DevNet from CSV config.
#   - Option 4 runs devnet_doe.py to load exported CSV DevNet and run sanity + solve checks.
#   - Option 5 runs devnet_stress.py for iterative stress testing and commit dashboards.
#   - Options 6–8 run plotting helpers.
#   - Provides an exit option and keeps the console tidy between runs.
# 
# Outputs
#   - Delegates outputs to the underlying scripts:
#     - devnet_config/*.csv
#     - exported PyPSA CSV folders
#     - plots/
#     - logs/
#     - stress_out/index.html

# Run: devnet_menu.py
# ------------------------------------------------------------------------------


# Run: devnet_menu.py

import os
import sys
import subprocess
from datetime import datetime

SECTION_SEPARATOR = "=" * 80

# ------------------------------------------------------------------------------
# script_path()
# Returns the absolute path to a DevNet script located alongside devnet_menu.py.
#
# Ensures:
# - Menu-launched scripts resolve independent of the current working directory.
# - All DevNet workflow scripts are launched from a consistent base path.
# ------------------------------------------------------------------------------
def script_path(name: str) -> str:
    """Return absolute path to a sibling script in the same folder as this file."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)

# ------------------------------------------------------------------------------
# run_script()
# Launches the selected DevNet workflow script using the current Python
# interpreter and returns its process exit code.
#
# CTRL-C terminates the active child process cleanly and propagates the
# interrupt to devnet_menu.py for graceful workflow termination.
# ------------------------------------------------------------------------------
def run_script(script_name: str) -> int:
    """Run a Python script as a subprocess using the current interpreter."""
    path = script_path(script_name)

    if not os.path.exists(path):
        print(f"\nERROR: Cannot find {script_name} at:\n  {path}\n")
        return 1

    print(f"\n{SECTION_SEPARATOR}")
    print(f"Running: {script_name}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{SECTION_SEPARATOR}\n")

    print(
        "Tip: Run devnet_cfg.py first to create/edit CSV inputs. "
        "Run devnet_stress.py before plot scripts.\n"
    )

    # ------------------------------------------------------------------
    # Run child script in its own process group.
    #
    # This keeps CTRL-C handling with devnet_menu.py so the active child
    # process can be terminated cleanly without a Python traceback dump.
    # ------------------------------------------------------------------
    popen_kwargs = {}

    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        [sys.executable, path],
        **popen_kwargs,
    )

    try:
        return process.wait()

    except KeyboardInterrupt:

        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        raise

# ------------------------------------------------------------------------------
# clear_console()
# Clears the terminal before redisplaying the DevNet workflow menu.
# ------------------------------------------------------------------------------
def clear_console():
    os.system("cls" if os.name == "nt" else "clear")

# ------------------------------------------------------------------------------
# print_header()
# Displays the DevNet workflow description, execution sequence, and usage notes.
# ------------------------------------------------------------------------------
def print_header():
    print(SECTION_SEPARATOR)
    print("DeltaE / PhD – Datacenter BYOG DoE Workflow (PyPSA)")
    print(SECTION_SEPARATOR)
    print(
        "\nWorkflow (intended use):\n"
        "  1) Generate DevNet CSV templates (devnet_cfg.py)\n"
        "     - Creates ./devnet_config/*.csv user-editable inputs\n"
        "     - Edit these CSVs before building SLDs\n"
        "\n"
        "  2) Build DevNet SLD (baseline network) from CSV config (devnet_sld.py)\n"
        "     - Creates the 6-bus USA-lite DevNet baseline + CSV export + plots/ + logs/\n"
        "\n"
        "  3) Datacenter case -- choose the engine route\n"
        "     - PyPSA route: build the 6-bus DevNet SLD with Datacenter BYOG\n"
        "       from CSV config (devnetDC_sld.py). Uses devnet_config/devnet_dc.csv\n"
        "       for datacenter bus, load, BYOG capacity and BYOG MC.\n"
        "     - PSO route: the ERCOT Texas7k public case (6717 buses), driven via\n"
        "       aimmspy against your own AIMMS install and license. PSO-only: it\n"
        "       does not build or touch a PyPSA network. Configure pso.local.toml\n"
        "       first (see pso.local.toml.example).\n"
        "\n"
        "  4) Run DoE sanity once (devnet_doe.py)\n"
        "     - Validates the exported DevNet and confirms baseline solve behavior\n"
        "\n"
        "  5) Stress / Asymptote finder (devnet_stress.py)\n"
        "     - Run as many times as needed\n"
        "     - Interactive commits: c1_, c2_, ... written under selected DevNet stress_out/\n"
        "\nImportant:\n"
        "  - Run (1) first if ./devnet_config/*.csv does not exist.\n"
        "  - Edit ./devnet_config/*.csv before running (2) or (3).\n"
        "  - Do NOT re-run (2) or (3) unless you intentionally want to rebuild a base DevNet.\n"
        "  - Use (4) and (5) for iterative research runs.\n"
        "\nVisualization:\n"
        "  - Open the stress report in a browser:\n"
        "      ./<selected-devnet>/stress_out/index.html\n"
        "\n"
        "\nVisualization (plots):\n"
        "  6) Load vs system metrics (devnet_load_plot.py)\n"
        "     - Produces a 4-panel PNG: objective, LMP spread, max line loading, near-bind count\n"
        "\n"
        "  7) MC table + LMP spread heatmap (devnet_lmp_plot.py)\n"
        "     - Links mc perturbations → congestion → LMP separation\n"
        "\n"
        "  8) Line deration vs system metrics (devnet_line_plot.py)\n"
        "     - X-axis is k_line for line-deration sensitivity scans\n"
        "\n"
        "  Notes:\n"
        "   - (6), (7), and (8) expect the stress workbook/report inputs to exist.\n"
        "   - If plots fail due to missing workbook/sheet, run option (5) first.\n"
        "\n"
        "\n(Analysis module will be added later.)\n"
    )

# ------------------------------------------------------------------------------
# print_menu()
# Displays the available DevNet build, stress-test, and plotting operations.
# ------------------------------------------------------------------------------
def print_menu():
    print("Select an option:")
    print("  1) Generate DevNet CSV templates (devnet_cfg.py)")
    print("  2) Build DevNet SLD (baseline network from CSV config)")
    print("  3) Datacenter case: PyPSA DevNet 6-bus or PSO ERCOT Texas7k")
    print("  4) Load network / sanity checks (devnet_doe.py)")
    print("  5) Find Network Asymptotes (devnet_stress.py)")
    print("  6) Plot: Load vs system metrics (devnet_load_plot.py)")
    print("  7) Plot: MC table + LMP spread heatmap + metrics panel (devnet_lmp_plot.py)")
    print("  8) Plot: Line deration vs system metrics (devnet_line_plot.py)")
    print("  9) Plot: DevNet 8760 objective/load/feasibility (devnet_sys_plot.py)")
    print(" 10) Plot: PJM_NE 8760 LMP chronology (devnet_pjm_ne_lmp_plot.py)")
    print(" 11) Plot: Journal publication figures (devnet_pub_figs.py)")
    print("  0) Exit")

# ------------------------------------------------------------------------------
# pick_submenu()
# Prompts for one of a numbered list of choices; returns the 1-based index, or
# 0 to go back. Re-asks on anything invalid; a bare Enter takes the default.
# ------------------------------------------------------------------------------
def pick_submenu(title: str, choices: list[str], default: int = 1) -> int:
    while True:
        print(f"\n{title}")

        for i, label in enumerate(choices, start=1):
            print(f"  {i}) {label}")

        print("  0) Back to main menu")

        raw = input(f"\nEnter choice [{default}]: ").strip()

        if not raw:
            return default

        if raw.isdigit() and int(raw) <= len(choices):
            return int(raw)

        print("\nInvalid choice.")

# ------------------------------------------------------------------------------
# run_datacenter_case()
# Option 3: pick the engine route for a datacenter case, then dispatch.
#
# PyPSA route -> devnetDC_sld.py, the 6-bus DevNet SLD with Datacenter BYOG.
# PSO route   -> the ERCOT Texas7k public case (ercot7k_pso.py). PSO-only: no
#                PyPSA network is built. The stress matrix is not part of this
#                build and says so rather than being hidden.
# ------------------------------------------------------------------------------
def run_datacenter_case() -> None:
    route = pick_submenu(
        "Datacenter case -- select engine route:",
        [
            "PyPSA: DevNet 6-bus SLD with Datacenter BYOG (devnetDC_sld.py)",
            "PSO:   ERCOT Texas7k public case (6717 buses)",
        ],
    )

    if route == 1:
        rc = run_script("devnetDC_sld.py")
        input(f"\nFinished devnetDC_sld.py (exit code {rc}). Press Enter to return to menu...")
        return

    if route != 2:
        return

    what = pick_submenu(
        "PSO route -- ERCOT Texas7k:",
        [
            "Run the base case, full cycle (ercot7k_pso.py)",
            "Run the stress matrix  [NOT YET AVAILABLE]",
        ],
    )

    if what == 1:
        rc = run_script("ercot7k_pso.py")
        input(f"\nFinished ercot7k_pso.py (exit code {rc}). Press Enter to return to menu...")
    elif what == 2:
        print("\nASR-DBG: The Texas7k stress matrix is not part of this build.")
        print("It arrives with the case-builder work; until then use the base case.\n")
        input("Press Enter to return to menu...")

# ------------------------------------------------------------------------------
# main()
# Runs the interactive DevNet workflow menu and dispatches the selected script.
#
# Continues returning to the menu after each completed operation until the user
# explicitly exits or terminates the workflow with CTRL-C.
# ------------------------------------------------------------------------------
def main():
    while True:
        clear_console()
        print_header()
        print_menu()

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            rc = run_script("devnet_cfg.py")
            input(f"\nFinished devnet_cfg.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "2":
            rc = run_script("devnet_sld.py")
            input(f"\nFinished devnet_sld.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "3":
            run_datacenter_case()
        elif choice == "4":
            rc = run_script("devnet_doe.py")
            input(f"\nFinished devnet_doe.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "5":
            rc = run_script("devnet_stress.py")
            input(f"\nFinished devnet_stress.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "6":
            rc = run_script("devnet_load_plot.py")
            input(f"\nFinished devnet_load_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "7":
            rc = run_script("devnet_lmp_plot.py")
            input(f"\nFinished devnet_lmp_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "8":
            rc = run_script("devnet_line_plot.py")
            input(f"\nFinished devnet_line_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "9":
            rc = run_script("devnet_sys_plot.py")
            input(f"\nFinished devnet_sys_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "10":
            rc = run_script("devnet_pjm_ne_lmp_plot.py")
            input(f"\nFinished devnet_pjm_ne_lmp_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "11":
            rc = run_script("devnet_pub_figs.py")
            input(f"\nFinished devnet_pub_figs.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "0":
            print("\nExiting devnet_menu.py\n")
            return 0
        else:
            input("\nInvalid choice. Press Enter to try again...")

if __name__ == "__main__":
    try:
        raise SystemExit(main())

    except KeyboardInterrupt:
        print("\n\nUser terminated. Exiting DevNet workflow.\n")
        raise SystemExit(130)
    
# ------------------------------------------------------------------------------
# END OF devnet_menu.py
# ------------------------------------------------------------------------------
