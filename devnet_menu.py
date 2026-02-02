"""
devnet_menu.py

Purpose
  Command-line wrapper for the Datacenter BYOG DoE workflow. Presents a simple menu
  that runs the current DevNet scripts in the correct order.

What it does
  - Option 1 runs devnet_sld.py to build the USA-lite 6-bus DevNet SLD and export CSVs.
  - Option 2 runs devnet_doe.py to load the exported CSV DevNet and run sanity + solve checks.
  - Provides an exit option and keeps the console tidy between runs.

Outputs
  - Delegates outputs to the underlying scripts (CSV folders, plots, logs).
"""

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
    print("Tip: If a plot script errors on missing devnet_plots.xlsx, run devnet_stress.py first.\n")
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
        "  1) Build SLD once (devnet_sld.py)\n"
        "     - Creates ./devnet-sld/ with CSVs + plots/ + logs/\n"
        "  2) Run DoE sanity once (devnet_doe.py)\n"
        "     - Validates the exported DevNet and confirms baseline solve behavior\n"
        "  3) Stress / Asymptote finder (devnet_stress.py)\n"
        "     - Run as many times as needed\n"
        "     - Interactive commits: c1_, c2_, ... written under ./devnet-sld/stress_out/\n"
        "\nImportant:\n"
        "  - Do NOT re-run (1) or (2) unless you intentionally want to rebuild/overwrite the base DevNet.\n"
        "  - Use (3) for iterative research runs.\n"
        "\nVisualization:\n"
        "  - Open the report in a browser:\n"
        "      ./devnet-sld/stress_out/index.html\n"
        "\nVisualization (plots):\n"
        "  4) Load vs system metrics (devnet_load_plot.py)\n"
        "     - Produces a 4-panel PNG: objective, LMP spread, max line loading, near-bind count\n"
        "     - Use this to see feasibility boundaries + linear cost scaling with load\n"
        "\n"
        "  5) MC table + LMP spread heatmap (devnet_lmp_plot.py)\n"
        "     - Left: bus mc perturbation table per case\n"
        "     - Middle: LMP spread heatmap aligned to cases\n"
        "     - Right: metrics panel (max_loading_pu, near_bind_ct, objective sparkline, top congested lines)\n"
        "     - Use this to visually link mc perturbations → congestion → LMP separation\n"
        "\n"
        "  6) Line deration vs system metrics (devnet_line_plot.py)\n"
        "     - Produces a 4-panel PNG: objective, LMP spread, max line loading, near-bind count\n"
        "     - X-axis is k_line (1.0 → 0.1) for quick line-deration sensitivity scans\n"
        "\n"
        "  Notes:\n"
        "   - (4) and (5) expect the stress workbook to exist (devnet_plots.xlsx).\n"
        "   - If plots fail due to missing workbook/sheet, run option (3) first.\n"
        "\n(Analysis module will be added later.)\n"
    )

def print_menu():
    print("Select an option:")
    print("  1) Build / export SLD network (devnet_sld.py)")
    print("  2) Load network / sanity checks (devnet_doe.py)")
    print("  3) Find Network Asymptotes (devnet_stress.py)")
    print("  4) Plot: Load vs system metrics (devnet_load_plot.py)")
    print("  5) Plot: MC table + LMP spread heatmap + metrics panel (devnet_lmp_plot.py)")
    print("  6) Plot: Line deration vs system metrics (devnet_line_plot.py)")
    print("  0) Exit")

def main():
    while True:
        clear_console()
        print_header()
        print_menu()

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            rc = run_script("devnet_sld.py")
            input(f"\nFinished devnet_sld.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "2":
            rc = run_script("devnet_doe.py")
            input(f"\nFinished devnet_doe.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "3":
            rc = run_script("devnet_stress.py")
            input(f"\nFinished devnet_stress.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "4":
            rc = run_script("devnet_load_plot.py")
            input(f"\nFinished devnet_load_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "5":
            rc = run_script("devnet_lmp_plot.py")
            input(f"\nFinished devnet_lmp_plot.py (exit code {rc}). Press Enter to return to menu...")
        elif choice == "6":
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
