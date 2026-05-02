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

def script_path(name: str) -> str:
    """Return absolute path to a sibling script in the same folder as this file."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)

def run_script(script_name: str) -> int:
    """Run a python script as a subprocess using the current interpreter."""
    path = script_path(script_name)
    if not os.path.exists(path):
        print(f"\nERROR: Cannot find {script_name} at:\n  {path}\n")
        return 1

    print(f"\n{SECTION_SEPARATOR}")
    print(f"Running: {script_name}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{SECTION_SEPARATOR}\n")

    # Run with the same Python interpreter that's running the menu.
    # This preserves your current environment (PyPSA, matplotlib, etc.)
    print("Tip: Run devnet_cfg.py first to create/edit CSV inputs. Run devnet_stress.py before plot scripts.\n")
    result = subprocess.run([sys.executable, path])
    return result.returncode

def clear_console():
    os.system("cls" if os.name == "nt" else "clear")

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
        "  3) Build DevNet SLD with Datacenter BYOG from CSV config (devnetDC_sld.py)\n"
        "     - Uses devnet_config/devnet_dc.csv for datacenter bus, load, BYOG capacity, BYOG MC\n"
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
        "\n(Analysis module will be added later.)\n"
    )

def print_menu():
    print("Select an option:")
    print("  1) Generate DevNet CSV templates (devnet_cfg.py)")
    print("  2) Build DevNet SLD (baseline network from CSV config)")
    print("  3) Build DevNet SLD with Datacenter BYOG (from CSV config)")
    print("  4) Load network / sanity checks (devnet_doe.py)")
    print("  5) Find Network Asymptotes (devnet_stress.py)")
    print("  6) Plot: Load vs system metrics (devnet_load_plot.py)")
    print("  7) Plot: MC table + LMP spread heatmap + metrics panel (devnet_lmp_plot.py)")
    print("  8) Plot: Line deration vs system metrics (devnet_line_plot.py)")
    print("  0) Exit")

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
            rc = run_script("devnetDC_sld.py")
            input(f"\nFinished devnetDC_sld.py (exit code {rc}). Press Enter to return to menu...")
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
        elif choice == "0":
            print("\nExiting devnet_menu.py\n")
            return 0
        else:
            input("\nInvalid choice. Press Enter to try again...")

if __name__ == "__main__":
    raise SystemExit(main())
# End of devnet_menu.py
