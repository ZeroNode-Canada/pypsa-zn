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

# ercot7k_build.py
#
# Purpose
#   Operator front end for the ERCOT Texas7k derived-case writer. Reads the
#   user-editable CSVs in ercot7k_config/, expands them into a delta list, and
#   asks ercot7k_case.py to emit one new case layer under ercot7k-derived/.
#
#   This script holds NO table logic. Every merge rule, every byte-fidelity
#   guarantee and every one of the V1-V13 checks lives in ercot7k_case.py, which
#   is importable-only and silent. What lives here is the house style: the
#   banner, the confirm() gates, the Tee log, the sanity report and the one line
#   to paste into pso.local.toml. If a rule about a PSO table seems to be in
#   this file, it is in the wrong file.
#
# What it does
#   - --init generates the ercot7k_config/ CSV templates, asking before it
#     overwrites anything.
#   - Lists the base case and every existing derived layer and asks which one to
#     build on, so a chain can be stacked a layer at a time.
#   - Builds either a datacenter layer (ercot7k_dc.csv) or a stress layer
#     (ercot7k_stress.csv, tall: one row per lever).
#   - Prints a sanity report BEFORE the write gate: base case summary, the
#     resolved datacenter node with its voltage class and whether it sits on a
#     Monitor=1 branch, the datacenter MW against the base forecast peak, and
#     BYOG coverage as a fraction of the datacenter load.
#   - Runs verify_case() through ercot7k_case.write_layer(), prints every
#     finding, and refuses to emit a layer that produced an ERROR.
#
# Outputs
#   - ercot7k-derived/<parent>__<slug>/ (a complete PSO case directory)
#   - ercot7k-derived/<parent>__<slug>/pso_case_manifest.json
#   - ercot7k-derived/<parent>__<slug>/logs/ercot7k_build_<TS>.log
#
# Run: python ercot7k_build.py [--init]
# ------------------------------------------------------------------------------

import io
import logging
import os
import shutil
import sys
from datetime import datetime

import pandas as pd

import ercot7k_case as ec

# Global defines
SECTION_SEPARATOR = "="*80 + "\n"  # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n"  # for print separation

print(SECTION_SEPARATOR)
print("ERCOT Texas7k Derived Case Builder...\n")

# ----- Resolve paths next to this script -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TS = datetime.now().strftime("%Y%m%d-%H%M%S")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "ercot7k_config")
DERIVED_ROOT = os.path.join(SCRIPT_DIR, "ercot7k-derived")
BASE_CASE_PATH = os.path.join(SCRIPT_DIR, "ercot7k")

DC_CSV = "ercot7k_dc.csv"
STRESS_CSV = "ercot7k_stress.csv"

# Set by build() once a layer is on disk, and read only by the teardown block at
# the bottom, which copies this run's log into <layer>/logs/. It stays None on
# every path that wrote nothing.
WRITTEN_LAYER = None

USAGE = (
    "Usage: python ercot7k_build.py [--init | --show-config [DIR] | --help]\n"
    "\n"
    "  (no arguments)  build one derived case layer, interactively\n"
    "  --init          generate the ercot7k_config/ CSV templates\n"
    "  --show-config   print the ACTIVE rows of the config CSVs and exit,\n"
    "                  so the '# Previous Values' cut is visible before a\n"
    "                  build rather than inferred from the result\n"
    "  --help          print this text\n"
)


# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt: str) -> bool:
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")


