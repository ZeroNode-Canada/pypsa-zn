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
#     DEVNET_PSO_RUN_NAME and DEVNET_PSO_ASSUME_YES answer the two interactive
#     gates for a batch driver (ercot7k_sweep.py); unset, both still prompt.
#   - Opens the AIMMS project via aimmspy and runs the case through
#     StartupDataID() (SC -> DA -> RT cycle stack, per texas7k_CYC_ID.csv).
#   - Verifies the solve by reading peak served Load out of
#     results_ED_Ara.csv -- never trusts the return code alone.
#   - On failure, prints what this run added to log/aimms.err plus the tail of
#     log/debuglog_*.txt from the PSO model directory.
#   - Times out if AIMMS never finishes opening, rather than hanging forever on
#     an AIMMS that failed to start (a missing solver library is the usual
#     cause). Override with DEVNET_PSO_OPEN_TIMEOUT.
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
import tempfile
import threading
import time
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
# Area "0" is PSO's system aggregate, not an area. A single-area case reports
# only that row; a case with an ARA_ID (the 2030 WA case: eight weather zones)
# reports the zones AND the aggregate, and summing every row double-counts --
# 165,184 MW where the real RT peak is 82,592. So an interval with an area-0
# row takes that row alone, and one without sums its areas.
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
        system_total = {}

        for row in reader:
            if cycle and cyc_field and row.get(cyc_field) != cycle:
                continue
            key = row.get("int") if "int" in fields else id(row)
            load = float(row.get("Load", 0.0) or 0.0)
            if row.get("ara") == "0":
                system_total[key] = system_total.get(key, 0.0) + load
            else:
                by_interval[key] = by_interval.get(key, 0.0) + load

    by_interval.update(system_total)
    return max(by_interval.values()) if by_interval else 0.0

# ------------------------------------------------------------------------------
# summarise_solves()
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
# aimms_err_size()
# Byte size of the PSO model's log/aimms.err, or 0 if absent.
#
# AIMMS APPENDS to aimms.err and never truncates it, so the file can hold the
# history of every case ever run against that project. Recording its size
# before the run lets the failure path print only what this run added, instead
# of replaying someone else's errors with the real cause buried at the end.
# ------------------------------------------------------------------------------
def aimms_err_size(project_path: str) -> int:
    err_path = os.path.join(os.path.dirname(project_path), "log", "aimms.err")
    return os.path.getsize(err_path) if os.path.isfile(err_path) else 0

