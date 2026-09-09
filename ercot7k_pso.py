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

# ercot7k_pso.py
#
# Purpose
#   Run the ERCOT Texas7k (6717-bus) public PSO case full-cycle through PSO,
#   driven from Python via aimmspy, using the user's own AIMMS install and
#   license (e.g. an academic license via license_url). This is a sibling to
#   devnetDC_sld.py, not a replacement: it is PSO-only and never builds a
#   PyPSA network.
#
# What it does
#   - Loads pso.local.toml (via pso_config.py) as DEVNET_PSO_* env defaults.
#   - Resolves the PSO case (ercot7k/texas7k.csv by default), the PSO project
#     (PSO.aimms), and the AIMMS install to use.
#   - Prompts for a run name and creates per-run logs/ and results/ dirs.
#   - Opens the AIMMS project via aimmspy and runs the case through
#     StartupDataID() (SC -> DA -> RT cycle stack, per texas7k_CYC_ID.csv).
#   - Verifies the solve by reading peak served Load out of
#     results_ED_Ara.csv -- never trusts the return code alone.
#   - On failure, prints log/aimms.err and the tail of log/debuglog_*.txt
#     from the PSO model directory verbatim.
#
# Outputs
#   - <run-name>/logs/<run-name>_<TS>.log
#   - <run-name>/results/*.csv (results_ED_Ara.csv, results_MC_Solution.csv, ...)

# Run: ercot7k_pso.py
# ------------------------------------------------------------------------------

import csv
import glob
import importlib.util
import io
import os
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

# Global defines
SECTION_SEPARATOR = "="*80 + "\n"  # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n"  # for print separation

print(SECTION_SEPARATOR)
print("ERCOT Texas7k PSO Full-Cycle Runner Script...\n")

# ----- Resolve paths next to this script -----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

DEFAULT_CASE = os.path.join("ercot7k", "texas7k.csv")

# ------------------------------------------------------------------------------
#   Helper functions
# ------------------------------------------------------------------------------
def confirm(prompt: str) -> bool:
    ans = input(f"{prompt} (Y/N): ").strip().lower()
    return ans in ("y", "yes")

# ------------------------------------------------------------------------------
# native_path()
# Converts a path to a string with OS-NATIVE separators (backslashes on
# Windows), resolved to an absolute path.
#
# PSO 3.3 on Windows silently misreads a forward-slash SelectedDataFile /
# ResultsFile path: StartupDataID() returns fine and a full result set is
# written, but Load = 0 and every LMP pegs at the -1500 unserved-energy
# penalty. There is no error -- just a wrong, plausible-looking answer. Every
# path handed to aimmspy in this script goes through this function.
# ------------------------------------------------------------------------------
def native_path(p) -> str:
    return str(Path(p).resolve())

