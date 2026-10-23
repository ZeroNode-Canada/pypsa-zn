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
#   Unified CLI for ZeroNode's PyPSA DevNet and Polaris PSO ERCOT Texas7k
#   datacenter modeling and experimental workflows.
#
# What it does
#   - Generates and manages PyPSA DevNet configuration CSVs.
#   - Builds baseline 6-bus DevNet and datacenter BYOG cases.
#   - Runs DevNet sanity checks, stress experiments, and plotting workflows.
#   - Provides a dedicated Polaris PSO ERCOT Texas7k route:
#       * Run baseline ERCOT7k optimization through AIMMS/CPLEX.
#       * Screen and rank nodes by LMP separation and stress duration.
#       * Generate standalone interactive geographic maps of ranked nodes.
#       * Select screening filters and geographic reference CSVs.
#       * Initialize and review datacenter/BYOG and stress configuration.
#       * Build derived cases without modifying the baseline.
#       * Select and optimize derived ERCOT7k cases.
#       * Compare baseline and derived results (pending integration).
#   - Validates PSO/AIMMS dependencies before optimization.
#   - Uses environment overrides for PSO case selection.
#   - Supports interactive navigation, confirmations, and CTRL-C handling.
#
# Inputs
#   - devnet_config/*.csv
#   - ercot7k/texas7k*.csv
#   - ercot7k_config/*.csv
#   - ercot7k_geo/texas7k_bus_coords.csv
#   - ercot7k-runs/<run>/results/*.csv
#   - pso.local.toml (machine-specific PSO configuration)
#
# Outputs
#   - Delegates output generation to the selected scripts:
#       * devnet_config/, plots/, logs/, stress_out/
#       * ercot7k_config/, ercot7k-derived/, ercot7k-runs/
#       * ercot7k-runs/<run>/ercot7k_node_ranked.csv
#       * geo-plots/ercot7k_node_map.html
#   - Does not directly modify model inputs or optimization results.
#
# Usage
#   python devnet_menu.py
#
#   Main menu option 3:
#     1) PyPSA DevNet 6-bus datacenter BYOG
#     2) PSO ERCOT Texas7k
#
#   PSO submenu:
#     1) Run Baseline
#     2) Screen / Rank ERCOT7k Nodes
#     3) Plot Ranked ERCOT7k Nodes
#     4) Configure Derived Case
#     5) Build Derived Case
#     6) Run Derived Case
#     7) Compare Baseline vs Derived Case [PENDING]
#
# Usage
#   python devnet_menu.py
#
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Standard imports
# ------------------------------------------------------------------------------
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
# Global defines
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
# Executes a sibling Python script with optional CLI arguments and environment
# overrides. Preserves CTRL-C handling and returns the child exit code.
# ------------------------------------------------------------------------------
def run_script(
    script_name: str,
    args: list[str] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> int:

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

    child_env = os.environ.copy()

    if env_overrides:
        child_env.update(env_overrides)

    process = subprocess.Popen(
        [sys.executable, path] + (args or []),
        env=child_env,
        cwd=os.path.dirname(path),
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
# print_menu()
# Displays the main PyPSA DevNet operations and datacenter engine selection.
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
        "     - PSO route: ERCOT Texas7k public case (6717 buses), using\n"
        "       Polaris PSO / AIMMS / CPLEX (separate license required).\n"
        "       Run baseline optimization, screen/rank candidate nodes,\n"
        "       configure datacenter BYOG/stress parameters, build derived\n"
        "       cases, and optimize selected scenarios.\n"
        "       PSO configuration: pso.local.toml (see example template).\n"
        "       Research configuration: ercot7k_config/*.csv.\n"
        "       Baseline ercot7k/ remains immutable.\n"
        "       Derived cases are written under ercot7k-derived/.\n"
        "       PSO case selection is handled automatically by the menu.\n"

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
# confirm_datacenter_route()
# Displays the selected modeling route and requests confirmation.
# ------------------------------------------------------------------------------
def confirm_datacenter_route(route: str) -> bool:
    print("\n" + "=" * 72)

    if route == "pypsa":
        print("PyPSA DevNet — Datacenter BYOG")
        print("-" * 72)
        print("Build a 6-bus DevNet model with configurable datacenter")
        print("load, BYOG generation capacity and marginal cost.")
        print("Configuration: devnet_config/devnet_dc.csv")
        print("Engine: PyPSA / HiGHS")

    elif route == "pso":
        print("PSO ERCOT Texas7k — Datacenter Modeling")
        print("-" * 72)
        print("Run the ERCOT7k baseline or build a derived case with")
        print("datacenter load, BYOG generation and stress parameters.")
        print("Configuration: ercot7k_config/*.csv and pso.local.toml")
        print("Engine: Polaris PSO / AIMMS / CPLEX")
        print("Requires a separately installed and licensed PSO environment.")

    else:
        return False

    print("=" * 72)

    answer = input("\nProceed with selected modeling route? [Y/N]: ")
    return answer.strip().lower() in ("y", "yes")


# ------------------------------------------------------------------------------
# pso_case_paths()
# Returns the ERCOT7k baseline and available derived-case control files.
# ------------------------------------------------------------------------------
def pso_case_paths() -> tuple[Path, list[Path]]:
    root = Path(__file__).resolve().parent

    baseline = root / "ercot7k" / "texas7k.csv"
    derived_root = root / "ercot7k-derived"

    derived = sorted(
        derived_root.glob("*/texas7k.csv")
    ) if derived_root.is_dir() else []

    return baseline, derived


# ------------------------------------------------------------------------------
# select_pso_derived_case()
# Prompts the researcher to select an existing derived case.
# ------------------------------------------------------------------------------
def select_pso_derived_case() -> Path | None:
    _, derived = pso_case_paths()

    if not derived:
        print("\nNo derived ERCOT7k cases found.")
        print("Use 'Build Derived Case' first.")
        return None

    choice = pick_submenu(
        "Select derived ERCOT7k case:",
        [path.parent.name for path in derived],
    )

    if choice == 0:
        return None

    return derived[choice - 1]


# ------------------------------------------------------------------------------
# run_pso_case()
# Validates the PSO environment and runs the selected case.
# ------------------------------------------------------------------------------
def run_pso_case(case_file: Path, label: str) -> None:
    if not case_file.is_file():
        print(f"\nAMW-ERR: PSO case not found:\n\t{case_file}")
        input("\nPress Enter to return to menu...")
        return

    print("\nPSO/AIMMS Environment Preflight")
    print("-" * 45)
    print(f"Selected case: {label}")
    print(f"Case file:\n\t{case_file}")
    print("See README.md -> PSO/AIMMS Environment Dependencies.")

    if input("\nProceed with PSO preflight? [Y/N]: ").strip().lower() not in ("y", "yes"):
        print("\nPSO execution cancelled.")
        return

    env = {"DEVNET_PSO_CASE": str(case_file.resolve())}

    rc = run_script("pso_preflight.py", env_overrides=env)

    if rc != 0:
        print("\nPSO preflight FAILED.")
        input("Press Enter to return to menu...")
        return

    rc = run_script("ercot7k_pso.py", env_overrides=env)

    input(
        f"\nFinished ercot7k_pso.py (exit code {rc}). "
        "Press Enter to return to menu..."
    )

# ------------------------------------------------------------------------------
# configure_pso_derived_case()
# Initializes or displays the ERCOT7k derived-case configuration.
# ------------------------------------------------------------------------------
def configure_pso_derived_case() -> None:
    root = Path(__file__).resolve().parent
    config_dir = root / "ercot7k_config"

    required = (
        config_dir / "ercot7k_dc.csv",
        config_dir / "ercot7k_stress.csv",
    )

    if not all(path.is_file() for path in required):
        print("\nERCOT7k configuration templates are missing.")
        print("Initializing ercot7k_config/*.csv...\n")

        rc = run_script("ercot7k_build.py", args=["--init"])

        if rc != 0:
            print("\nConfiguration initialization failed.")
            input("Press Enter to return to menu...")
            return

    print("\nActive ERCOT7k configuration:")
    rc = run_script("ercot7k_build.py", args=["--show-config"])

    print("\nEdit the CSV configuration files before building a derived case.")
    print(f"Configuration directory:\n\t{config_dir}")

    input(f"\nConfiguration review finished (exit code {rc}). Press Enter...")


# ------------------------------------------------------------------------------
# run_pso_node_screen()
# Selects an existing PSO result set and launches interactive node screening.
# Delegates filter review, geographic mapping, and CSV output to the screener.
# ------------------------------------------------------------------------------
def run_pso_node_screen() -> None:
    root = Path(__file__).resolve().parent
    runs_dir = root / "ercot7k-runs"

    if not runs_dir.is_dir():
        print("\nASR-ERR: No ERCOT7k run directory found.")
        print("Run the ERCOT7k baseline first.")
        input("\nPress Enter to return to menu...")
        return

    available = sorted(
        path.name
        for path in runs_dir.iterdir()
        if path.is_dir()
        and (path / "results" / "results_PC_Nd.csv").is_file()
        and (path / "results" / "results_ED_Ara.csv").is_file()
    )

    if not available:
        print("\nASR-ERR: No valid ERCOT7k PSO result sets found.")
        print("Expected results_PC_Nd.csv and results_ED_Ara.csv.")
        input("\nPress Enter to return to menu...")
        return

    selected = pick_submenu(
        "Select ERCOT7k baseline run for node screening:",
        available,
    )

    if selected == 0:
        return

    run_name = available[selected - 1]

    print("\nERCOT7k Node Screening")
    print("-" * 72)
    print(f"Selected run: {run_name}")
    print("Screen and rank nodes using LMP separation from area balance price.")
    print("Metrics: max_spread | mean_spread | stress_hours")
    print("The screening script will confirm filter, geographic, and output CSVs.")
    print("No AIMMS/CPLEX optimization is performed.")

    if input("\nProceed? [Y/N]: ").strip().lower() not in ("y", "yes"):
        print("\nASR-DBG: Node screening cancelled.")
        return

    rc = run_script(
        "ercot7k_node_screen.py",
        args=["--run", run_name],
    )

    input(
        f"\nFinished ercot7k_node_screen.py (exit code {rc}). "
        "Press Enter to return to PSO menu..."
    )

# ------------------------------------------------------------------------------
# run_pso_geo_plot()
# Selects ranked ERCOT7k node data and generates an interactive geographic map.
# ------------------------------------------------------------------------------
def run_pso_geo_plot() -> None:
    root = Path(__file__).resolve().parent
    runs_dir = root / "ercot7k-runs"

    if not runs_dir.is_dir():
        print("\nASR-ERR: ERCOT7k runs directory not found.")
        input("Press Enter to return to menu...")
        return

    available = sorted(
        runs_dir.rglob("ercot7k_node_ranked.csv")
    )

    if not available:
        print("\nASR-ERR: No ranked-node CSV files found.")
        print("Run 'Screen / Rank ERCOT7k Nodes' first.")
        input("Press Enter to return to menu...")
        return

    choice = pick_submenu(
        "Select ERCOT7k ranked-node dataset:",
        [str(path.relative_to(runs_dir)) for path in available],
    )

    if choice == 0:
        return

    selected = available[choice - 1]
    output = root / "geo-plots" / "ercot7k_node_map.html"

    print("\nERCOT7k Geographic Plot")
    print("-" * 72)
    print(f"Input CSV:\n  {selected}")
    print(f"Output HTML:\n  {output}")
    print("Interactive Texas map with ranked nodes and LMP/stress metrics.")
    print("No PSO optimization is performed.")

    if input("\nProceed? [Y/N]: ").strip().lower() not in ("y", "yes"):
        print("\nASR-DBG: Geographic plotting cancelled.")
        return

    rc = run_script(
        "geo-plots/ercot7k_node_map.py",
        args=[
            "--input", str(selected),
            "--output", str(output),
        ],
    )

    if rc == 0:
        print(f"\nASR-DBG: Geographic plot generated:\n  {output}")
        print("Open the HTML file in your browser.")

    input(
        f"\nGeographic plot finished (exit code {rc}). "
        "Press Enter to return to PSO menu..."
    )

# ------------------------------------------------------------------------------
# run_pso_menu()
# Central entry point for ERCOT7k baseline optimization, node screening,
# geographic visualization, derived-case configuration, and optimization.
# Baseline/derived comparison remains pending.
# ------------------------------------------------------------------------------
def run_pso_menu() -> None:
    while True:
        what = pick_submenu(
            "PSO route -- ERCOT Texas7k:",
            [
                "Run Baseline (ercot7k_pso.py)",
                "Screen / Rank ERCOT7k Nodes (ercot7k_node_screen.py)",
                "Plot Ranked ERCOT7k Nodes (geo-plots/ercot7k_node_map.py)",
                "Configure Derived Case (ercot7k_build.py --init / --show-config)",
                "Build Derived Case (ercot7k_build.py / ercot7k_case.py)",
                "Run Derived Case (ercot7k_pso.py)",
                "Compare Baseline vs Derived Case (ercot7k_results.py) [PENDING]",
            ],
        )

        if what == 0:
            return


        if what == 1:
            baseline, _ = pso_case_paths()
            run_pso_case(baseline, "ERCOT7k Baseline")

        elif what == 2:
            run_pso_node_screen()

        elif what == 3:
            run_pso_geo_plot()

        elif what == 4:
            configure_pso_derived_case()

        elif what == 5:
            root = Path(__file__).resolve().parent
            config_dir = root / "ercot7k_config"

            if not config_dir.is_dir():
                print("\nERCOT7k configuration not initialized.")
                print("Use 'Configure Derived Case' first.")
                input("Press Enter to continue...")
                continue

            rc = run_script("ercot7k_build.py")

            input(
                f"\nDerived-case builder finished (exit code {rc}). "
                "Press Enter to continue..."
            )

        elif what == 6:
            selected = select_pso_derived_case()

            if selected is not None:
                run_pso_case(selected, selected.parent.name)

        elif what == 7:
            print("\nBaseline/derived comparison is not yet connected.")
            print("We will integrate ercot7k_results.py after reviewing its interface.")
            input("Press Enter to continue...")

# ------------------------------------------------------------------------------
# run_datacenter_case()
# Option 3: pick the engine route for a datacenter case, then dispatch.
#
# PyPSA route -> devnetDC_sld.py, the 6-bus DevNet SLD with Datacenter BYOG.
# PSO route   -> the ERCOT Texas7k public case: run it (ercot7k_pso.py) or build
#                a derived case layer on top of the immutable base
#                (ercot7k_build.py). PSO-only: no PyPSA network is built. The
#                stress matrix is not part of this build and says so rather than
#                being hidden.
#
#                The builder lives here rather than at a top level of its own so
#                that every PSO entry point sits behind the one engine route.
# ------------------------------------------------------------------------------
def run_datacenter_case() -> None:
    route = pick_submenu(
        "Datacenter case -- select engine route:",
        [
            "PyPSA: DevNet 6-bus SLD with Datacenter BYOG (devnetDC_sld.py)",
            "PSO:   ERCOT Texas7k public case (6717 buses) (ercot7k_pso.py)",
        ],
    )

    if route == 1:
        if not confirm_datacenter_route("pypsa"):
            print("\nReturning to main menu.")
            return

        rc = run_script("devnetDC_sld.py")
        input(f"\nFinished devnetDC_sld.py (exit code {rc}). Press Enter to return to menu...")
        return

    if route != 2:
        return

    if not confirm_datacenter_route("pso"):
        print("\nReturning to main menu.")
        return

    run_pso_menu()

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
