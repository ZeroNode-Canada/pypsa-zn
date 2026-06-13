#!/usr/bin/env python3

# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2026 ZeroNode
#
# Licensed under the Apache License, Version 2.0

# pypsa_zn_demo.py
#
# ZeroNode Demo Runner
#
# Non-interactive demo wrapper around:
#   lib/devnet_stress_lib.py
#
# Run:
#
#   Enumerate available demo presets:
#       python pypsa_zn_demo.py
#
#   Run explicit preset:
#       python pypsa_zn_demo.py --preset byog_competes_case1
#       python pypsa_zn_demo.py --preset byog_competes_case2
#       python pypsa_zn_demo.py --preset byog_complements_case1
#
# ------------------------------------------------------------------
# Demo preset families
#
#   byog_competes_case*
#       ρ → ∞
#       BYOG competes with grid generation
#
#   byog_complements_case*
#       ρ ≈ 1
#       BYOG complements grid supply
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------
#   Standard library imports
# ------------------------------------------------------------------
import os
import sys
import json
import argparse

# ------------------------------------------------------------------
#   Demo HTTP server imports
# ------------------------------------------------------------------
import threading
import subprocess
import webbrowser

from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from urllib.parse import urlparse, parse_qs

# ------------------------------------------------------------------
#    Runtime arg assembly / filesystem helpers
# ------------------------------------------------------------------
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

# ------------------------------------------------------------------
#   Third-party imports
# ------------------------------------------------------------------
import pandas as pd
import pypsa
import matplotlib.pyplot as plt

# ------------------------------------------------------------------------------
#   Resolve paths
# ------------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYPSA_ZN_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
LIB_DIR = os.path.join(PYPSA_ZN_ROOT, "lib")

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import devnet_stress_lib as dsl

TS = datetime.now().strftime("%Y%m%d-%H%M%S")

SECTION_SEPARATOR = dsl.SECTION_SEPARATOR
SUBSECTION_SEPARATOR = dsl.SUBSECTION_SEPARATOR

# ------------------------------------------------------------------------------
#   Demo paths
# ------------------------------------------------------------------------------
DEVNET_NAME = "devnetDC-sld"
DEVNET_BLD_PATH = os.path.join(PYPSA_ZN_ROOT, DEVNET_NAME)

DEMO_PRESETS_JSON = os.path.join(SCRIPT_DIR, "demo_presets.json")
DEMO_OUTDIR = os.path.join(SCRIPT_DIR, "demo_out")

DEMO_PLOTS_DIR = os.path.join(
    SCRIPT_DIR,
    "plots"
)

RUNTIME_COMPETES_CSV = os.path.join(
    DEMO_OUTDIR,
    "byog_competes.csv"
)

RUNTIME_COMPLEMENTS_CSV = os.path.join(
    DEMO_OUTDIR,
    "byog_complements.csv"
)

# ------------------------------------------------------------------------------
#       Set MASTER_CSV_MODE = True::
#           Generates golden demo/plots/*.csv for plottingMASTER_CSV_MODE = False
# ------------------------------------------------------------------------------
MASTER_CSV_MODE = False  # False | True

BYOG_COMPETES_CSV = os.path.join(
    DEMO_PLOTS_DIR,
    "byog_competes.csv"
)

BYOG_COMPLEMENTS_CSV = os.path.join(
    DEMO_PLOTS_DIR,
    "byog_complements.csv"
)

DEMO_HTML = os.path.join(SCRIPT_DIR, "pypsa_zn_demo.html")
DEMO_ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
DEMO_DASHBOARD_TEMPLATE = os.path.join(
    DEMO_ASSETS_DIR,
    "demo_dashboard.html"
)