# ------------------------------------------------------------------------------
# print_pso_error_logs()
# On a failed / exception-raising run, prints what this run appended to the PSO
# model directory's log/aimms.err (the real cause of a PSO failure never
# appears in the Python exception) plus the tail of the latest debuglog.
# ------------------------------------------------------------------------------
def print_pso_error_logs(project_path: str, err_offset: int = 0,
                         since: float = 0.0) -> None:
    model_dir = os.path.dirname(project_path)
    log_dir = os.path.join(model_dir, "log")

    err_path = os.path.join(log_dir, "aimms.err")
    print(SUBSECTION_SEPARATOR)
    if os.path.isfile(err_path):
        with open(err_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(err_offset)
            new_text = f.read()

        if new_text.strip():
            print(f"AMW-ERR: {err_path}, this run only:\n")
            print(new_text)
        else:
            print(f"AMW-ERR: {err_path} gained nothing during this run.")
            print("AIMMS appends to that file, so anything already in it is from")
            print("earlier runs and is not this failure.")
    else:
        print(f"AMW-ERR: no aimms.err found at {err_path}")

    # Only a debuglog this run actually wrote. The newest file in that
    # directory may belong to an entirely different case, and its tail then
    # reads as though it were this failure.
    debuglogs = [p for p in sorted(glob.glob(os.path.join(log_dir, "debuglog_*.txt")))
                 if os.path.getmtime(p) >= since]

    if debuglogs:
        latest = debuglogs[-1]
        print(f"\nAMW-ERR: tail of {latest}:\n")
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in lines[-60:]:
            print(line, end="")
        print()
    else:
        print(f"\nAMW-ERR: this run wrote no debuglog_*.txt in {log_dir}")
        print("(any older debuglog there belongs to a previous run, so it is not shown)")
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
    print(f"AMW-DBG: pso_config.load_config() failed ({e}); continuing on plain env vars.")

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
    print("AMW-ERR: DEVNET_PSO_PROJECT is not set (path to PSO.aimms).")
    print("Copy pso.local.toml.example -> pso.local.toml at the repo root and set 'project',")
    print("or set the DEVNET_PSO_PROJECT environment variable directly.")
    sys.exit(1)

if not os.path.isabs(CASE):
    CASE = os.path.join(SCRIPT_DIR, CASE)

if not os.path.isfile(CASE):
    sys.exit(f"AMW-ERR: case file not found: {CASE}")
if not os.path.isfile(PROJECT):
    sys.exit(f"AMW-ERR: PSO project not found: {PROJECT} (set DEVNET_PSO_PROJECT)")

# Normalize BEFORE anything is handed to aimmspy -- see native_path().
PROJECT = native_path(PROJECT)

# AIMMS appends to log/aimms.err and never truncates it, so note how big it is
# before this run touches anything. The failure path prints only what gets
# added past this point -- otherwise the real cause arrives buried under every
# earlier case run against the same PSO project.
ERR_OFFSET = aimms_err_size(PROJECT)

# Same reasoning for the debuglog: only one written after this instant belongs
# to this run.
RUN_START = time.time()

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
        print("AMW-DBG: aimmspy not in this interpreter; re-launching under:")
        print(f"\t{SOLVE_PYTHON}\n")
        os.environ["DEVNET_PSO_RELAUNCHED"] = "1"
        sys.exit(subprocess.call([SOLVE_PYTHON, os.path.abspath(__file__)] + sys.argv[1:]))

    print("AMW-ERR: aimmspy is not available in this interpreter:")
    print(f"\t{sys.executable}\n")
    print("aimmspy ships with AIMMS and cannot share an environment with PyPSA.")
    print("Set 'python' in pso.local.toml (or DEVNET_PSO_PYTHON) to the interpreter")
    print("that has aimmspy installed, or run this script with that interpreter directly.")
    sys.exit(1)

# ------------------------------------------------------------------------------
#   Prompt for run name; create per-run logs/ and results/ dirs.
#
#   Every run lands under ONE parent directory, RUNS_DIRNAME, rather than at the
#   repo root. A run writes 442 MB, and the run name is the operator's to
#   choose, so a root-level directory can only be ignored by guessing the name:
#   .gitignore listed "ercot7k-run*/" and the first run called anything else --
#   "kline90", say -- left 465 MB untracked in a repo whose README calls itself
#   clean after a run. One nested parent is one ignore rule that cannot be
#   out-guessed.
# ------------------------------------------------------------------------------
#   Both prompts below can be answered by environment instead, because
#   ercot7k_sweep.py drives this script once per sweep step and cannot answer a
#   prompt. Unset, nothing changes: the run name is still asked for and the
#   solve still has to be confirmed. They are deliberately two separate
#   variables -- a batch driver needs to name its run whether or not it is
#   skipping the gate, and a human piloting one case should be able to name it
#   without also disarming the confirmation.
RUNS_DIRNAME = "ercot7k-runs"

ENV_RUN_NAME = os.environ.get("DEVNET_PSO_RUN_NAME", "").strip()
ASSUME_YES = os.environ.get("DEVNET_PSO_ASSUME_YES", "").strip().lower() in (
    "1", "true", "yes", "y",
)

default_run = "ercot7k-run"
if ENV_RUN_NAME:
    RUN_NAME = ENV_RUN_NAME
    print(f"AMW-DBG: run name from DEVNET_PSO_RUN_NAME: {RUN_NAME}")
else:
    user_input = input(f"Enter run name [{default_run}]: ").strip()
    RUN_NAME = user_input if user_input else default_run

# Keep run output out of the tracked case directory and out of nested paths.
if os.sep in RUN_NAME or "/" in RUN_NAME or RUN_NAME == os.path.dirname(DEFAULT_CASE):
    sys.exit(f"AMW-ERR: invalid run name '{RUN_NAME}' -- use a plain name, "
             f"not a path and not '{os.path.dirname(DEFAULT_CASE)}' (the case directory).")

print(f"AMW-DBG::Using RUN_NAME::\n\t{RUN_NAME}\n")

# DEVNET_PSO_RUNS_ROOT relocates the whole parent, for a batch driver that wants
# its runs somewhere other than the repo (a scratch volume, say). It must stay in
# step with ercot7k_sweep.py's --runs-root: the sweep computes each step's
# results path from what it passed here, so a runner that ignored it would send
# the results somewhere the mapper does not look -- a solve that succeeds and
# then reads as a missing file.
RUNS_ROOT = os.environ.get("DEVNET_PSO_RUNS_ROOT", "").strip() or os.path.join(
    SCRIPT_DIR, RUNS_DIRNAME)

RUN_PATH = os.path.join(RUNS_ROOT, RUN_NAME)
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
print("AMW-DBG::Pre-flight summary::\n")
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

if ASSUME_YES:
    print("AMW-DBG: DEVNET_PSO_ASSUME_YES is set -- proceeding without the "
          "confirm gate.\n")
elif not confirm("Proceed with PSO solve"):
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
print(f"AMW-DBG::Opening AIMMS project::\n\taimms_path={aimms_path}\n\tproject={PROJECT}"
      f"\n\tlicense_url={'(set)' if LICENSE_URL else '(machine default)'}\n")

selected_data_file = native_path(CASE)
results_file = native_path(os.path.join(RESULTS_PATH, "results.csv"))

# aimmspy's get_model() uses its argument for exactly one thing: it writes a
# 3.8 MB editor stub of the PSO model's identifiers to <dir>/<basename>.pyi.
#
# Nothing here consumes that stub, and it is not a run artifact: it is
# byte-identical between runs and between cases, because it describes the AIMMS
# model rather than anything this script did. Passing __file__ dropped it in the
# repo root on every run -- untracked noise, and a stub that claims to type
# *this script* when it does nothing of the kind. Keeping a copy per run would
# just move the noise, so it goes to the OS temp directory and is not kept.
#
# There is no way to decline it. get_model()'s own default writes a hidden
# ".pyi" into the process working directory, which is worse than naming a path.
model_stub = os.path.join(tempfile.gettempdir(), "pso_model.pyi")


# ------------------------------------------------------------------------------
# open_and_handshake()
# Opens the AIMMS project and assigns the three model identifiers.
#
# Run under a timeout with a heartbeat. Opening a large PSO model is slow and
# silent, which reads as a hang -- and if AIMMS does fail to start, it prints
# its reason, exits, and every later aimmspy call blocks on a server that is no
# longer there. Either way the script used to sit there until it was killed
# from Task Manager. The heartbeat distinguishes "slow" from "stuck", and the
# timeout bounds the second case.
#
#   native_path() converts to OS-native separators -- see its docstring for
#   why a forward-slash path here is a silent Load=0 failure, not an error.
# ------------------------------------------------------------------------------
def open_and_handshake() -> None:
    global aimms_model

    project = Project(**project_kwargs)
    aimms_model = project.get_model(model_stub)

    aimms_model.SelectedDataFile.assign(selected_data_file)
    aimms_model.ResultsFile.assign(results_file)
    aimms_model.FileOptionString.assign("CSV text")


aimms_model = None

HEARTBEAT = 30.0

# ------------------------------------------------------------------------------
# run_with_heartbeat()
# Runs fn() on a worker thread, printing "<label> (Ns)..." every HEARTBEAT
# seconds, and gives up after timeout seconds (0 = wait indefinitely).
#
# Both phases of a PSO run are long and completely silent, which is
# indistinguishable from a hang at the console: opening compiles the model, and
# StartupDataID reads the case and solves it -- on the shipped ercot7k case
# that is close to six minutes during which the script prints two lines. The
# heartbeat is what stops someone reaching for Task Manager.
#
# Returns (finished, error). error is whatever fn() raised, for the caller to
# report and re-raise on the main thread.
# ------------------------------------------------------------------------------
def run_with_heartbeat(fn, label: str, timeout: float) -> tuple[bool, BaseException | None]:
    box: list[BaseException] = []

    def worker() -> None:
        try:
            fn()
        except BaseException as exc:
            box.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    waited = 0.0
    while thread.is_alive():
        remaining = (timeout - waited) if timeout > 0 else None

        if remaining is not None and remaining <= 0:
            break

        # Never wait past the deadline just because the heartbeat is coarser
        # than the time left.
        slice_s = HEARTBEAT if remaining is None else min(HEARTBEAT, remaining)
        thread.join(slice_s)

        if not thread.is_alive():
            break

        waited += slice_s

        if remaining is None or waited < timeout:
            print(f"AMW-DBG: {label} ({waited:.0f}s)...", flush=True)

    return (not thread.is_alive()), (box[0] if box else None)


# Generous by default: a cold first open compiles the PSO model, which is slow
# but finite. Override with DEVNET_PSO_OPEN_TIMEOUT (seconds; 0 disables).
OPEN_TIMEOUT = float(os.environ.get("DEVNET_PSO_OPEN_TIMEOUT", "600"))

_finished, _handshake_exc = run_with_heartbeat(
    open_and_handshake, "still opening AIMMS", OPEN_TIMEOUT
)
_handshake_error = [_handshake_exc] if _handshake_exc else []

if not _finished:
    print(f"\nAMW-ERR: AIMMS did not finish opening within {OPEN_TIMEOUT:.0f}s -- giving up.\n")
    print("Two possibilities, and AIMMS's own output above distinguishes them:\n")
    print("  1. It is genuinely still working. A cold first open compiles the PSO")
    print("     model, which is slow but finite. Raise DEVNET_PSO_OPEN_TIMEOUT")
    print(f"     (currently {OPEN_TIMEOUT:.0f}s) and try again.")
    print("  2. AIMMS failed to start and exited. It prints its reason before")
    print("     exiting, so scroll up to the lines after the --as-server command.\n")
    print("Note: 'Unable to load IBM CPLEX library. Exiting.' is NOT a reason to")
    print("stop here. AIMMS support describe it as harmless under aimmspy; it comes")
    print("from ODH-CPLEX being present in the solver configuration without a")
    print("licence for it, and the model still runs. Remove ODH-CPLEX from the")
    print("solver configuration to silence it, and keep looking for the real cause.\n")
    print_pso_error_logs(PROJECT, ERR_OFFSET, RUN_START)
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    os._exit(1)          # a live daemon thread blocks a normal interpreter exit

if _handshake_error:
    print(f"\nAMW-ERR: opening the AIMMS project raised: {_handshake_error[0]}\n")
    print_pso_error_logs(PROJECT, ERR_OFFSET, RUN_START)
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    raise _handshake_error[0]

print(f"AMW-DBG::SelectedDataFile::\n\t{selected_data_file}\n")
print(f"AMW-DBG::ResultsFile::\n\t{results_file}\n")

print(SECTION_SEPARATOR)
print("AMW-DBG::StartupDataID()::\n")

# The solve is the longest silent stretch of the run -- on the shipped ercot7k
# case it is close to six minutes in which nothing at all is printed. Run it
# under the same heartbeat so it is visibly working. No time limit by default:
# a legitimate solve is long and case-dependent, and killing one on a guess is
# worse than waiting. Set DEVNET_PSO_SOLVE_TIMEOUT to bound it.
SOLVE_TIMEOUT = float(os.environ.get("DEVNET_PSO_SOLVE_TIMEOUT", "0"))

run_failed = False

_solved, _solve_exc = run_with_heartbeat(
    aimms_model.StartupDataID, "still solving", SOLVE_TIMEOUT
)

if not _solved:
    print(f"\nAMW-ERR: StartupDataID did not finish within {SOLVE_TIMEOUT:.0f}s.\n")
    print("This is a time limit you set, not evidence that the solve is stuck --")
    print("raise or clear DEVNET_PSO_SOLVE_TIMEOUT to let it run.\n")
    print_pso_error_logs(PROJECT, ERR_OFFSET, RUN_START)
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    os._exit(1)          # a live daemon thread blocks a normal interpreter exit

if _solve_exc is not None:
    print(f"AMW-ERR: StartupDataID raised: {_solve_exc}\n")
    print_pso_error_logs(PROJECT, ERR_OFFSET, RUN_START)
    sys.stdout = _orig_stdout
    sys.stderr = _orig_stderr
    _log_file_for_prints.close()
    raise _solve_exc

print("AMW-DBG: StartupDataID returned OK\n")

# ------------------------------------------------------------------------------
#   Verify a REAL value, never the return code: total served Load out of
#   results_ED_Ara.csv. A zero/missing total is FAILED regardless of what
#   StartupDataID() reported.
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print("AMW-DBG::Verifying solve (results_ED_Ara.csv Load)::\n")

peak_load = peak_served_load(RESULTS_PATH, REPORT_CYCLE)
cycle_label = REPORT_CYCLE if REPORT_CYCLE else "all cycles"

if peak_load is None:
    print("AMW-ERR: results_ED_Ara.csv not found in results dir -- RUN FAILED.\n")
    run_failed = True
elif peak_load == 0:
    print("AMW-ERR: results_ED_Ara.csv Load peaks at 0 MW -- RUN FAILED "
          "(this is the classic forward-slash-path silent failure -- check "
          "SelectedDataFile/ResultsFile above used native separators).\n")
    run_failed = True
else:
    print(f"AMW-DBG: Peak served load ({cycle_label}) = {peak_load:,.1f} MW "
          f"-- solve looks real.\n")

if run_failed:
    print_pso_error_logs(PROJECT, ERR_OFFSET, RUN_START)

# ------------------------------------------------------------------------------
#   Results summary
# ------------------------------------------------------------------------------
print(SECTION_SEPARATOR)
print(f"AMW-DBG::Result files written to {RESULTS_PATH}::\n")

result_files = sorted(Path(RESULTS_PATH).glob("*"))
for f in result_files:
    size_kb = f.stat().st_size / 1024
    print(f"\t{f.name:40s} {size_kb:12,.1f} KB")
print(f"\n\t{len(result_files)} file(s), "
      f"{sum(f.stat().st_size for f in result_files) / (1024*1024):,.1f} MB total\n")

solves = summarise_solves(RESULTS_PATH)
if solves:
    breakdown = ", ".join(f"{n} {s}" for s, n in sorted(solves["status"].items()))
    print(f"AMW-DBG::Solves (results_MC_Solution.csv)::\n"
          f"\t{solves['solves']} solve(s): {breakdown}\n")
else:
    print("AMW-DBG: results_MC_Solution.csv not found (no solve summary to report).\n")

costs = summarise_cycle_cost(RESULTS_PATH)
if costs:
    print("AMW-DBG::Cost by cycle (results_MC_Hrzn.csv, DeltaCost)::\n")
    for cyc in sorted(costs):
        print(f"\t{cyc:8s} {costs[cyc]:20,.3f}")
    print()
else:
    print("AMW-DBG: results_MC_Hrzn.csv not found (no cycle costs to report).\n")

print(SECTION_SEPARATOR)
if run_failed:
    print("AMW-ERR: RUN FAILED -- see aimms.err / debuglog above.\n")
else:
    print(f"AMW-DBG: RUN OK -- peak served load {peak_load:,.1f} MW ({cycle_label}).\n")

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
