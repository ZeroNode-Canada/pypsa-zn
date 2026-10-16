
#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 ZeroNode
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

# pso_preflight.py
#
# Purpose
#   Validate the PSO/AIMMS Python environment before launching the
#   ERCOT Texas7k PSO full-cycle runner.
#
# What it does
#   - Loads pso.local.toml through pso_config.py.
#   - Verifies the PSO AIMMS project path.
#   - Verifies the configured PSO Python interpreter.
#   - Confirms aimmspy imports successfully in that interpreter.
#   - Returns a nonzero exit code on validation failure.
#
# Usage
#   python pso_preflight.py
#
#   Automatically invoked by devnet_menu.py:
#   Option 3 -> PSO route -> Run the base case, full cycle.
#
# Note
#   Does not launch AIMMS or execute a PSO solve.
#   AIMMS licensing and solver readiness are checked by ercot7k_pso.py.
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Standard imports
# ------------------------------------------------------------------------------
import os
import subprocess
import sys
from pathlib import Path

# ------------------------------------------------------------------------------
# Project imports
# ------------------------------------------------------------------------------
import pso_config

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
SECTION_SEPARATOR = "-" * 45
README_SECTION = "PSO/AIMMS Environment Dependencies"

# ------------------------------------------------------------------------------
# main()
# Validates PSO configuration, interpreter availability and aimmspy import.
# Returns 0 on success, 1 on failure.
# ------------------------------------------------------------------------------
def main() -> int:
    print("\nPSO/AIMMS environment preflight")
    print(SECTION_SEPARATOR)

    # ------------------------------------------------------------------
    # Validate and load PSO configuration.
    # ------------------------------------------------------------------
    if not pso_config.CONFIG_FILE.is_file():
        print("FAIL: pso.local.toml not found.")
        print("Copy pso.local.toml.example and configure it.")
        return 1

    try:
        pso_config.load_config()
    except Exception as exc:
        print(f"FAIL: Cannot read pso.local.toml: {exc}")
        return 1

    project = os.environ.get("DEVNET_PSO_PROJECT", "").strip()
    python = os.environ.get("DEVNET_PSO_PYTHON", "").strip()

    # ------------------------------------------------------------------
    # Validate AIMMS project and PSO Python interpreter paths.
    # ------------------------------------------------------------------
    if not project or not Path(project).is_file():
        print(f"FAIL: Invalid PSO project path: {project or '(unset)'}")
        return 1

    print("OK: PSO.aimms project found.")

    if not python or not Path(python).is_file():
        print(f"FAIL: Invalid PSO Python path: {python or '(unset)'}")
        return 1

    print(f"OK: PSO Python interpreter: {python}")

    # ------------------------------------------------------------------
    # Verify aimmspy in the dedicated PSO Python environment.
    # ------------------------------------------------------------------
    probe = (
        "import aimmspy; "
        "print('aimmspy OK:', aimmspy.__version__)"
    )

    try:
        result = subprocess.run(
            [python, "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: Could not execute PSO Python: {exc}")
        return 1

    if result.returncode != 0:
        print("FAIL: aimmspy import failed.")
        print((result.stderr or result.stdout).strip())
        print(f"See README.md -> {README_SECTION}.")
        return 1

    print(f"OK: {result.stdout.strip()}")
    print("PSO preflight PASSED.\n")
    return 0


# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())

# ------------------------------------------------------------------------------
# END OF pso_preflight.py
# ------------------------------------------------------------------------------