DEMO_LANDING_TEMPLATE = os.path.join(
    DEMO_ASSETS_DIR,
    "demo_landing.html"
)
DEMO_LANDING_HTML = os.path.join(
    SCRIPT_DIR,
    "pypsa_zn_demo_land.html"
)
DEMO_SERVER_PORT = 8000
DEMO_SESSION_STARTED = False

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def load_demo_presets() -> dict:
    if not os.path.exists(DEMO_PRESETS_JSON):
        raise FileNotFoundError(f"Missing demo preset file:\n\t{DEMO_PRESETS_JSON}")

    with open(DEMO_PRESETS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_preset(preset_name: str, preset: dict) -> None:
    required = [
        "k_load",
    ]

    for r in required:
        if r not in preset:
            raise ValueError(f"Preset '{preset_name}' missing field: {r}")

def load_devnet() -> pypsa.Network:
    if not os.path.isdir(DEVNET_BLD_PATH):
        raise FileNotFoundError(f"Missing DevNet build folder:\n\t{DEVNET_BLD_PATH}")

    return pypsa.Network(DEVNET_BLD_PATH)

# ------------------------------------------------------------------------------
#   Runtime arg assembly
# ------------------------------------------------------------------------------
def build_runtime_args(cli_args, preset: dict) -> SimpleNamespace:

    # ------------------------------------------------------------------
    # Resolve runtime defaults from loaded DevNet CSV configuration
    # ------------------------------------------------------------------
    devnet = load_devnet()

    dc_defaults = dsl.resolve_dc_csv_values(devnet)

    # ------------------------------------------------------------------
    # Resolve generator marginal costs from CSV network
    # ------------------------------------------------------------------
    mc_bus = {}

    for gen_name, row in devnet.generators.iterrows():
        bus = row["bus"]
        mc = float(row["marginal_cost"])
        mc_bus[bus] = mc

    # ------------------------------------------------------------------
    # Optional mc_bus overrides from demo preset
    # ------------------------------------------------------------------
    mc_bus.update(
        preset.get("mc_bus", {})
    )

    k_load = preset["k_load"]

    # ------------------------------------------------------------------
    # Resolve runtime values:
    #
    # Priority:
    #   CLI override
    #     > preset override
    #       > DevNet CSV defaults
    # ------------------------------------------------------------------

    byog_mc = (
        cli_args.byog_mc
        if cli_args.byog_mc is not None
        else preset.get("byog_mc", dc_defaults["byog_mc"])
    )

    dc_p_nom = (
        cli_args.dc_p_nom
        if cli_args.dc_p_nom is not None
        else preset.get("dc_p_nom", dc_defaults["p_nom"])
    )

    dc_p_set = (
        cli_args.dc_p_set
        if cli_args.dc_p_set is not None
        else preset.get("dc_p_set", None)
    )

    return SimpleNamespace(
        scenario="baseline",
        solver="highs",
        outdir=DEMO_OUTDIR,

        k_load=json.dumps(k_load),
        k_line="{}",

        mc_bus=json.dumps(mc_bus),

        mc_mode="set",

        byog_mc=float(byog_mc),

        dc_p_set=float(dc_p_set) if dc_p_set is not None else None,

        dc_p_nom=float(dc_p_nom),

        line="",

        kmin=1.0,
        kmax=0.2,
        kstep=-0.1,
    )

# ------------------------------------------------------------------------------
#   Demo HTTP handler
# ------------------------------------------------------------------------------
class DemoHTTPRequestHandler(SimpleHTTPRequestHandler):

    # --------------------------------------------------------------
    # Suppress HTTP request logging
    # --------------------------------------------------------------
    def log_message(
        self,
        format,
        *args
    ):
        pass

    def translate_path(self, path):

        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]

        # --------------------------------------------------------------
        # Serve DevNet build assets outside demo/
        # --------------------------------------------------------------
        if path.startswith("/devnetDC-sld/"):

            rel = path[len("/devnetDC-sld/"):]

            return os.path.join(
                PYPSA_ZN_ROOT,
                "devnetDC-sld",
                rel
            )

        if path.startswith("/devnet-sld/"):

            rel = path[len("/devnet-sld/"):]

            return os.path.join(
                PYPSA_ZN_ROOT,
                "devnet-sld",
                rel
            )

        return super().translate_path(path)

    def do_GET(self):

        parsed = urlparse(self.path)

        # --------------------------------------------------------------
        # DevNet base parameter endpoint
        # --------------------------------------------------------------
        if parsed.path == "/devnet_base_params":

            devnet = load_devnet()

            txt = "\n".join(
                dsl.build_sanity_panel_lines(devnet)
            )

            self.send_response(200)

            self.send_header(
                "Content-type",
                "text/plain"
            )

            self.end_headers()

            self.wfile.write(
                txt.encode("utf-8")
            )

            return

        # --------------------------------------------------------------
        # Heartbeat endpoint
        # --------------------------------------------------------------
        if parsed.path == "/heartbeat":

            self.send_response(200)

            self.send_header(
                "Content-type",
                "text/plain"
            )

            self.end_headers()

            self.wfile.write(b"alive")

            return
        
        # ------------------------------------------------------------------
        # Execute preset scenario
        # ------------------------------------------------------------------
        if parsed.path == "/run":

            global DEMO_SESSION_STARTED
            # ----------------------------------------------------------
            # First visitor run:
            #   purge prior commits/session artifacts
            # ----------------------------------------------------------
            if not DEMO_SESSION_STARTED:
                demo_out = Path(DEMO_OUTDIR)
                if demo_out.exists():

                    for f in demo_out.glob("*"):
                        try:
                            if f.is_file():
                                f.unlink()
                        except Exception:
                            pass
                DEMO_SESSION_STARTED = True

            qs = parse_qs(parsed.query)

            preset = qs.get("preset", [None])[0]

            if preset is None:

                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing preset")
                return

            cmd = [
                sys.executable,
                os.path.join(SCRIPT_DIR, "pypsa_zn_demo.py"),
                "--preset",
                preset
            ]

            if MASTER_CSV_MODE:

                cmd.append(
                    "--master-csv-mode"
                )

            subprocess.run(cmd)

            self.send_response(302)
            self.send_header(
                "Location",
                "/pypsa_zn_demo.html"
            )
            self.end_headers()

            return

        return super().do_GET()