# ------------------------------------------------------------------------------
# read_mdl_horizon()
# Reads Name/StartDate/StopDate/TimeUnit/IntervalLength from an MDL_ID CSV so
# the pre-flight summary can show the horizon without invoking AIMMS.
# ------------------------------------------------------------------------------
def read_mdl_horizon(mdl_id_path: str) -> dict:
    with open(mdl_id_path, "r", newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    return row

# ------------------------------------------------------------------------------
# read_cyc_list()
# Reads the Cycle column from a CYC_ID CSV so the pre-flight summary can show
# the cycle stack (e.g. SC -> DA -> RT) without invoking AIMMS.
# ------------------------------------------------------------------------------
def read_cyc_list(cyc_id_path: str) -> list[str]:
    with open(cyc_id_path, "r", newline="", encoding="utf-8") as f:
        return [row["Cycle"] for row in csv.DictReader(f)]

# ------------------------------------------------------------------------------
# peak_served_load()
# Reads results_ED_Ara.csv from a results directory and returns PEAK served
# load in MW: Load summed over areas within an interval, maximised over
# intervals of the requested cycle.
#
# Note the file is one row per (cycle, scenario, area, interval), so a plain
# sum of the Load column would add SC + DA + RT together and integrate over
# the whole horizon -- ~17.9 million on this case, not a MW figure at all.
# Filtering to one cycle and peaking over intervals gives a real MW number:
# ~46,795 MW on the RT cycle of the shipped ercot7k week.
#
# Returns None if the file is missing (caller treats that as FAILED). This is
# the "verify a real value" check: a zero/missing peak is a failed run
# regardless of what StartupDataID()'s return value or the exit status say.
# ------------------------------------------------------------------------------
def peak_served_load(results_dir: str, cycle: str = "") -> float | None:
    path = os.path.join(results_dir, "results_ED_Ara.csv")
    if not os.path.isfile(path):
        return None

    with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []

        # The cycle column is the first field; PSO writes it comment-prefixed
        # (e.g. "//cyc"), so match on position rather than on a literal name.
        cyc_field = fields[0] if fields else ""
        by_interval = {}

        for row in reader:
            if cycle and cyc_field and row.get(cyc_field) != cycle:
                continue
            key = row.get("int") if "int" in fields else id(row)
            by_interval[key] = by_interval.get(key, 0.0) + float(row.get("Load", 0.0) or 0.0)

    return max(by_interval.values()) if by_interval else 0.0

# ------------------------------------------------------------------------------
# read_mc_solution()
# Summarises the solve: how many solves ran, and their Status breakdown.
#
# Deliberately does NOT report results_MC_Solution.csv's Objective column. That
# file holds one row per solve -- 190 of them on the shipped case -- so the
# first row is one horizon of one cycle, not the cost of the run. Printing it
# next to the word "Objective" invites reading a single horizon as the whole
# week. Cycle costs come from summarise_cycle_cost() instead.
# ------------------------------------------------------------------------------
def summarise_solves(results_dir: str) -> dict | None:
    path = os.path.join(results_dir, "results_MC_Solution.csv")
    if not os.path.isfile(path):
        return None

    status: dict[str, int] = {}

    with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            key = (row.get("Status") or "").strip() or "(blank)"
            status[key] = status.get(key, 0) + 1

    return {"solves": sum(status.values()), "status": status}

# ------------------------------------------------------------------------------
# summarise_cycle_cost()
# Sums results_MC_Hrzn.csv DeltaCost per cycle.
#
# DeltaCost is the cost of the periods inside a horizon's DeltaTime, i.e. the
# non-overlapping slice. Summing it is meaningful where summing per-solve
# objectives is not, because SC and DA horizons overlap their look-ahead.
# ------------------------------------------------------------------------------
def summarise_cycle_cost(results_dir: str) -> dict[str, float]:
    path = os.path.join(results_dir, "results_MC_Hrzn.csv")
    if not os.path.isfile(path):
        return {}

    totals: dict[str, float] = {}

    with open(path, "r", newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        cyc_field = (reader.fieldnames or [""])[0]

        for row in reader:
            cyc = (row.get(cyc_field) or "").strip()
            totals[cyc] = totals.get(cyc, 0.0) + float(row.get("DeltaCost", 0.0) or 0.0)

    return totals

# ------------------------------------------------------------------------------
# print_pso_error_logs()
# On a failed / exception-raising run, prints the PSO model directory's
# log/aimms.err verbatim (the real cause of a PSO failure never appears in the
# Python exception) plus the tail of the most recent log/debuglog_*.txt.
# ------------------------------------------------------------------------------
def print_pso_error_logs(project_path: str) -> None:
    model_dir = os.path.dirname(project_path)
    log_dir = os.path.join(model_dir, "log")

    err_path = os.path.join(log_dir, "aimms.err")
    print(SUBSECTION_SEPARATOR)
    if os.path.isfile(err_path):
        print(f"ASR-ERR: contents of {err_path}:\n")
        with open(err_path, "r", encoding="utf-8", errors="replace") as f:
            print(f.read())
    else:
        print(f"ASR-ERR: no aimms.err found at {err_path}")

    debuglogs = sorted(glob.glob(os.path.join(log_dir, "debuglog_*.txt")))
    if debuglogs:
        latest = debuglogs[-1]
        print(f"\nASR-ERR: tail of {latest}:\n")
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in lines[-60:]:
            print(line, end="")
        print()
    else:
        print(f"\nASR-ERR: no debuglog_*.txt found in {log_dir}")
    print(SUBSECTION_SEPARATOR)

# ------------------------------------------------------------------------------
#   Load pso.local.toml -> DEVNET_PSO_* env defaults (must precede reading
#   any DEVNET_PSO_* var below).
# ------------------------------------------------------------------------------
sys.path.insert(0, SCRIPT_DIR)
try:
    import pso_config
    pso_config.load_config()
except Exception as e:
    print(f"ASR-DBG: pso_config.load_config() failed ({e}); continuing on plain env vars.")

# ------------------------------------------------------------------------------
#   Resolve config (env-only from here -- config-error path must not require
#   aimmspy, so the import stays below this block).
# ------------------------------------------------------------------------------
PROJECT = os.environ.get("DEVNET_PSO_PROJECT")
CASE = os.environ.get("DEVNET_PSO_CASE") or DEFAULT_CASE
AIMMS_PATH = os.environ.get("DEVNET_PSO_AIMMS_PATH")
AIMMS_VERSION = os.environ.get("DEVNET_PSO_AIMMS_VERSION")
LICENSE_URL = os.environ.get("DEVNET_PSO_LICENSE_URL")

if not PROJECT:
    print("ASR-ERR: DEVNET_PSO_PROJECT is not set (path to PSO.aimms).")
    print("Copy pso.local.toml.example -> pso.local.toml at the repo root and set 'project',")
    print("or set the DEVNET_PSO_PROJECT environment variable directly.")
    sys.exit(1)

if not os.path.isabs(CASE):
    CASE = os.path.join(SCRIPT_DIR, CASE)

if not os.path.isfile(CASE):
    sys.exit(f"ASR-ERR: case file not found: {CASE}")
if not os.path.isfile(PROJECT):
    sys.exit(f"ASR-ERR: PSO project not found: {PROJECT} (set DEVNET_PSO_PROJECT)")

# Normalize BEFORE anything is handed to aimmspy -- see native_path().
PROJECT = native_path(PROJECT)

# ------------------------------------------------------------------------------
#   aimmspy availability, and re-launch into the solve interpreter if needed.
#
#   devnet_menu.py runs every script with sys.executable, i.e. whichever
#   interpreter started the menu -- the PyPSA environment. aimmspy cannot live
#   there: its dependencies force linopy down and break PyPSA's n.optimize (see
#   the note in pyproject.toml), so the two need separate environments. Set
#   'python' in pso.local.toml to the interpreter that has aimmspy and this
#   script re-launches itself there.
#
#   Checked here, before the run-name prompt and before the log file is opened,
#   so a missing aimmspy fails in a second instead of three prompts later.
# ------------------------------------------------------------------------------
SOLVE_PYTHON = os.environ.get("DEVNET_PSO_PYTHON")

try:
    _has_aimmspy = importlib.util.find_spec("aimmspy") is not None
except Exception:
    _has_aimmspy = False

if not _has_aimmspy:
    if SOLVE_PYTHON and os.path.isfile(SOLVE_PYTHON) and not os.environ.get("DEVNET_PSO_RELAUNCHED"):
        print("ASR-DBG: aimmspy not in this interpreter; re-launching under:")
        print(f"\t{SOLVE_PYTHON}\n")
        os.environ["DEVNET_PSO_RELAUNCHED"] = "1"
        sys.exit(subprocess.call([SOLVE_PYTHON, os.path.abspath(__file__)] + sys.argv[1:]))

    print("ASR-ERR: aimmspy is not available in this interpreter:")
    print(f"\t{sys.executable}\n")
    print("aimmspy ships with AIMMS and cannot share an environment with PyPSA.")
    print("Set 'python' in pso.local.toml (or DEVNET_PSO_PYTHON) to the interpreter")
    print("that has aimmspy installed, or run this script with that interpreter directly.")
    sys.exit(1)

# ------------------------------------------------------------------------------
#   Prompt for run name; create per-run logs/ and results/ dirs.
# ------------------------------------------------------------------------------
default_run = "ercot7k-run"
user_input = input(f"Enter run name [{default_run}]: ").strip()
RUN_NAME = user_input if user_input else default_run

# Keep run output out of the tracked case directory and out of nested paths.
if os.sep in RUN_NAME or "/" in RUN_NAME or RUN_NAME == os.path.dirname(DEFAULT_CASE):
    sys.exit(f"ASR-ERR: invalid run name '{RUN_NAME}' -- use a plain name, "
             f"not a path and not '{os.path.dirname(DEFAULT_CASE)}' (the case directory).")

print(f"ASR-DBG::Using RUN_NAME::\n\t{RUN_NAME}\n")

RUN_PATH = os.path.join(SCRIPT_DIR, RUN_NAME)
LOG_PATH = os.path.join(RUN_PATH, "logs")
RESULTS_PATH = os.path.join(RUN_PATH, "results")

os.makedirs(LOG_PATH, exist_ok=True)
os.makedirs(RESULTS_PATH, exist_ok=True)

LOG_NAME = f"{RUN_NAME}_{TS}.log"
LOG_FILE = os.path.join(LOG_PATH, LOG_NAME)

# ------------------------------------------------------------------------------
#   Logging: Single-writer log (prints + logger all go through Tee)
#   Capture Python logging + print/stdout/stderr into file
# ------------------------------------------------------------------------------
_log_file_for_prints = open(LOG_FILE, "w", encoding="utf-8")  # ONE file handle

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

# Keep original stdout & stderr handles to restore later
_orig_stdout, _orig_stderr = sys.stdout, sys.stderr

# Tee prints to console + log file (single writer)
sys.stdout = Tee(_orig_stdout, _log_file_for_prints)
sys.stderr = Tee(_orig_stderr, _log_file_for_prints)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

print(f"Saving logs to: {LOG_NAME}")

# ------------------------------------------------------------------------------
#   Pre-flight summary (reads CSVs directly -- no AIMMS needed for this part)
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("ASR-DBG::Pre-flight summary::\n")
print(f"\tCase:         {CASE}")
print(f"\tProject:      {PROJECT}")
print(f"\tLicense URL:  {'(set)' if LICENSE_URL else '(machine default)'}")

case_dir = os.path.dirname(CASE)
mdl_id = os.path.join(case_dir, "texas7k_MDL_ID.csv")
cyc_id = os.path.join(case_dir, "texas7k_CYC_ID.csv")

if os.path.isfile(mdl_id):
    mdl = read_mdl_horizon(mdl_id)
    print(f"\tHorizon:      {mdl['StartDate']} -> {mdl['StopDate']}"
          f"  ({mdl['TimeUnit']}, interval {mdl['IntervalLength']})")
else:
    print(f"\tHorizon:      (could not read {mdl_id})")

if os.path.isfile(cyc_id):
    cycles = read_cyc_list(cyc_id)
    print(f"\tCycle stack:  {' -> '.join(cycles)}")
else:
    cycles = []
    print(f"\tCycle stack:  (could not read {cyc_id})")

# Last cycle in the stack (RT here) is the one the load check reports on.
REPORT_CYCLE = cycles[-1] if cycles else ""

print(f"\tResults dir:  {RESULTS_PATH}")
print(f"\tLog file:     {LOG_FILE}")
print()

if not confirm("Proceed with PSO solve"):
    print("User aborted before solve. Exiting...")
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    sys.exit(0)

# ------------------------------------------------------------------------------
#   Resolve AIMMS install + open the project (aimmspy imported only now, so
#   the config-error paths above never need it loaded).
# ------------------------------------------------------------------------------
os.environ["PSO_AIMMS_MODE"] = "Python"

from aimmspy.project.project import Project
from aimmspy.utils import find_aimms_path

# Resolve the AIMMS install: explicit path > pinned version > match aimmspy.
if AIMMS_PATH:
    aimms_path = AIMMS_PATH
elif AIMMS_VERSION:
    aimms_path = find_aimms_path(AIMMS_VERSION)
else:
    # Default: match the AIMMS runtime to the installed aimmspy major.minor
    # (e.g. aimmspy 26.1.x -> AIMMS 26.1), not blindly the newest install.
    try:
        import aimmspy
        _mm = ".".join(str(aimmspy.__version__).split(".")[:2])
        aimms_path = find_aimms_path(_mm)
    except Exception:
        aimms_path = find_aimms_path()

# Normalize the resolved install path too -- native_path() applies to every
# path handed to aimmspy, not just the case and results files.
if aimms_path:
    aimms_path = native_path(aimms_path)

project_kwargs = {"aimms_path": aimms_path, "aimms_project_file": PROJECT}
if LICENSE_URL:
    project_kwargs["license_url"] = LICENSE_URL

print(SECTION_SEPARATOR)
print(f"ASR-DBG::Opening AIMMS project::\n\taimms_path={aimms_path}\n\tproject={PROJECT}"
      f"\n\tlicense_url={'(set)' if LICENSE_URL else '(machine default)'}\n")

project = Project(**project_kwargs)
aimms_model = project.get_model(__file__)

# ------------------------------------------------------------------------------
#   Assign case / results paths and run.
#
#   native_path() converts to OS-native separators -- see its docstring for
#   why a forward-slash path here is a silent Load=0 failure, not an error.
# ------------------------------------------------------------------------------
selected_data_file = native_path(CASE)
results_file = native_path(os.path.join(RESULTS_PATH, "results.csv"))

aimms_model.SelectedDataFile.assign(selected_data_file)
aimms_model.ResultsFile.assign(results_file)
aimms_model.FileOptionString.assign("CSV text")

print(f"ASR-DBG::SelectedDataFile::\n\t{selected_data_file}\n")
print(f"ASR-DBG::ResultsFile::\n\t{results_file}\n")

print(SECTION_SEPARATOR)
print("ASR-DBG::StartupDataID()::\n")

run_failed = False
try:
    aimms_model.StartupDataID()
    print("ASR-DBG: StartupDataID returned OK\n")
except Exception as e:
    print(f"ASR-ERR: StartupDataID raised: {e}\n")
    print_pso_error_logs(PROJECT)
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    raise

# ------------------------------------------------------------------------------
#   Verify a REAL value, never the return code: total served Load out of
#   results_ED_Ara.csv. A zero/missing total is FAILED regardless of what
#   StartupDataID() reported.
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("ASR-DBG::Verifying solve (results_ED_Ara.csv Load)::\n")

peak_load = peak_served_load(RESULTS_PATH, REPORT_CYCLE)
cycle_label = REPORT_CYCLE if REPORT_CYCLE else "all cycles"

if peak_load is None:
    print("ASR-ERR: results_ED_Ara.csv not found in results dir -- RUN FAILED.\n")
    run_failed = True
elif peak_load == 0:
    print("ASR-ERR: results_ED_Ara.csv Load peaks at 0 MW -- RUN FAILED "
          "(this is the classic forward-slash-path silent failure -- check "
          "SelectedDataFile/ResultsFile above used native separators).\n")
    run_failed = True
else:
    print(f"ASR-DBG: Peak served load ({cycle_label}) = {peak_load:,.1f} MW "
          f"-- solve looks real.\n")

if run_failed:
    print_pso_error_logs(PROJECT)

# ------------------------------------------------------------------------------
#   Results summary
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print(f"ASR-DBG::Result files written to {RESULTS_PATH}::\n")

result_files = sorted(Path(RESULTS_PATH).glob("*"))
for f in result_files:
    size_kb = f.stat().st_size / 1024
    print(f"\t{f.name:40s} {size_kb:12,.1f} KB")
print(f"\n\t{len(result_files)} file(s), "
      f"{sum(f.stat().st_size for f in result_files) / (1024*1024):,.1f} MB total\n")

solves = summarise_solves(RESULTS_PATH)
if solves:
    breakdown = ", ".join(f"{n} {s}" for s, n in sorted(solves["status"].items()))
    print(f"ASR-DBG::Solves (results_MC_Solution.csv)::\n"
          f"\t{solves['solves']} solve(s): {breakdown}\n")
else:
    print("ASR-DBG: results_MC_Solution.csv not found (no solve summary to report).\n")

costs = summarise_cycle_cost(RESULTS_PATH)
if costs:
    print("ASR-DBG::Cost by cycle (results_MC_Hrzn.csv, DeltaCost)::\n")
    for cyc in sorted(costs):
        print(f"\t{cyc:8s} {costs[cyc]:20,.3f}")
    print()
else:
    print("ASR-DBG: results_MC_Hrzn.csv not found (no cycle costs to report).\n")

print(SECTION_SEPARATOR)
if run_failed:
    print("ASR-ERR: RUN FAILED -- see aimms.err / debuglog above.\n")
else:
    print(f"ASR-DBG: RUN OK -- peak served load {peak_load:,.1f} MW ({cycle_label}).\n")

# ------------------------------------------------------------------------------
# --- Tear down (IMPORTANT: restore orig stdout, stderr handles, then close) ---
# ------------------------------------------------------------------------------
print("Tearing down logging redirection...")
sys.stdout = _orig_stdout
sys.stderr = _orig_stderr
_log_file_for_prints.close()

if run_failed:
    sys.exit(1)

# ------------------------------------------------------------------------------
# END OF ercot7k_pso.py
# ------------------------------------------------------------------------------
