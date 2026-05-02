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

# devnet_cfg.py
# 
# Generates default user-configurable CSV templates for DevNet.
# 
# Output:
# ./devnet_config/
#    devnet_buses.csv
#    devnet_lines.csv
#    devnet_assets.csv
#    devnet_dc.csv
#    devnet_carriers.csv
#
# Workflow:
# 1. Run this script once.
# 2. Edit CSV values in ./devnet_config/.
# 3. Run devnet_sld.py to build the PyPSA network from CSV inputs.

# Run: devnet_cfg.py
# ------------------------------------------------------------------------------

import os
import sys
import pandas as pd

# Global defines
SECTION_SEPARATOR = "=" * 80 + "\n"
SUBSECTION_SEPARATOR = "-"*40 + "\n" # for print separation

# ----- Resolve paths next to this script -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "devnet_config")


# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt: str) -> bool:
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")


def write_csv_if_allowed(path: str, df: pd.DataFrame) -> None:
    fname = os.path.basename(path)

    # Context-aware message
    if fname == "devnet_dc.csv":
        print("ASR-DBG: Writing datacenter BYOG configuration (devnet_dc.csv)...")

    if os.path.exists(path):
        print(f"ASR-DBG: Found existing CSV:\n\t{path}")
        if not confirm("Overwrite this CSV?"):
            print("ASR-DBG: Keeping existing CSV.\n")
            return

    df.to_csv(path, index=False)
    print(f"ASR-DBG: Wrote CSV:\n\t{path}\n")

# ------------------------------------------------------------------------------
#   Main function
# ------------------------------------------------------------------------------
def main() -> None:
    print(SECTION_SEPARATOR)
    print("DevNet 6 bus node SLD CSV Configuration Generator...")
    print(SUBSECTION_SEPARATOR)

    print("This script will create default DevNet 6 bus node CSV templates in:")
    print(f"\t{CONFIG_PATH}\n")

    print("After this step:")
    print("\t1. Edit the CSV files as needed.")
    print("\t2. Then run devnet_sld.py to generate the PyPSA SLD/network.\n")

    if os.path.isdir(CONFIG_PATH):
        print(f"ASR-DBG: Found existing config folder:\n\t{CONFIG_PATH}\n")
    else:
        os.makedirs(CONFIG_PATH)
        print(f"ASR-DBG: Created config folder:\n\t{CONFIG_PATH}\n")

    input("Press Enter to generate / verify default CSV templates...\n")

    buses_df = pd.DataFrame([
        {"bus": "WECC_NW",  "x": 10.0,  "y": 0.0,    "v_nom": 345, "carrier": "ac"},
        {"bus": "WECC_SW",  "x": 5.0,   "y": -8.66,  "v_nom": 345, "carrier": "ac"},
        {"bus": "SPP_MISO", "x": -5.0,  "y": -8.66,  "v_nom": 345, "carrier": "ac"},
        {"bus": "PJM_NE",   "x": -10.0, "y": 0.0,    "v_nom": 345, "carrier": "ac"},
        {"bus": "SERC_SE",  "x": -5.0,  "y": 8.66,   "v_nom": 345, "carrier": "ac"},
        {"bus": "ERCOT",    "x": 5.0,   "y": 8.66,   "v_nom": 345, "carrier": "ac"},
    ])

    lines_df = pd.DataFrame([
        {"line": "L_WECC_NW_WECC_SW",  "bus0": "WECC_NW",  "bus1": "WECC_SW",  "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
        {"line": "L_WECC_SW_SPP_MISO", "bus0": "WECC_SW",  "bus1": "SPP_MISO", "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
        {"line": "L_SPP_MISO_ERCOT",   "bus0": "SPP_MISO", "bus1": "ERCOT",    "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
        {"line": "L_SPP_MISO_PJM_NE",  "bus0": "SPP_MISO", "bus1": "PJM_NE",   "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
        {"line": "L_PJM_NE_SERC_SE",   "bus0": "PJM_NE",   "bus1": "SERC_SE",  "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
        {"line": "L_SERC_SE_ERCOT",    "bus0": "SERC_SE",  "bus1": "ERCOT",    "x": 0.1, "r": 0.01, "s_nom": 5000, "carrier": "ac"},
    ])

    assets_df = pd.DataFrame([
        {"bus": "WECC_NW",  "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
        {"bus": "WECC_SW",  "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
        {"bus": "SPP_MISO", "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
        {"bus": "PJM_NE",   "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
        {"bus": "SERC_SE",  "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
        {"bus": "ERCOT",    "gen_p_nom": 8000, "gen_mc": 50, "load_p_set": 5000},
    ])

    print("ASR-DBG: Adding datacenter w/ BYOG asset at PJM_NE bus...\n")
    dc_df = pd.DataFrame([
        {
            "dc_name": "DC_PJM_NE",
            "bus": "PJM_NE",
            "p_set": 2000,
            "byog_p_nom": 2000,
            "byog_mc": 60,
        }
    ])

    carriers_df = pd.DataFrame([
        {"carrier": "gas",  "co2_emissions": 0.19},
        {"carrier": "load", "co2_emissions": 0.00},
        {"carrier": "ac",   "co2_emissions": 0.00},
    ])

    write_csv_if_allowed(os.path.join(CONFIG_PATH, "devnet_buses.csv"), buses_df)
    write_csv_if_allowed(os.path.join(CONFIG_PATH, "devnet_lines.csv"), lines_df)
    write_csv_if_allowed(os.path.join(CONFIG_PATH, "devnet_assets.csv"), assets_df)
    write_csv_if_allowed(os.path.join(CONFIG_PATH, "devnet_dc.csv"), dc_df)
    write_csv_if_allowed(os.path.join(CONFIG_PATH, "devnet_carriers.csv"), carriers_df)

    print(SECTION_SEPARATOR)
    print("DevNet CSV templates are ready.\n")
    print("Next step:")
    print(f"\tEdit CSVs in:\n\t{CONFIG_PATH}\n")
    print("Then run:")
    print("\tpython devnet_sld.py\n")

# ------------------------------------------------------------------------------
#   Entry point
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
# ------------------------------------------------------------------------------
# End of devnet_cfg.py
# ------------------------------------------------------------------------------