# ------------------------------------------------------------------------------
#   Generate demo landing page
# ------------------------------------------------------------------------------
def write_demo_landing_page(
    presets: dict
) -> str:

    if not os.path.exists(DEMO_LANDING_TEMPLATE):
        raise FileNotFoundError(
            f"Missing landing template:\n\t{DEMO_LANDING_TEMPLATE}"
        )

    with open(
        DEMO_LANDING_TEMPLATE,
        "r",
        encoding="utf-8"
    ) as f:

        html = f.read()

    # ------------------------------------------------------------------
    # Build preset tiles
    # ------------------------------------------------------------------
    tiles = []

    for preset_name, preset in presets.items():

        desc = preset.get(
            "description",
            ""
        )

        notes = preset.get(
            "notes",
            []
        )

        is_scenario_header = (
            preset_name.endswith("_scenario")
        )

        notes_html = ""
        if notes:
            notes_html += (
                '<div class="preset-notes">'
            )
            for n in notes:

                notes_html += (
                    f"<div>• {n}</div>"
                )
            notes_html += "</div>"

        if is_scenario_header:

            notes_html = ""

            for n in desc:
                notes_html += f"<div>• {n}</div>"

            tiles.append(
                f'''
                <div class="preset-card">

                  <div class="preset-title">
                    {preset_name.replace("_", " ").title()}
                  </div>

                  <div class="preset-desc scenario-desc">
                    {notes_html}
                  </div>

                </div>
                '''
            )

        else:

            notes_html = ""

            for n in notes:
                notes_html += f"<div>• {n}</div>"

            tiles.append(
                f'''
                <div class="preset-card">

                  <div class="preset-title">
                    {preset_name}
                  </div>

                  <div class="preset-desc">
                    {desc}
                  </div>

                  <div class="preset-notes">
                    {notes_html}
                  </div>

                  <a
                      class="run-btn"
                      href="javascript:void(0);"
                      onclick="runScenario('{preset_name}')"
                  >
                      Run Scenario
                  </a>

                </div>
                '''
            )

    html = html.replace(
        "{{PRESET_TILES}}",
        "\n".join(tiles).strip()
    )

    with open(
        DEMO_LANDING_HTML,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    return DEMO_LANDING_HTML

# ------------------------------------------------------------------------------
#   Append master plot row: 
#       Set MASTER_CSV_MODE = True::
#           Generates golden demo/plots/*.csv for plotting
# ------------------------------------------------------------------------------
def build_master_plot_csvs(
    preset_name: str,
    args,
    dash: dict
):

    Path(DEMO_PLOTS_DIR).mkdir(
        parents=True,
        exist_ok=True
    )

    if preset_name.startswith(
        "byog_competes_case"
    ):

        csv_file = BYOG_COMPETES_CSV

        scenario = "byog_competes"

    elif preset_name.startswith(
        "byog_complements_case"
    ):

        csv_file = BYOG_COMPLEMENTS_CSV

        scenario = "byog_complements"

    else:

        return

    row = {
        "scenario": scenario,
        "case": preset_name,
        "k_load": args.k_load,
        "byog_mc": args.byog_mc,
        "dc_p_nom": args.dc_p_nom,
        "objective": dash.get(
            "objective",
            float("nan")
        ),
        "dc_dispatch_mw": dash.get(
            "dc_dispatch_mw",
            float("nan")
        ),
        "lmp_spread": dash.get(
            "lmp_spread",
            float("nan")
        )
    }

    df_new = pd.DataFrame([row])

    if os.path.exists(csv_file):

        df_old = pd.read_csv(csv_file)

        df_old = df_old[
            df_old["case"] != preset_name
        ]

        df = pd.concat(
            [df_old, df_new],
            ignore_index=True
        )

    else:

        df = df_new

    df.to_csv(
        csv_file,
        index=False
    )

# ------------------------------------------------------------------------------
#   Append runtime results to CSV for plotting
# ------------------------------------------------------------------------------
def append_runtime_plot_row(
    preset_name: str,
    args,
    dash: dict
):

    Path(DEMO_OUTDIR).mkdir(
        parents=True,
        exist_ok=True
    )

    if preset_name.startswith(
        "byog_competes_case"
    ):

        csv_file = RUNTIME_COMPETES_CSV

        scenario = "byog_competes"

    elif preset_name.startswith(
        "byog_complements_case"
    ):

        csv_file = RUNTIME_COMPLEMENTS_CSV

        scenario = "byog_complements"

    else:

        return

    row = {
        "scenario": scenario,
        "case": preset_name,
        "k_load": args.k_load,
        "byog_mc": args.byog_mc,
        "dc_p_nom": args.dc_p_nom,
        "objective": dash.get(
            "objective",
            float("nan")
        ),
        "dc_dispatch_mw": dash.get(
            "dc_dispatch_mw",
            float("nan")
        ),
        "lmp_spread": dash.get(
            "lmp_spread",
            float("nan")
        )
    }

    df_new = pd.DataFrame([row])

    if os.path.exists(csv_file):

        df_old = pd.read_csv(csv_file)

        df = pd.concat(
            [df_old, df_new],
            ignore_index=True
        )

    else:

        df = df_new

    df.to_csv(
        csv_file,
        index=False
    )

# ------------------------------------------------------------------------------
#   Demo HTML
# ------------------------------------------------------------------------------
def write_demo_html(
    result: dict,
    args: SimpleNamespace,
    preset_name: str
) -> str:

    Path(SCRIPT_DIR).mkdir(parents=True, exist_ok=True)

    if not os.path.exists(DEMO_DASHBOARD_TEMPLATE):
        raise FileNotFoundError(
            f"Missing dashboard template:\n\t{DEMO_DASHBOARD_TEMPLATE}"
        )

    dash = result["dash"]

    # ------------------------------------------------------------------
    # Resolve runtime values
    # ------------------------------------------------------------------
    objective_m = dash.get("objective", 0.0) / 1e6

    lmp_spread = dash.get("lmp_spread", 0.0)

    max_loading = dash.get("max_loading_pu", 0.0)

    near_bind = dash.get("near_bind_ct", 0)

    dc_p_set_display = (
        "CSV Preset::2000.0"
        if args.dc_p_set is None
        else f"{args.dc_p_set:.0f} MW"
    )

    # ------------------------------------------------------------------
    # Load HTML template
    # ------------------------------------------------------------------
    with open(
        DEMO_DASHBOARD_TEMPLATE,
        "r",
        encoding="utf-8"
    ) as f:

        html = f.read()

    # ------------------------------------------------------------------
    # Template substitutions
    # ------------------------------------------------------------------
    html = html.replace("{{PRESET_NAME}}", str(preset_name))

    html = html.replace(
        "{{OBJECTIVE_M}}",
        f"${objective_m:.3f}M"
    )

    html = html.replace(
        "{{LMP_SPREAD}}",
        f"{lmp_spread:.3f}"
    )

    html = html.replace(
        "{{MAX_LOADING_PU}}",
        f"{max_loading:.3f}"
    )

    html = html.replace(
        "{{NEAR_BIND_CT}}",
        str(near_bind)
    )

    html = html.replace(
        "{{K_LOAD}}",
        str(args.k_load)
    )

    html = html.replace(
        "{{BYOG_MC}}",
        f"${args.byog_mc:.1f}/MWh"
    )

    html = html.replace(
        "{{DC_P_NOM}}",
        f"{args.dc_p_nom:.0f} MW"
    )

    html = html.replace(
        "{{DC_P_SET}}",
        dc_p_set_display
    )

    # ------------------------------------------------------------------
    # Write rendered dashboard
    # ------------------------------------------------------------------
    with open(
        DEMO_HTML,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    return DEMO_HTML

# ------------------------------------------------------------------------------
#   Purge master plot artifacts
# ------------------------------------------------------------------------------
def purge_master_plot_artifacts():

    Path(DEMO_PLOTS_DIR).mkdir(
        parents=True,
        exist_ok=True
    )

    for fn in [

        "byog_competes.csv",
        "byog_complements.csv",

        "competes_cost.png",
        "competes_lmp.png",

        "complements_cost.png",
        "complements_lmp.png"
    ]:

        f = Path(DEMO_PLOTS_DIR) / fn

        if f.exists():

            try:
                f.unlink()
            except Exception:
                pass


# ------------------------------------------------------------------------------
#   Generate story plots
# ------------------------------------------------------------------------------
def generate_story_plots():

    Path(DEMO_PLOTS_DIR).mkdir(
        parents=True,
        exist_ok=True
    )

    competes_csv = Path(
        BYOG_COMPETES_CSV
    )

    complements_csv = Path(
        BYOG_COMPLEMENTS_CSV
    )

    if not competes_csv.exists():

        print(
            "\nERROR::Missing:\n"
            f"\t{competes_csv}\n"
        )

        return

    if not complements_csv.exists():

        print(
            "\nERROR::Missing:\n"
            f"\t{complements_csv}\n"
        )

        return

    df_competes = pd.read_csv(
        competes_csv
    )

    df_complements = pd.read_csv(
        complements_csv
    )

    # ----------------------------------------------------------
    # Competes :: System Cost
    # ----------------------------------------------------------
    plt.figure(figsize=(8,5))

    plt.bar(
        df_competes["case"],
        df_competes["objective"] / 1e6
    )

    plt.title(
        "BYOG Competes :: System Cost"
    )

    plt.ylabel(
        "System Cost ($M)"
    )

    plt.xticks(
        rotation=45
    )

    plt.tight_layout()

    plt.savefig(
        Path(DEMO_PLOTS_DIR)
        / "byog_competes_cost.png"
    )

    plt.close()

    # ----------------------------------------------------------
    # Competes :: Profit Proxy
    # ----------------------------------------------------------
    df_competes[
        "profit_proxy"
    ] = (
        df_competes["dc_dispatch_mw"]
        *
        df_competes["byog_mc"]
    )

    plt.figure(figsize=(8,5))

    plt.bar(
        df_competes["case"],
        df_competes["profit_proxy"]
    )

    plt.title(
        "BYOG Competes :: Profit Proxy"
    )

    plt.ylabel(
        "Dispatch MW × BYOG MC"
    )

    plt.xticks(
        rotation=45
    )

    plt.tight_layout()

    plt.savefig(
        Path(DEMO_PLOTS_DIR)
        / "byog_competes_profit.png"
    )

    plt.close()

    # ----------------------------------------------------------
    # Complements :: LMP Spread
    # ----------------------------------------------------------
    plt.figure(figsize=(8,5))

    plt.bar(
        df_complements["case"],
        df_complements["lmp_spread"]
    )

    plt.title(
        "BYOG Complements :: LMP Spread"
    )

    plt.ylabel(
        "LMP Spread"
    )

    plt.xticks(
        rotation=45
    )

    plt.tight_layout()

    plt.savefig(
        Path(DEMO_PLOTS_DIR)
        / "byog_complements_lmp.png"
    )

    plt.close()

    # ----------------------------------------------------------
    # Complements :: System Cost
    # ----------------------------------------------------------
    plt.figure(figsize=(8,5))

    plt.bar(
        df_complements["case"],
        df_complements["objective"] / 1e6
    )

    plt.title(
        "BYOG Complements :: System Cost"
    )

    plt.ylabel(
        "System Cost ($M)"
    )

    plt.xticks(
        rotation=45
    )

    plt.tight_layout()

    plt.savefig(
        Path(DEMO_PLOTS_DIR)
        / "byog_complements_cost.png"
    )

    plt.close()

    print(
        "\nGenerated:\n"
        "\tbyog_competes_cost.png\n"
        "\tbyog_competes_profit.png\n"
        "\tbyog_complements_lmp.png\n"
        "\tbyog_complements_cost.png\n"
    )

# ------------------------------------------------------------------------------
#   Refresh story plot references in generated dashboard
# ------------------------------------------------------------------------------
def refresh_demo_dashboard_plots():

    if not os.path.exists(DEMO_HTML):

        print(
            "\nERROR::Missing generated dashboard:\n"
            f"\t{DEMO_HTML}\n"
            "\nRun at least one scenario first.\n"
        )

        return

    required = [
        "byog_competes_cost.png",
        "byog_competes_profit.png",
        "byog_complements_lmp.png",
        "byog_complements_cost.png",
    ]

    missing = []

    for fn in required:

        fp = Path(DEMO_PLOTS_DIR) / fn

        if not fp.exists():
            missing.append(str(fp))

    if missing:

        print("\nERROR::Missing story plot images:\n")

        for m in missing:
            print(f"\t{m}")

        print("\nRun menu option 4 first.\n")

        return

    with open(
        DEMO_DASHBOARD_TEMPLATE,
        "r",
        encoding="utf-8"
    ) as f:

        template_html = f.read()

    start = template_html.find("<!-- STORY_PLOTS_BEGIN -->")
    end = template_html.find("<!-- STORY_PLOTS_END -->")

    if start < 0 or end < 0:

        print(
            "\nERROR::Story plot markers missing from demo_dashboard.html\n"
        )

        return

    story_block = template_html[
        start:end + len("<!-- STORY_PLOTS_END -->")
    ]

    with open(
        DEMO_HTML,
        "r",
        encoding="utf-8"
    ) as f:

        html = f.read()

    start = html.find("<!-- STORY_PLOTS_BEGIN -->")
    end = html.find("<!-- STORY_PLOTS_END -->")

    if start < 0 or end < 0:

        print(
            "\nERROR::Story plot markers missing from pypsa_zn_demo.html\n"
            "\nRun one scenario once to regenerate the dashboard, then rerun option 5.\n"
        )

        return

    html = (
        html[:start]
        + story_block
        + html[end + len("<!-- STORY_PLOTS_END -->"):]
    )

    with open(
        DEMO_HTML,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    print(
        "\nRefreshed story plot references in:\n"
        f"\t{DEMO_HTML}\n"
    )

# ------------------------------------------------------------------------------
#   CLI parser
# ------------------------------------------------------------------------------
def build_argparser() -> argparse.ArgumentParser:

    p = argparse.ArgumentParser()

    p.add_argument(
        "--preset",
        required=False,
        default=None,
        help="Demo preset name",
    )

    p.add_argument(
        "--master-csv-mode",
        action="store_true",
        help="Append results to master plot CSVs"
    )

    p.add_argument("--byog_mc", type=float, default=None)
    p.add_argument("--dc_p_nom", type=float, default=None)
    p.add_argument("--dc_p_set", type=float, default=None)

    return p

# ------------------------------------------------------------------------------
#   Demo preset enumeration
# ------------------------------------------------------------------------------
def print_demo_presets(presets: dict):

    print(SECTION_SEPARATOR)
    print("Available Demo Presets\n")

    families = {}

    for k in presets.keys():

        family = k.split("_case")[0]

        if family not in families:
            families[family] = []

        families[family].append(k)

    for fam, cases in families.items():

        print(f"{fam}::")

        for i, c in enumerate(cases, start=1):
            print(f"  {i:2d}) {c}")

        print("")

    print("Example invocation:\n")

    first = sorted(presets.keys())[0]

    print(f"  python pypsa_zn_demo.py --preset {first}\n")

    print(SECTION_SEPARATOR)

# ------------------------------------------------------------------------------
#   Purge demo_out runtime artifacts
# ------------------------------------------------------------------------------
def purge_demo_out():

    demo_out = Path(DEMO_OUTDIR)

    if not demo_out.exists():
        return

    for f in demo_out.glob("*"):

        try:

            if f.is_file():
                f.unlink()

        except Exception:
            pass

# ------------------------------------------------------------------------------
#   Start demo HTTP server
# ------------------------------------------------------------------------------
def start_demo_http_server():

    os.chdir(SCRIPT_DIR)

    httpd = TCPServer(
        ("localhost", DEMO_SERVER_PORT),
        DemoHTTPRequestHandler
    )

    t = threading.Thread(
        target=httpd.serve_forever,
        daemon=True
    )

    t.start()

    return httpd

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------
def main():
    print(SECTION_SEPARATOR)
    print("ZeroNode Demo Runner...\n")

    cli_args = build_argparser().parse_args()

    global MASTER_CSV_MODE

    if cli_args.master_csv_mode:

        MASTER_CSV_MODE = True

    # ------------------------------------------------------------------
    # Demo UX mode selection
    #
    # If preset explicitly supplied:
    #   -> force CLI execution mode
    #
    # Otherwise:
    #   -> operator chooses interactive vs CLI
    # ------------------------------------------------------------------
    if cli_args.preset is not None:
        server_mode = False
    else:
        print(
            "\nSelect Demo Mode:\n"
            "\n"
            "  1) Interactive Demo Landing Page\n"
            "  2) CLI Researcher / Preset Mode\n"
            "  3) Build Master CSVs\n"
            "  4) Generate Story Plots\n"
            "  5) Refresh Story Plots in Dashboard\n"
            "  0) Exit\n"
        )

        mode_choice = input(
            "Enter choice [1]: "
        ).strip()

        if mode_choice == "2":

            server_mode = False

        elif mode_choice == "3":

            print(
                "\nWARNING:\n"
                "\n"
                "This will delete:\n"
                "\tplots/byog_competes.csv\n"
                "\tplots/byog_complements.csv\n"
                "\n"
                "before rebuilding master CSVs.\n"
            )

            ok = input(
                "Enter 'OK' to continue [N | (any key) aborts]: "
            ).strip()

            if ok.upper() != "OK":

                print(
                    "\nAborted.\n"
                )

                return

            purge_master_plot_artifacts()

            MASTER_CSV_MODE = True

            server_mode = True

        elif mode_choice == "4":

            print(
                "\nWARNING:\n"
                "\n"
                "This will delete:\n"
                "\n"
                "\tbyog_competes_cost.png\n"
                "\tbyog_competes_profit.png\n"
                "\tbyog_complements_lmp.png\n"
                "\tbyog_complements_cost.png\n"
            )

            ok = input(
                "Enter 'OK' to continue [N | (any key) aborts]: "
            ).strip()

            if ok.upper() != "OK":

                print(
                    "\nAborted.\n"
                )

                return

            generate_story_plots()

            return

        elif mode_choice == "5":

            refresh_demo_dashboard_plots()

            return

        elif mode_choice == "0":

            print(
                "\nExiting.\n"
            )

            return

        else:

            server_mode = True

    presets = load_demo_presets()

    # ------------------------------------------------------------------
    # Start local demo server ONLY in launcher mode
    # ------------------------------------------------------------------
    if server_mode:
        # ------------------------------------------------------------------
        # Start each demo session from a clean runtime state
        # ------------------------------------------------------------------
        purge_demo_out()

        start_demo_http_server()
        landing_url = (
            f"http://localhost:{DEMO_SERVER_PORT}/"
            "pypsa_zn_demo_land.html"
        )
        write_demo_landing_page(presets)
        webbrowser.open(landing_url)
        print(SECTION_SEPARATOR)
        print("ZeroNode Interactive Demo Mode...\n")
        print(
            "Landing page:\n"
            f"\t{landing_url}\n"
        )
        print(
            "Use browser scenario buttons to execute presets.\n"
        )
        print(
            "Press Ctrl+C in this terminal to stop demo server.\n"
        )
        print(SECTION_SEPARATOR)

        # ------------------------------------------------------------------
        # Keep interactive server alive
        # ------------------------------------------------------------------
        try:
            while True:
                pass
        except KeyboardInterrupt:
            print("\nShutting down demo server...\n")
        return
    
    # ------------------------------------------------------------------
    # Enumerate presets if no explicit preset supplied
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # CLI demo mode
    # ------------------------------------------------------------------
    if (
        cli_args.preset is None
        and not server_mode
    ):

        print(
            "\nCLI Mode:\n"
            "\n"
            "  1) Accumulate demo_out artifacts\n"
            "  2) Purge demo_out and start fresh\n"
        )

        choice = input(
            "Enter choice [1]: "
        ).strip()

        if choice == "2":

            purge_demo_out()

            print(
                "\nASR-DBG::demo_out purged\n"
            )

        print_demo_presets(presets)

        return

    if cli_args.preset not in presets:

        print(f"\nERROR: Unknown preset:\n\t{cli_args.preset}\n")

        print_demo_presets(presets)
        return

    preset = presets[cli_args.preset]

    validate_preset(cli_args.preset, preset)

    Path(DEMO_OUTDIR).mkdir(parents=True, exist_ok=True)

    print(f"ASR-DBG::Loading DevNet::\n\t{DEVNET_BLD_PATH}\n")
    devnet = load_devnet()

    args = build_runtime_args(cli_args, preset)

    print("ASR-DBG::Demo args::")
    print(f"\tpreset      = {cli_args.preset}")
    print(f"\tk_load      = {args.k_load}")
    print(f"\tbyog_mc     = {args.byog_mc}")
    print(f"\tdc_p_nom    = {args.dc_p_nom}")
    print(f"\tdc_p_set    = {args.dc_p_set}")
    print(f"\toutdir      = {args.outdir}\n")

    result = dsl.run_commit(
        devnet,
        args,
        DEVNET_NAME,
        use_http_paths=server_mode
    )

    if MASTER_CSV_MODE:

        build_master_plot_csvs(
            cli_args.preset,
            args,
            result["dash"]
        )

    else:

        append_runtime_plot_row(
            cli_args.preset,
            args,
            result["dash"]
        )

    print(result["dashboard_text"], end="")
    print(f"Commit id:\t{result['commit_id']}")
    print(f"HTML report:\t{result['index_path']}")

    demo_html = write_demo_html(result, args, cli_args.preset)

    print(f"Demo HTML:\t{demo_html}")
    print(SECTION_SEPARATOR)

# ------------------------------------------------------------------------------
#   Entrypoint
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()

# ------------------------------------------------------------------------------
# END OF pypsa_zn_demo.py
# ------------------------------------------------------------------------------