# ------------------------------------------------------------------------------
# read_active_config_csv()
#
# COPIED VERBATIM from devnetDC_sld.py. It cannot be imported: devnetDC_sld.py
# executes on import -- it prints a banner, prompts for a DevNet name, creates
# directories and replaces sys.stdout -- so importing it to reach one 12-line
# helper would hang this script before it started. A shared lib/ home is the
# right eventual fix; the 7k track does not touch lib/.
#
# Reads the active portion of a configuration CSV. The first row whose first
# column contains
#     # Previous Values
# marks the end of the active configuration; every row below it is ignored. That
# is what lets an operator keep the previous experiment's numbers in the same
# file instead of maintaining copies.
# ------------------------------------------------------------------------------
def read_active_config_csv(csv_path):
    """
    Read only the active section of a config CSV.

    Any row whose first column contains:
        # Previous Values

    terminates the active configuration.
    Everything below that row is ignored.
    """
    df = pd.read_csv(csv_path, dtype=str)

    if df.empty:
        return df

    first_col = df.columns[0]

    marker = (
        df[first_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("# Previous Values")
    )

    if marker.any():
        marker_idx = marker[marker].index[0]
        df = df.loc[: marker_idx - 1]

    df = df.dropna(how="all")

    return df


# ------------------------------------------------------------------------------
# config_rows()
#
# read_active_config_csv() hands back a str-typed frame in which an empty CSV
# field is NaN, not "". Every consumer downstream compares strings -- a blank
# target is a MEANINGFUL value for the k_load lever -- so the NaNs are filled
# here, once, rather than in each caller.
# ------------------------------------------------------------------------------
def config_rows(csv_path: str) -> list:
    df = read_active_config_csv(csv_path)
    if df.empty:
        return []
    return df.fillna("").astype(str).to_dict("records")


# ------------------------------------------------------------------------------
# write_csv_if_allowed()
#
# The devnet_cfg.py pattern: existence check, then confirm() before overwrite. A
# config CSV holds an operator's edits, so it is never silently replaced.
# ------------------------------------------------------------------------------
def write_csv_if_allowed(path: str, df: pd.DataFrame) -> None:
    if os.path.exists(path):
        print(f"AMW-DBG: Found existing CSV:\n\t{path}")
        if not confirm("Overwrite this CSV?"):
            print("AMW-DBG: Keeping existing CSV.\n")
            return

    df.to_csv(path, index=False)
    print(f"AMW-DBG: Wrote CSV:\n\t{path}\n")


# ------------------------------------------------------------------------------
# init_config()
#
# Generates the two config templates.
#
# The active row of each template is a WORKING configuration, and the node is
# chosen for WHERE IT SITS ELECTRICALLY, not just for passing validation.
#
# N210144 is HEWITT 3, 345 kV, on 6 Monitor=1 branches, so a run straight after
# --init verifies clean. What earns it the default is the measurement: across
# the 168 RT intervals of the base run only SEVEN branches ever bind, and
# N210144_N210332_1 -- HEWITT <- RIESEL -- is the most persistent of them at
# 69/168. Flow on it runs Riesel to Hewitt against a binding limit, so Hewitt is
# the IMPORT-constrained side: LMP 48.018 there against 23.442 at Riesel across
# the constraint, the system minimum. Load added at Hewitt deepens a constraint
# that is already binding, which is what makes the asymptote reachable and BYOG
# worth anything.
#
# The previous default, N110126 (BAY CITY 3), was picked for validation alone.
# It is a real 345 kV node on monitored branches and it verifies clean, but it
# never appears in the binding set at all, so a datacenter there is simply
# served: no congestion response, no asymptote, and a BYOG unit with nothing to
# displace. It is kept below the marker as the "quiet node" control case.
#
# The design document's illustrative node N123456 does not exist in NDE_ID, so
# it too is kept below the "# Previous Values" marker where it documents the
# example without being read.
# ------------------------------------------------------------------------------
def init_config() -> int:
    print(SECTION_SEPARATOR)
    print("ERCOT Texas7k Config Generator...")
    print(SUBSECTION_SEPARATOR)

    print("This script will create default ercot7k CSV templates in:")
    print(f"\t{CONFIG_PATH}\n")

    print("After this step:")
    print("\t1. Edit the CSV files as needed.")
    print("\t2. Then re-run ercot7k_build.py to write a derived case layer.\n")

    if os.path.isdir(CONFIG_PATH):
        print(f"AMW-DBG: Found existing config folder:\n\t{CONFIG_PATH}\n")
    else:
        os.makedirs(CONFIG_PATH)
        print(f"AMW-DBG: Created config folder:\n\t{CONFIG_PATH}\n")

    input("Press Enter to generate / verify default CSV templates...\n")

    dc_df = pd.DataFrame([
        {"dc_name": "DC1", "node": "N210144", "p_set_mw": 1000,
         "byog_p_nom_mw": 500, "byog_max_mw": 500, "byog_mc": 65,
         "load_shape": "flat"},
        {"dc_name": "# Previous Values", "node": "", "p_set_mw": "",
         "byog_p_nom_mw": "", "byog_max_mw": "", "byog_mc": "",
         "load_shape": ""},
        # BAY CITY 3: verifies clean but never binds -- the quiet-node control.
        {"dc_name": "DC1", "node": "N110126", "p_set_mw": 1000,
         "byog_p_nom_mw": 500, "byog_max_mw": 500, "byog_mc": 65,
         "load_shape": "flat"},
        {"dc_name": "DC1", "node": "N123456", "p_set_mw": 1000,
         "byog_p_nom_mw": 500, "byog_max_mw": 500, "byog_mc": 65,
         "load_shape": "flat"},
    ])

    # Tall, not wide: a new lever adds a ROW. An operator who has never heard of
    # the new lever opens a file that still reads the way it did.
    stress_df = pd.DataFrame([
        {"lever": "k_load", "target": "", "mode": "scale", "value": 1.20},
        {"lever": "# Previous Values", "target": "", "mode": "", "value": ""},
        {"lever": "k_load", "target": "", "mode": "scale", "value": 1.10},
    ])

    print("AMW-DBG: Writing datacenter configuration "
          f"({DC_CSV})...")
    write_csv_if_allowed(os.path.join(CONFIG_PATH, DC_CSV), dc_df)
    print("AMW-DBG: Writing stress lever configuration "
          f"({STRESS_CSV})...")
    write_csv_if_allowed(os.path.join(CONFIG_PATH, STRESS_CSV), stress_df)

    print(SECTION_SEPARATOR)
    print("ercot7k CSV templates are ready.\n")
    print("Implemented stress levers:")
    for lever in sorted(ec.STRESS_LEVERS):
        entry = ec.STRESS_LEVERS[lever]
        print(f"\t{lever:10s} mode(s): {', '.join(entry['modes'])}")
        print(f"\t{'':10s} {entry['note']}")
    print("\nAn unrecognised lever is refused, never skipped.\n")
    print("Next step:")
    print(f"\tEdit CSVs in:\n\t{CONFIG_PATH}\n")
    print("Then run:")
    print("\tpython ercot7k_build.py\n")
    print(SECTION_SEPARATOR)
    return 0


# ------------------------------------------------------------------------------
# candidate_parents()
#
# The base case plus every derived layer already on disk. A layer is built on a
# parent, so stacking a datacenter layer and then a stress layer on top of it is
# two runs of this script, not one.
# ------------------------------------------------------------------------------
def candidate_parents() -> list:
    parents = []
    if os.path.isfile(os.path.join(BASE_CASE_PATH, "texas7k.csv")):
        parents.append(BASE_CASE_PATH)
    if os.path.isdir(DERIVED_ROOT):
        for name in sorted(os.listdir(DERIVED_ROOT)):
            path = os.path.join(DERIVED_ROOT, name)
            if os.path.isfile(os.path.join(path, "texas7k.csv")):
                parents.append(path)
    return parents


# ------------------------------------------------------------------------------
# slug_for_stress()
#
# A directory-safe name for a stress layer, built from the levers it applies, so
# that a chain reads from `ls` without opening a manifest. Dots become "p"
# because a directory name full of dots reads as a file extension.
# ------------------------------------------------------------------------------
def slug_for_stress(rows: list) -> str:
    parts = []
    for row in rows:
        lever = str(row.get("lever", "")).strip()
        value = str(row.get("value", "")).strip().replace(".", "p")
        parts.append(f"{lever}{value}")
    return "-".join(parts) or "stress"


# ------------------------------------------------------------------------------
# print_case_summary()
#
# The base case in the numbers an operator would use to recognise it. Nothing
# here has solved anything: the forecast peak is a SCHEDULE peak read from
# SCH_TMP, not served load.
# ------------------------------------------------------------------------------
def print_case_summary(summary: dict) -> None:
    print("Base case summary:")
    print(f"  nodes                {summary['nodes']:>10,d}")
    print(f"  branches             {summary['branches']:>10,d}")
    print(f"  injectors            {summary['injectors']:>10,d}")
    print(f"  schedules            {summary['schedules']:>10,d}")
    print(f"  horizon              {summary['min_date']} .. "
          f"{summary['max_date']}  ({summary['timepoints']} time points)")
    print(f"  cycle stack          {', '.join(summary['cycles'])}")
    print(f"  scenarios            {', '.join(summary['scenarios'])}")
    peak = summary["forecast_peak_mw"]
    if peak is None:
        print("  forecast peak        (no default-scenario area load schedule)")
    else:
        print(f"  forecast peak        {peak:>10,.1f} MW  "
              f"(schedule {summary['forecast_schedule']}, an INPUT peak)")
    print("")


# ------------------------------------------------------------------------------
# show_config()
#
# Prints the rows a build would actually read, after the "# Previous Values"
# cut. An operator keeps old parameter sets in the same file, so "which numbers
# are live" is a real question, and answering it by looking at the layer that
# came out is answering it too late.
#
# Takes an optional directory so the rule can be exercised against a scratch
# config without touching the operator's own.
# ------------------------------------------------------------------------------
def show_config(config_path: str) -> int:
    print(SECTION_SEPARATOR)
    print(f"AMW-DBG::ercot7k config path::\n\t{config_path}\n")
    if not os.path.isdir(config_path):
        print(f"AMW-ERR: config folder not found:\n\t{config_path}")
        return 2
    found = 0
    for name in (DC_CSV, STRESS_CSV):
        path = os.path.join(config_path, name)
        print(SUBSECTION_SEPARATOR)
        if not os.path.isfile(path):
            print(f"AMW-DBG: {name} is absent")
            continue
        found += 1
        rows = config_rows(path)
        print(f"AMW-DBG::{name}:: {len(rows)} active row(s)")
        for row in rows:
            print("\t" + ", ".join(f"{k}={v}" for k, v in row.items()))
    print(SUBSECTION_SEPARATOR)
    if not found:
        print("AMW-ERR: neither config CSV is present.")
        print("Run: python ercot7k_build.py --init")
        return 2
    print(SECTION_SEPARATOR)
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0
    if "--init" in args:
        return init_config()
    if "--show-config" in args:
        rest = args[args.index("--show-config") + 1:]
        return show_config(rest[0] if rest else CONFIG_PATH)
    unknown = [a for a in args if a not in ("--init", "--help", "-h")]
    if unknown:
        print(f"AMW-ERR: unrecognized argument(s): {', '.join(unknown)}")
        print(USAGE)
        return 2
    return build()


# ------------------------------------------------------------------------------
# build()
#
# The interactive path. Laid out in the order an operator reads it: config,
# parent, layer kind, sanity report, gate, write, verdict, and the line to paste
# into pso.local.toml.
# ------------------------------------------------------------------------------
def build() -> int:
    global WRITTEN_LAYER
    print(SECTION_SEPARATOR)
    print(f"AMW-DBG::ercot7k config path::\n\t{CONFIG_PATH}\n")

    if not os.path.isdir(CONFIG_PATH):
        print("AMW-ERR: ercot7k_config folder not found.")
        print("Run: python ercot7k_build.py --init")
        return 2

    csv_files = sorted(f for f in os.listdir(CONFIG_PATH) if f.endswith(".csv"))
    if not csv_files:
        print("AMW-ERR: No CSV files found in ercot7k_config.")
        print("Run: python ercot7k_build.py --init")
        return 2

    print("AMW-DBG::CSV files found:")
    for name in csv_files:
        print(f"\t{name}")
    print("")

    # ----- parent case -----
    parents = candidate_parents()
    if not parents:
        print(f"AMW-ERR: no case directory found at:\n\t{BASE_CASE_PATH}")
        return 2

    print("Select the parent case to build on:")
    for index, path in enumerate(parents, start=1):
        kind = "base" if path == BASE_CASE_PATH else "layer"
        print(f"  {index}) [{kind}] {os.path.relpath(path, SCRIPT_DIR)}")
    choice = input("Enter choice [1]: ").strip() or "1"
    if not choice.isdigit() or not 1 <= int(choice) <= len(parents):
        print(f"AMW-ERR: invalid choice {choice!r}")
        return 2
    parent_path = parents[int(choice) - 1]
    print(f"\nAMW-DBG::Parent case::\n\t{parent_path}\n")

    # ----- layer kind -----
    print("Select the layer to build:")
    print(f"  1) Datacenter layer   (from {DC_CSV})")
    print(f"  2) Stress layer       (from {STRESS_CSV})")
    kind_choice = input("Enter choice [1]: ").strip() or "1"
    if kind_choice not in ("1", "2"):
        print(f"AMW-ERR: invalid choice {kind_choice!r}")
        return 2

    tables = ec.read_case(parent_path)
    summary = ec.case_summary(tables)

    print(SECTION_SEPARATOR)
    print("ercot7k Derived Case Sanity Report...\n")
    print_case_summary(summary)

    if kind_choice == "1":
        spec, slug = _read_dc_spec()
        if spec is None:
            return 2
        if not _report_datacenter(tables, summary, spec):
            return 2
    else:
        rows, slug = _read_stress_rows()
        if rows is None:
            return 2
        if not _report_stress(rows):
            return 2

    # ----- write gate -----
    out_name = ec.layer_dir_name(parent_path, slug)
    out_path = os.path.join(DERIVED_ROOT, out_name)
    print(SUBSECTION_SEPARATOR)
    print(f"AMW-DBG::Layer directory::\n\t{out_path}\n")
    if os.path.exists(out_path):
        print(f"AMW-ERR: {out_name} already exists. A layer is written once; "
              "delete it or change the configuration.")
        return 2
    if not confirm("Write this layer?"):
        print("User aborted. Nothing was written.")
        return 0

    os.makedirs(DERIVED_ROOT, exist_ok=True)
    print(SECTION_SEPARATOR)
    print("Writing layer...\n")
    try:
        if kind_choice == "1":
            manifest = ec.build_datacenter_layer(parent_path, out_path, spec)
        else:
            manifest = ec.build_stress_layer(parent_path, out_path, rows,
                                             slug=slug)
    except ec.Ercot7kCaseError as exc:
        print(f"AMW-ERR: {exc}")
        return 1
    except NotImplementedError as exc:
        print(f"AMW-ERR: {exc}")
        return 1

    # ----- verdict -----
    WRITTEN_LAYER = out_path
    print(f"AMW-DBG::Layer id::\n\t{manifest['layer_id']}\n")
    print("Verification (V1-V13, no PSO run):")
    findings = [ec.Finding(**f) for f in manifest["verification"]["findings"]]
    print(ec.format_findings(findings))
    print("")
    warnings = [f for f in findings if f.level == ec.LEVEL_WARNING]
    for finding in warnings:
        print(f"AMW-DBG: WARNING {finding.check}: {finding.message}")
    if warnings:
        print("")

    case_line = f'case = "ercot7k-derived/{out_name}/texas7k.csv"'
    print(SECTION_SEPARATOR)
    print("Layer written. Paste this line into pso.local.toml, then run "
          "ercot7k_pso.py (menu option 12):\n")
    print(f"\t{case_line}\n")
    print(SECTION_SEPARATOR)
    return 0


# ------------------------------------------------------------------------------
# _read_dc_spec()
#
# One datacenter per layer. Multiple datacenters per layer are out of scope, so
# a config carrying more than one active row is refused rather than quietly
# using the first: the second row would be an operator's intent that the layer
# does not contain.
# ------------------------------------------------------------------------------
def _read_dc_spec():
    path = os.path.join(CONFIG_PATH, DC_CSV)
    if not os.path.isfile(path):
        print(f"AMW-ERR: {DC_CSV} not found in {CONFIG_PATH}")
        print("Run: python ercot7k_build.py --init")
        return None, ""
    rows = config_rows(path)
    if not rows:
        print(f"AMW-ERR: {DC_CSV} has no active rows")
        return None, ""
    if len(rows) > 1:
        print(f"AMW-ERR: {DC_CSV} has {len(rows)} active rows. One datacenter "
              "per layer; multiple datacenters per layer are out of scope. "
              "Move the others below a '# Previous Values' row.")
        return None, ""
    row = rows[0]
    try:
        spec = ec.DatacenterSpec(
            dc_name=row["dc_name"].strip(),
            node=row["node"].strip(),
            p_set_mw=float(row["p_set_mw"]),
            byog_p_nom_mw=float(row["byog_p_nom_mw"]),
            byog_max_mw=float(row["byog_max_mw"]),
            byog_mc=float(row["byog_mc"]),
            load_shape=(row.get("load_shape") or "flat").strip() or "flat",
        )
    except (KeyError, ValueError) as exc:
        print(f"AMW-ERR: {DC_CSV} row is not readable: {exc}")
        return None, ""
    return spec, spec.dc_name.lower()


# ------------------------------------------------------------------------------
# _report_datacenter()
#
# The sanity report for a datacenter layer. Everything here is a question an
# operator should have to answer NO to before the write gate, not after a solve.
# ------------------------------------------------------------------------------
def _report_datacenter(tables: dict, summary: dict, spec) -> bool:
    node = ec.node_report(tables, spec.node)
    print(SUBSECTION_SEPARATOR)
    print("Datacenter:")
    print(f"  name                 {spec.dc_name}")
    print(f"  load injector        {spec.load_injector}")
    print(f"  BYOG injector        {spec.byog_injector}")
    print(f"  p_set                {spec.p_set_mw:>10,.1f} MW (fixed dispatch, "
          "cannot curtail)")
    print(f"  byog_p_nom           {spec.byog_p_nom_mw:>10,.1f} MW (this run, "
          "SCN_INJ_MAX.MaxMw)")
    print(f"  byog_max_mw          {spec.byog_max_mw:>10,.1f} MW (study "
          "ceiling, INJ_ID.MaxMw)")
    print(f"  byog_mc              {spec.byog_mc:>10,.1f} $/MWh")
    print(f"  load_shape           {spec.load_shape}")
    print("")

    if not node["exists"]:
        print(f"AMW-ERR: node {spec.node} is not in NDE_ID.Enode. An injector "
              "mapped to an unknown node falls back to area load distribution, "
              "silently putting the datacenter somewhere else.")
        return False

    voltages = ", ".join(f"{v} kV" for v in node["voltages"]) or "(no branches)"
    print("Node:")
    print(f"  enode                {node['node']}")
    print(f"  name                 {node['name']}")
    print(f"  substation           {node['substation']}")
    print(f"  voltage class        {voltages}")
    print(f"  branches touching    {node['branches']} "
          f"({node['monitored_branches']} with Monitor=1)")
    print(f"  injectors already    {len(node['hosted_injectors'])}")
    if node["monitored_branches"] == 0:
        print("\nAMW-DBG: WARNING (V8) this node is touched only by Monitor=0 "
              "branches. When Monitor is not flagged, flows are not calculated "
              "and the limit is not enforced, so any congestion the datacenter "
              "creates here is never reported: the case looks clean and is "
              "wrong.")
    print("")

    peak = summary["forecast_peak_mw"]
    print("Proportions:")
    if peak:
        print(f"  DC load vs forecast peak   "
              f"{100.0 * spec.p_set_mw / peak:>8.2f} %  "
              f"({spec.p_set_mw:,.1f} of {peak:,.1f} MW)")
    else:
        print("  DC load vs forecast peak   (no forecast schedule to compare)")
    if spec.p_set_mw > 0:
        coverage = 100.0 * spec.byog_p_nom_mw / spec.p_set_mw
        print(f"  BYOG coverage of DC load   {coverage:>8.2f} %")
    else:
        coverage = 0.0
        print("  BYOG coverage of DC load   (p_set is zero)")
    if spec.byog_p_nom_mw <= spec.p_set_mw:
        print("  byog_p_nom <= p_set, so net injection at this node is never "
              "positive: the datacenter can never export.")
    else:
        print("  AMW-DBG: byog_p_nom > p_set, so this node can EXPORT. That is "
              "a generator sited behind a load, not a behind-the-meter "
              "datacenter; confirm it is intended.")
    print("")
    return True


# ------------------------------------------------------------------------------
# _read_stress_rows()
# ------------------------------------------------------------------------------
def _read_stress_rows():
    path = os.path.join(CONFIG_PATH, STRESS_CSV)
    if not os.path.isfile(path):
        print(f"AMW-ERR: {STRESS_CSV} not found in {CONFIG_PATH}")
        print("Run: python ercot7k_build.py --init")
        return None, ""
    rows = config_rows(path)
    if not rows:
        print(f"AMW-ERR: {STRESS_CSV} has no active rows")
        return None, ""
    return rows, slug_for_stress(rows)


def _report_stress(rows: list) -> bool:
    print(SUBSECTION_SEPARATOR)
    print("Stress levers (tall: one row per lever):")
    for row in rows:
        print(f"  {row.get('lever', ''):10s} target={row.get('target', '')!r:8s} "
              f"mode={row.get('mode', ''):8s} value={row.get('value', '')}")
    print("")
    print(f"Implemented levers: {', '.join(sorted(ec.STRESS_LEVERS))}. An "
          "unrecognised lever is refused, never skipped.\n")
    return True


# ------------------------------------------------------------------------------
#   Logging: Single-writer log (prints + logger all go through Tee)
#
#   The log is opened under ercot7k-derived/logs/ because the layer directory
#   cannot exist yet: write_layer() refuses an output directory that is already
#   there, which is what makes a layer write-once. Once the layer is on disk the
#   log is COPIED into <layer>/logs/ so it travels with the case it describes.
#   case_files() counts files, not directories, so a logs/ subdirectory is
#   invisible to the manifest hash and to V9 and V10.
# ------------------------------------------------------------------------------
class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = list(streams)  # list so remove() works safely

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


STAGING_LOG_DIR = os.path.join(DERIVED_ROOT, "logs")
os.makedirs(STAGING_LOG_DIR, exist_ok=True)
LOG_NAME = f"ercot7k_build_{TS}.log"
LOG_PATH = os.path.join(STAGING_LOG_DIR, LOG_NAME)
print("AMW-DBG::Log file::\n\t{0}\n".format(LOG_PATH))

_log_file_for_prints = open(LOG_PATH, "w", encoding="ascii")  # ONE file handle

# Keep original stdout & stderr handles to restore later
_orig_stdout, _orig_stderr = sys.stdout, sys.stderr

# Tee prints to console + log file (single writer)
sys.stdout = Tee(_orig_stdout, _log_file_for_prints)
sys.stderr = Tee(_orig_stderr, _log_file_for_prints)

# Configure logging to flow through sys.stdout (=> Tee => same log file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

print(f"Saving logs to: {LOG_NAME}")

# ------------------------------------------------------------------------------
#   Entry point
# ------------------------------------------------------------------------------
_rc = 1
try:
    _rc = main()
except EOFError:
    # Piped or closed stdin. Say so plainly instead of dumping a traceback: this
    # script is interactive by design and is launched from devnet_menu.py.
    print("\nAMW-ERR: stdin closed while waiting for input. ercot7k_build.py "
          "is interactive; run it from a terminal or from devnet_menu.py.")
    _rc = 2
except KeyboardInterrupt:
    print("\nUser terminated. Nothing was written.")
    _rc = 130

# ------------------------------------------------------------------------------
#   Teardown: move the log next to the case it describes, restore the streams
# ------------------------------------------------------------------------------
try:
    _log_file_for_prints.flush()
finally:
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()

if WRITTEN_LAYER and os.path.isdir(WRITTEN_LAYER):
    _target_dir = os.path.join(WRITTEN_LAYER, "logs")
    os.makedirs(_target_dir, exist_ok=True)
    shutil.copyfile(LOG_PATH, os.path.join(_target_dir, LOG_NAME))
    print(f"AMW-DBG: Log copied into the layer:\n\t"
          f"{os.path.join(_target_dir, LOG_NAME)}\n")

sys.exit(_rc)

# ------------------------------------------------------------------------------
# End of ercot7k_build.py
# ------------------------------------------------------------------------------
