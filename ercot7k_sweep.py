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

# ercot7k_sweep.py
#
# Purpose
#   Sweep ONE stress lever across a range on the ERCOT Texas7k PSO case: build a
#   derived layer per step, solve it, map the results at the study's pinned
#   interval, and write one summary table for the whole sweep.
#
#   An importable module with a CLI, like ercot7k_results.py -- NOT an
#   interactive front end like ercot7k_build.py. A sweep is n solves of roughly
#   six minutes each; it has to be startable and then left alone, and every
#   choice it makes belongs on a command line that can be read back afterwards
#   rather than in a prompt nobody recorded.
#
#   The whole design question here is not "how do I loop" -- it is "how does
#   this sweep's own output prove the lever was applied". devnet's
#   run_sweep_line answers that question with nothing at all, and is wrong in
#   two independent ways (see THE TWO INHERITED DEFECTS below), so neither
#   failure is visible in its summary CSV. Every step here therefore carries a
#   WITNESS: a quantity read back out of the SOLVED results that can only move
#   if the lever reached the solver. A sweep whose witness never moves is
#   reported as a failed sweep, not as a flat response curve.
#
# What it does
#   - plan : print the steps, the witness, and the projected wall clock and
#            disk, then stop. The cheap way to find a bad range before an hour
#            of solving.
#   - run  : build + solve + map one layer per step, writing a step record as
#            each finishes, then the summary table and the verdict.
#   - check: re-run the verdict over an existing sweep directory's step
#            records, without solving anything.
#
# Outputs
#   - ercot7k-sweeps/<sweep_id>/sweep.json        the plan, written before step 1
#   - ercot7k-sweeps/<sweep_id>/step_<nn>.json    one per completed step
#   - ercot7k-sweeps/<sweep_id>/sweep_summary.csv the table
#   - ercot7k-sweeps/<sweep_id>/sweep_report.txt  the verdict
#   - ercot7k-sweeps/<sweep_id>/artifacts/        mapped artifacts per step
#   - ercot7k-derived/<parent>__<lever><value>/   one case layer per step
#   - ercot7k-runs/<sweep_id>-<nn>-<slug>/        one PSO run per step
#
# Run: python ercot7k_sweep.py plan --help
# ------------------------------------------------------------------------------
#
# THE TWO INHERITED DEFECTS
#
# Both are live in lib/devnet_stress_lib.py::run_sweep_line on main, both were
# reported to ZeroNode, and neither is inherited here. They are written out
# because "we avoided them" is worth nothing without saying what they were.
#
# 1. THE SWEEP DOES NOT APPLY THE SWEEP. Inside run_sweep_line's loop the only
#    corridor call is apply_corridor_reducers(n, parse_json_dict(args.k_line)) --
#    the loop variable k appears nowhere in it and is used ONLY to label the
#    output row. Every step solves the identical network while the summary
#    reports a moving k. Nothing in that CSV can distinguish it from a network
#    that genuinely does not respond.
#
#    Not inherited structurally: build_step_rows() puts the step value in the
#    one place the layer is built from, so a step that failed to apply it could
#    not produce a layer at all. Not inherited observably either: the witness
#    is read back from the results and checked against what the layer WROTE, so
#    the claim rests on a measurement rather than on the code being right.
#
# 2. DESCENDING SWEEPS DROP THEIR LAST POINT. np.arange(kmin, kmax + 1e-9,
#    kstep): the +1e-9 endpoint guard only helps an ASCENDING step, and every
#    preset in devnet_stress.py uses a negative one, so kmin=1.0 kmax=0.2
#    kstep=-0.1 yields 8 steps ending at 0.3 and silently never solves the
#    0.2 case -- the most interesting point of the sweep, and the reason the
#    sweep was run.
#
#    Not inherited: sweep_steps() counts steps as integers rather than
#    accumulating floats, includes both endpoints by construction in either
#    direction, and ASSERTS that the last step equals kmax before returning. A
#    range that is not a whole number of steps is refused rather than truncated,
#    because truncation is exactly this bug wearing a different hat.
# ------------------------------------------------------------------------------

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ercot7k_case as ec  # noqa: E402
import ercot7k_results as er  # noqa: E402

# Global defines
SECTION_SEPARATOR = "="*80 + "\n"  # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n"  # for print separation

DRIVER_ID = "ercot7k_sweep.py/1"
SWEEP_SCHEMA = "ercot7k-sweep/1"
STEP_SCHEMA = "ercot7k-sweep-step/1"

SWEEPS_DIRNAME = "ercot7k-sweeps"
DERIVED_DIRNAME = "ercot7k-derived"
RUNS_DIRNAME = "ercot7k-runs"
PSO_SCRIPT = "ercot7k_pso.py"

SWEEP_NAME = "sweep.json"
SUMMARY_NAME = "sweep_summary.csv"
REPORT_NAME = "sweep_report.txt"
ARTIFACTS_DIRNAME = "artifacts"

# Measured on the shipped case: 190 solves, 5.7 minutes, 442 MB of results per
# run. Used for the projection printed before a sweep starts, and superseded by
# the measured size of the first completed step -- see enough_disk_for_step(),
# which re-checks between steps so that a sweep stops before it fills the
# volume rather than after.
ESTIMATED_RUN_MB = 450.0
ESTIMATED_RUN_MINUTES = 6.0

# Free space the projection must leave behind, so a sweep cannot fill the disk
# it is writing to and take the rest of the machine with it.
DISK_MARGIN_MB = 2048.0

# Results print MW at three decimals, so an exact comparison has to allow the
# last printed digit. Relative tolerance carries the large numbers (area load
# runs to 46,000 MW); the absolute floor carries the small ones.
WITNESS_RTOL = 1e-6
WITNESS_ATOL = 5e-4

# Step values are rounded to this many decimals before they become both the
# CSV value and the directory slug, so that 1.0 - 3*0.1 is 0.7 rather than
# 0.7000000000000001 in a directory name and in a config field.
DEFAULT_DECIMALS = 4


class Ercot7kSweepError(Exception):
    """Base class for every error this module raises deliberately."""


# ------------------------------------------------------------------------------
#   The witness: what proves a step's lever reached the solver
# ------------------------------------------------------------------------------
# A witness is a quantity read out of the SOLVED results that is an INPUT ECHO
# of the lever -- PSO reporting back the number it was given. That is the point:
# a response variable moving proves the model did something, but only an input
# echo proves it did what the step asked. The campaign notes' whole finding was
# that a lever can be written, verified, solved and reported while changing
# nothing (SCN_BRN_LMT.ScaleFactor scales Schedule and Sequence, not the limit;
# an unmonitored branch has no flow computed at all), and every one of those
# reads as a clean run.
#
# kind:
#   absolute     -- the results carry the lever's value in the lever's own
#                   units, so the check is observed == what the layer wrote.
#                   The strongest available: it compares the case file against
#                   the result file and needs no reference step.
#   proportional -- the results carry a quantity that scales with the lever, so
#                   the check is observed[i]/observed[0] == value[i]/value[0].
#
# enforcement -- how W6 can ask "and was that value in the LP?", which is a
# different question per table and must not be answered by analogy:
#   bit          -- the results carry an explicit enforcement flag beside the
#                   limit (PN_Pth.MinEnforced/MaxEnforced).
#   respected    -- there is no flag because the limit is structural, so the
#                   evidence is that dispatch obeyed it: PSO's injector
#                   dispatch limits are soft slacks, so a cap reported and not
#                   applied shows as ED_Inj.LimitViolation.
#   none         -- the quantity is consumed unconditionally and the question
#                   does not arise (area load).
#
# Keyed by (lever, MODE), not by lever. k_gen writes three different tables
# depending on its mode, two of them sweepable and one not, and a witness chosen
# by lever alone would read SCN_INJ_MAX for a sweep that wrote SCN_INJ_OUT.
# ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Witness:
    kind: str
    column: str
    unit: str
    note: str
    enforcement: str = "none"


WITNESSES: Dict[Tuple[str, str], Witness] = {
    ("k_line", "scale"): Witness(
        kind="absolute",
        column="PN_Pth.Max",
        unit="MW",
        enforcement="bit",
        note=("the enforced flow limit on the derated branch at the pinned "
              "interval, which is BRN_ID.NormalLimit as this step's "
              "SCN_BRN_LMT row amended it"),
    ),
    ("k_load", "scale"): Witness(
        kind="proportional",
        column="ED_Ara.Load",
        unit="MW",
        enforcement="none",
        note=("fixed area load at the pinned interval, summed over areas. "
              "ED_Ara.Load is documented as unaffected by Violation, i.e. an "
              "input echo rather than served load, which is what makes it a "
              "witness and not a response"),
    ),
    ("k_gen", "derate"): Witness(
        kind="absolute",
        column="ED_Inj.Max",
        unit="MW",
        enforcement="respected",
        note=("the dispatch limit on the derated generator at the pinned "
              "interval. ED_Inj.md: Max is 'de-rated by ... dispatch limits "
              "(SCN_INJ_MAX)', so on a capped unit it is this step's MaxMw "
              "read back out of the solution"),
    ),
    ("k_gen", "avail"): Witness(
        kind="proportional",
        column="ED_Inj.Max",
        unit="MW",
        enforcement="respected",
        note=("the dispatch limit on the scaled generator at the pinned "
              "interval. The lever scales an availability SCHEDULE, so what "
              "the results echo is factor x schedule(interval) -- known only "
              "up to the factor, which is why this mode is proportional where "
              "'derate' is absolute"),
    ),
}

# The (lever, mode) pairs a sweep can walk. k_gen's third mode, 'outage', is
# deliberately absent: SCN_INJ_OUT.Outage is a BIT, the mode takes the value 1
# and nothing else, and a value axis with one admissible point is not a sweep.
SWEEPABLE: Tuple[Tuple[str, str], ...] = tuple(sorted(WITNESSES))


def sweepable_text() -> str:
    return ", ".join("%s/%s" % pair for pair in SWEEPABLE)


def witness_for(lever: str, mode: str) -> Witness:
    witness = WITNESSES.get((lever, mode))
    if witness is not None:
        return witness

    entry = ec.STRESS_LEVERS.get(lever)
    if entry is None:
        raise Ercot7kSweepError(
            "lever %r is not implemented at all. Implemented levers: %s. "
            "Sweepable lever/mode pairs: %s."
            % (lever, ", ".join(sorted(ec.STRESS_LEVERS)), sweepable_text()))
    if mode not in entry["modes"]:
        raise Ercot7kSweepError(
            "lever %s does not implement mode %r; it implements %s. Sweepable "
            "lever/mode pairs: %s."
            % (lever, mode, ", ".join(entry["modes"]), sweepable_text()))
    raise Ercot7kSweepError(
        "lever %s implements mode %s, but that pair cannot be swept: it "
        "writes %s, and this driver only sweeps a value that is a continuous "
        "axis with a readable witness. %s Sweepable lever/mode pairs: %s."
        % (lever, mode,
           (entry.get("mode_tables") or {}).get(mode, entry.get("table", "?")),
           entry["note"], sweepable_text()))


# ------------------------------------------------------------------------------
# sweep_steps()
#
# The step list, endpoint-inclusive in BOTH directions. See inherited defect 2.
#
# Integer step counting rather than float accumulation, so the i-th value is
# kmin + i*kstep computed once instead of kmin plus i roundings, and the count
# is decided before any value is produced. Three things are refused rather than
# worked around, because each of them is a silently short sweep:
#
#   - a zero step (no sweep exists)
#   - a step whose sign disagrees with the direction from kmin to kmax (devnet's
#     presets are all descending, which is how the arange bug went unnoticed)
#   - a range that is not a whole number of steps, e.g. 1.0 -> 0.25 by -0.1.
#     np.arange truncates this to 0.3 and reports a sweep that never reached its
#     endpoint. Refusing it names the two step counts that do fit.
#
# A single-point sweep is refused too: with one step the witness cannot vary, so
# the one check that makes this driver worth having cannot run. One point is a
# single run -- ercot7k_build.py then ercot7k_pso.py.
# ------------------------------------------------------------------------------
def sweep_steps(kmin: float, kmax: float, kstep: float,
                decimals: int = DEFAULT_DECIMALS) -> List[float]:
    kmin = float(kmin)
    kmax = float(kmax)
    kstep = float(kstep)

    if kstep == 0.0:
        raise Ercot7kSweepError(
            "kstep is 0, so no sweep exists. A step of zero produces either an "
            "empty list or an infinite one depending on how the loop is "
            "written; neither is a sweep.")
    if kmin == kmax:
        raise Ercot7kSweepError(
            "kmin == kmax == %s, which is one point. A sweep needs at least "
            "two, because the witness check compares steps against each other "
            "-- with one step there is nothing to compare and a lever that "
            "never applied would pass. Run a single point with "
            "ercot7k_build.py then %s." % (kmin, PSO_SCRIPT))

    span = kmax - kmin
    if (span > 0.0) != (kstep > 0.0):
        raise Ercot7kSweepError(
            "kstep %s runs away from kmax: kmin=%s kmax=%s needs a %s step. "
            "This is the direction that hides devnet's arange bug, so it is "
            "refused rather than corrected silently."
            % (kstep, kmin, kmax, "positive" if span > 0.0 else "negative"))

    exact = span / kstep
    count = int(round(exact))
    if count < 1 or abs(exact - count) > 1e-9:
        low = max(1, int(math.floor(exact)))
        high = max(low + 1, int(math.ceil(exact)))
        # Suggest KMAX values, not step sizes. A suggested step is rounded to
        # `decimals` and the rounded value no longer divides the span, so
        # following that advice reproduces this very message -- a refusal that
        # loops. kmin + n*kstep is always reachable by construction.
        raise Ercot7kSweepError(
            "kmin=%s kmax=%s kstep=%s is not a whole number of steps "
            "(%.6f of them). np.arange would truncate this and report a sweep "
            "that never reached kmax. Keep this kstep and use kmax=%s (%d "
            "steps) or kmax=%s (%d steps), or change kstep."
            % (kmin, kmax, kstep, exact,
               value_text(_round(kmin + low * kstep, decimals), decimals),
               low + 1,
               value_text(_round(kmin + high * kstep, decimals), decimals),
               high + 1))

    values = [_round(kmin + index * kstep, decimals)
              for index in range(count + 1)]

    # Asserted, not assumed. This is the endpoint the inherited bug drops, and
    # an assertion here is what stops a future refactor reintroducing it.
    if values[-1] != _round(kmax, decimals):
        raise Ercot7kSweepError(
            "step generation lost the endpoint: last step is %s, kmax is %s. "
            "This is the descending-sweep defect; do not paper over it."
            % (values[-1], _round(kmax, decimals)))
    if len(set(values)) != len(values):
        raise Ercot7kSweepError(
            "step generation produced duplicate values at %d decimals: %s. "
            "Raise --decimals or widen kstep." % (decimals, values))
    return values


def _round(value: float, decimals: int) -> float:
    # round() then add 0.0 so that -0.0 never reaches a directory name.
    return round(float(value), decimals) + 0.0


def value_text(value: float, decimals: int = DEFAULT_DECIMALS) -> str:
    """
    The step value as it goes into the config row: no trailing zero noise.

    The strip is guarded on a decimal point being present, which is not
    pedantry. Unguarded, "%.0f" % 100.0 is "100" and rstrip("0") eats the
    significant zeros, giving "1" -- and since this string is what
    build_step_rows puts into the layer, the sweep would build, solve and
    verify a factor of 1 while every label said 100. The witness would agree
    with the case file perfectly, because the case file would also say 1.
    """
    text = "%.*f" % (max(0, decimals), value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0"):
        # "-0" is what a small negative rounds to at coarse precision. It is
        # not a value any lever should be handed, and as a directory slug it
        # reads as a distinct step from "0" while meaning the same thing.
        return "0"
    return text


def value_slug(value: float, decimals: int = DEFAULT_DECIMALS) -> str:
    """Directory-safe form. Dots become 'p' -- a dotted directory reads as a
    file extension, which is the convention ercot7k_build.py already uses."""
    return value_text(value, decimals).replace(".", "p").replace("-", "m")


def step_slug(lever: str, value: float, prefix: str = "",
              decimals: int = DEFAULT_DECIMALS) -> str:
    """
    The layer slug for one step, e.g. k_line0p9.

    The target is deliberately NOT in the slug. Two sweeps of the same lever and
    values on different targets then collide on the layer directory name, and
    write_layer() refuses an existing directory -- so the collision is a stated
    error naming the directory, not a silently reused layer from the wrong
    branch. Pass --slug-prefix to run both.
    """
    return "%s%s%s" % (prefix, lever, value_slug(value, decimals))


# ------------------------------------------------------------------------------
# build_step_rows()
#
# The step value goes into the tall (lever, target, mode, value) row that the
# layer is built from -- the ONE place a value can enter a layer. This is what
# makes inherited defect 1 structurally impossible here rather than merely
# absent: there is no second path by which a layer could be built from
# something other than this step's value.
# ------------------------------------------------------------------------------
def build_step_rows(lever: str, target: str, mode: str, value: float,
                    decimals: int = DEFAULT_DECIMALS) -> List[Dict[str, str]]:
    return [{"lever": lever, "target": target, "mode": mode,
             "value": value_text(value, decimals)}]


# ------------------------------------------------------------------------------
# read_witness()
#
# The readback, out of the solved results, at the pinned interval.
#
# NaN means NOT MEASURED and is never 0.0. For k_line that distinction is the
# whole finding of section 5f of the task notes: the set of paths a run REPORTS
# is narrower than the monitored set and varies by run (the reference run
# reports 1,171 per cycle, our own runs report 7-9), so a derated branch can be
# absent from PN_Pth entirely. A 0.0 there would read as "limit of zero", which
# is a documented PSO meaning ("if NormalLimit = 0, limits are ignored"), i.e.
# the one value that must never be invented.
# ------------------------------------------------------------------------------
def read_witness(lever: str, mode: str, target: str, results_dir: Path,
                 key: er.ReportKey) -> Tuple[float, float]:
    """
    Returns (witness, enforced) at the pinned interval.

    enforced is 1.0 / 0.0 / NaN-for-unknown, and it is the second half of the
    claim. For k_line the witness is PN_Pth.Max, which PN_Pth.md defines as the
    maximum flow LIMIT -- an echo of the case file -- while enforcement is a
    separate bit. The committed reference run is full of rows reading
    Max=1371.200 with neither side enforced: the limit reported back with no
    part in dispatch. Without the bit, a k_line sweep can round-trip the CSV it
    just wrote and agree with itself to the digit.

    "Enforced" means MinEnforced OR MaxEnforced, because NormalLimit is
    bi-directional -- see path_limit_by_interval, where the study's own
    corridor is measured binding on Min in all 168 intervals and on Max in
    none.

    k_load has no equivalent question -- area load is consumed by the power
    balance unconditionally -- so it reports enforcement as NaN, meaning "not
    applicable", and W6 skips it by enforcement kind rather than by value.

    For k_gen there is no enforcement flag to read, because an injector
    dispatch limit is structural rather than discovered. What can be read is
    whether the solution OBEYED it, and that is a real question and not a
    tautology: PSO's dispatch limits are soft slacks, so a cap the LP did not
    apply appears as a positive ED_Inj.LimitViolation rather than as an
    infeasible solve.
    """
    # Refuses an unsweepable lever/mode before touching the disk.
    witness_for(lever, mode)
    results_dir = Path(results_dir)
    if lever == "k_line":
        limits = er.path_limit_by_interval(results_dir, key.cycle,
                                           key.scenario, target)
        entry = limits.get(key.interval)
        if entry is None:
            return math.nan, math.nan
        return entry["max_mw"], entry["enforced"]
    if lever == "k_load":
        metrics = er.area_metrics_by_interval(results_dir, key.cycle,
                                              key.scenario)
        entry = metrics.get(key.interval)
        return (entry["load_mw"] if entry else math.nan), math.nan
    if lever == "k_gen":
        limits = er.injector_limit_by_interval(results_dir, key.cycle,
                                               key.scenario, target)
        entry = limits.get(key.interval)
        if entry is None:
            return math.nan, math.nan
        # A Max of zero is NOT MEASURED, never a cap of zero. ED_Inj.md: Max
        # "is set to zero when off due to scheduled outage, forced outage,
        # failed startup, or unavailable for commitment" -- 33,675 of the
        # validated run's 106,848 RT rows are exactly that -- while no
        # admissible step can ask for a cap of zero, because a zero MaxMw
        # without Enforce is ignored and both partial modes refuse the value.
        # So a zero here is an unavailable unit and cannot have come from the
        # lever. Reported as a number it would be read as the deepest possible
        # derate: W3 would call the sweep broken, and on a sweep where the unit
        # was uncommitted at every step the witness would be perfectly constant
        # and W2 would call the lever unapplied.
        if entry["max_mw"] == 0.0:
            return math.nan, math.nan
        # The enforcement half rests on P against Max, which are both columns
        # this reader requires; LimitViolation corroborates it where the
        # results carry it. Unreadable dispatch is UNKNOWN rather than
        # respected, so that W6 can say so instead of passing on nothing.
        if not (_finite(entry["p_mw"]) and _finite(entry["max_mw"])):
            return entry["max_mw"], math.nan
        respected = 1.0
        if entry["p_mw"] > entry["max_mw"] + WITNESS_ATOL:
            respected = 0.0
        if (_finite(entry["limit_violation_mw"])
                and entry["limit_violation_mw"] > 0.0):
            respected = 0.0
        return entry["max_mw"], respected
    raise Ercot7kSweepError(
        "lever %s is in WITNESSES but read_witness() has no branch for it"
        % lever)


# ------------------------------------------------------------------------------
# written_witness()
#
# What the LAYER says the witness should be, for an absolute lever: read back
# out of the case file this step built, not recomputed from the step value.
#
# Recomputing it would test the arithmetic in this module against itself. Read
# from the file, it tests the case PSO was handed against the results PSO
# returned -- two independent artifacts -- and that is the comparison that can
# actually fail.
# ------------------------------------------------------------------------------
def written_witness(lever: str, mode: str, target: str,
                    layer_dir: Path) -> float:
    if witness_for(lever, mode).kind != "absolute":
        return math.nan
    layer_dir = Path(layer_dir)
    prefix = ec.case_prefix(layer_dir)
    if lever == "k_line":
        path = layer_dir / ("%s_SCN_BRN_LMT.csv" % prefix)
        if not path.is_file():
            return math.nan
        for record in ec.read_table(path).records():
            if record.get("Branch") == target and record.get("Scenario") == "0":
                return _as_float(record.get("NormalLimit", ""))
        return math.nan
    if lever == "k_gen" and mode == "derate":
        path = layer_dir / ("%s_SCN_INJ_MAX.csv" % prefix)
        if not path.is_file():
            return math.nan
        for record in ec.read_table(path).records():
            if (record.get("Injector") == target
                    and record.get("Scenario") == "0"):
                return _as_float(record.get("MaxMw", ""))
        return math.nan
    return math.nan


def _as_float(text: str) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return math.nan


def _finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def _close(left: float, right: float) -> bool:
    if not (_finite(left) and _finite(right)):
        return False
    return abs(left - right) <= max(WITNESS_ATOL, WITNESS_RTOL * abs(right))


# ------------------------------------------------------------------------------
#   The plan
# ------------------------------------------------------------------------------
@dataclass
class SweepPlan:
    sweep_id: str
    parent: Path
    lever: str
    target: str
    mode: str
    values: List[float]
    key: er.ReportKey
    pinned_by: Path
    slug_prefix: str = ""
    decimals: int = DEFAULT_DECIMALS

    @property
    def witness(self) -> Witness:
        """The (lever, mode) pair's witness. A property rather than a stored
        field so that a plan read back from sweep.json cannot carry a witness
        that disagrees with the lever and mode beside it."""
        return witness_for(self.lever, self.mode)

    def slug(self, value: float) -> str:
        return step_slug(self.lever, value, self.slug_prefix, self.decimals)

    def run_name(self, index: int, value: float) -> str:
        # Three digits, matching step_record_name: an operator lists these
        # directories too, and at two digits run 100 sorts before run 99.
        return "%s-%03d-%s" % (self.sweep_id, index, self.slug(value))

    def identity_digest(self) -> str:
        """A short hash of everything that makes this sweep this sweep.

        The run marker carries it so that ownership of a results directory
        means "the same PLAN wrote here", not merely "some sweep with this id
        did". Without it the marker is a re-encoding of the directory name it
        was derived from -- run_name is sweep_id + index + slug, which is
        exactly what the marker recorded -- so it could only ever disagree if
        someone hand-edited it.
        """
        # Built from the identity fields directly rather than by taking a
        # slice of as_dict(). as_dict() also resolves the witness, which is a
        # property of the (lever, mode) pair and refuses a pair that cannot be
        # swept -- a correct refusal in a sweep record, and an unwanted one in
        # a hash whose only job is to say whether two plans are the same.
        payload: Dict[str, Any] = {
            "parent": str(self.parent),
            "lever": self.lever,
            "target": self.target,
            "mode": self.mode,
            "values": list(self.values),
            "slug_prefix": self.slug_prefix,
            "decimals": self.decimals,
        }
        missing = sorted(set(PLAN_IDENTITY) - set(payload))
        if missing:
            raise Ercot7kSweepError(
                "identity_digest() does not hash %s, which PLAN_IDENTITY says "
                "is part of a sweep's identity: two sweeps differing only "
                "there would share a digest and each other's results."
                % ", ".join(missing))
        payload["report"] = self.key.as_dict()
        text = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": SWEEP_SCHEMA,
            "writer": DRIVER_ID,
            "created_utc": _utc_now(),
            "sweep_id": self.sweep_id,
            "parent": str(self.parent),
            "lever": self.lever,
            "target": self.target,
            "mode": self.mode,
            "values": list(self.values),
            "decimals": self.decimals,
            "slug_prefix": self.slug_prefix,
            "report": self.key.as_dict(),
            "pinned_by": str(self.pinned_by),
            "witness": {
                "kind": self.witness.kind,
                "column": self.witness.column,
                "unit": self.witness.unit,
                "enforcement": self.witness.enforcement,
                "note": self.witness.note,
            },
        }


# ------------------------------------------------------------------------------
# resolve_pin()
#
# The pinned interval belongs to the STUDY, not to a run: every step of a sweep
# has to report the same hour or the response curve is the pin moving. It is
# written once by ercot7k_results.py's `pin` command into a case directory, and
# write_layer() copies it down the chain like any other case file -- so the
# nearest ancestor carrying study.json is the study's pin.
#
# Walking the chain rather than looking only at the parent matters because a pin
# written AFTER a layer was built cannot travel: case_digest() covers study.json,
# so adding one to a case that already has children makes walk_chain() refuse the
# children as hand-edited. Pin the base first, then build.
# ------------------------------------------------------------------------------
def resolve_pin(case_dir: Path) -> Tuple[er.ReportKey, Path]:
    case_dir = Path(case_dir).resolve()
    chain = ec.walk_chain(case_dir)
    for layer in reversed(chain):
        if er.has_study(layer.path):
            return er.pinned_report_key(layer.path), layer.path
    raise Ercot7kSweepError(
        "no %s anywhere in the chain above %s, so this sweep has no pinned "
        "interval and every step would report a different hour -- which is the "
        "failure mode that makes a sweep unreadable (a k_load step moves the "
        "peak, and hour 88 then gets compared against hour 91). Pin it from a "
        "BASE run first:\n"
        "    python %s pin <base-results-dir> --case-dir %s\n"
        "and pin before building layers: the pin file is part of the case "
        "digest, so adding one to a case that already has children invalidates "
        "them." % (er.STUDY_NAME, case_dir, "ercot7k_results.py",
                   chain[0].path))


# ------------------------------------------------------------------------------
# assert_witness_can_see_the_lever()
#
# Checked at PLAN time, before an hour of solving, because the failure it
# catches would surface as a W3 error blaming the lever for something the
# witness cannot observe.
#
# SCN_ARA_LOD.md gives the priority Sequence > Schedule > static Load, and says
# ScaleFactor is "applied to Schedule and Sequence" -- NOT to the static Load
# field. So an area whose load comes from the static field is not scaled by
# k_load at all, while ED_Ara.Load still reports it. On a case mixing the two,
# the witness would move by less than the lever and W3 would call the sweep
# broken when the lever applied exactly as documented to everything it can
# reach.
#
# The shipped case is clean -- both SCN_ARA_LOD rows carry a schedule and a
# blank Load -- so this is a guard against the case changing, which is why it
# names the rows rather than just refusing.
#
# k_gen asks the same question of the other table. Its two partial modes write
# the SAME FIELD FAMILY to two disjoint populations of injector, and the wrong
# one for the population is not an error in PSO -- it is a row that reads as a
# derate and is discarded (a static MaxMw beside a schedule that outranks it; a
# ScaleFactor with no schedule to scale). ercot7k_case.py refuses both when the
# layer is built, which is already before the solve; refusing here as well is
# what stops a plan being ACCEPTED, printed with a projected cost and a step
# list, and then dying on step 1.
# ------------------------------------------------------------------------------
def assert_witness_can_see_the_lever(parent: Path, lever: str,
                                     mode: str = "", target: str = "") -> None:
    if lever == "k_gen":
        _assert_injector_population(Path(parent), mode, target)
        return
    if lever != "k_load":
        return
    parent = Path(parent)
    prefix = ec.case_prefix(parent)
    path = parent / ("%s_SCN_ARA_LOD.csv" % prefix)
    if not path.is_file():
        return
    static = [record for record in ec.read_table(path).records()
              if (record.get("Load") or "").strip()]
    if not static:
        return
    raise Ercot7kSweepError(
        "%s has %d row(s) carrying a static Load (%s). SCN_ARA_LOD.md: "
        "ScaleFactor is applied to Schedule and Sequence, not to the static "
        "Load field, so k_load would leave those rows unscaled while "
        "ED_Ara.Load still reports them -- the witness would move by less "
        "than the lever and W3 would report a broken sweep for a lever that "
        "applied correctly to everything it can reach. Drive that area's load "
        "from a schedule, or sweep something else."
        % (path.name, len(static),
           ", ".join("scenario %s area %s" % (r.get("Scenario", ""),
                                              r.get("Area", ""))
                     for r in static[:4])))


def _injector_max_rows(parent: Path, injector: str) -> List[Dict[str, str]]:
    path = parent / ("%s_SCN_INJ_MAX.csv" % ec.case_prefix(parent))
    if not path.is_file():
        return []
    return [r for r in ec.read_table(path).records()
            if r.get("Injector") == injector]


def _assert_injector_population(parent: Path, mode: str, target: str) -> None:
    rows = _injector_max_rows(parent, target)
    if mode == "derate" and rows:
        raise Ercot7kSweepError(
            "%s already carries %d SCN_INJ_MAX row(s) (%s), so mode 'derate' "
            "-- a static MaxMw -- cannot reach it: Sequence and Schedule both "
            "outrank the static value, and those schedules cover every "
            "interval. Sweep it with mode 'avail', which scales the schedule."
            % (target, len(rows),
               ", ".join("%s -> %s" % (r.get("Scenario", ""),
                                       r.get("Schedule") or "(none)")
                         for r in rows[:4])))
    if mode == "avail" and not rows:
        raise Ercot7kSweepError(
            "%s carries no SCN_INJ_MAX row, so mode 'avail' has no Schedule or "
            "Sequence to scale and a ScaleFactor on it would state nothing. "
            "Sweep it with mode 'derate', which writes an absolute MaxMw in MW."
            % target)


# ------------------------------------------------------------------------------
# assert_values_admissible()
#
# Every step of the plan, against the ceiling and floor the case states, before
# any of them is solved.
#
# A sweep is where an out-of-range value stops being a refusal and starts being
# a PLATEAU: SCN_INJ_MAX can only restrict, so k_gen derate steps above the
# nameplate all report the same number, and a reader of the response curve sees
# a lever that saturated rather than a case that refused. The layer writer
# refuses each of them, but it refuses them one at a time, six minutes apart,
# after the earlier steps have already been solved and written.
# ------------------------------------------------------------------------------
def assert_values_admissible(parent: Path, lever: str, mode: str, target: str,
                             values: Sequence[float]) -> None:
    if lever != "k_gen":
        return
    parent = Path(parent)
    if mode == "avail":
        over = [v for v in values if v > 1.0]
        if over:
            raise Ercot7kSweepError(
                "mode 'avail' scales an availability schedule and can only "
                "restrict it, so %d step(s) above 1.0 (%s) would ask the case "
                "for capacity the schedule never claimed."
                % (len(over), ", ".join(value_text(v) for v in over[:5])))
        return
    if mode != "derate":
        return

    prefix = ec.case_prefix(parent)
    nameplate = math.nan
    path = parent / ("%s_INJ_ID.csv" % prefix)
    if path.is_file():
        for record in ec.read_table(path).records():
            if record.get("Injector") == target:
                nameplate = _as_float(record.get("MaxMw", ""))
                break
    if math.isnan(nameplate):
        raise Ercot7kSweepError(
            "%s is not in INJ_ID, so there is no nameplate to sweep below. "
            "The target of k_gen is an Injector key, not a node or a "
            "substation name." % target)
    over = [v for v in values if v > nameplate]
    if over:
        raise Ercot7kSweepError(
            "%d step(s) ask for more than %s's INJ_ID.MaxMw of %s (%s). "
            "SCN_INJ_MAX can only restrict, never raise, so every one of them "
            "would report the SAME dispatch limit and read as a saturated "
            "lever rather than as a refused input."
            % (len(over), target, _fmt(nameplate),
               ", ".join(value_text(v) for v in over[:5])))

    floor = math.nan
    path = parent / ("%s_INJ_CMT.csv" % prefix)
    if path.is_file():
        for record in ec.read_table(path).records():
            if record.get("Injector") == target:
                floor = _as_float(record.get("MinDispatch", ""))
                break
    under = [v for v in values if _finite(floor) and v < floor]
    if under:
        raise Ercot7kSweepError(
            "%d step(s) ask for less than %s's INJ_CMT.MinDispatch of %s (%s). "
            "VERIFIED, SCN_INJ_MAX.md: 'Limit cannot be more restrictive than "
            "MinDispatch (INJ_CMT).' Stop the sweep at the floor, or take the "
            "unit out entirely with mode 'outage'."
            % (len(under), target, _fmt(floor),
               ", ".join(value_text(v) for v in under[:5])))


# The characters Windows refuses in a file name, plus the separators. A name
# that passes this validator and is then refused by the filesystem is worse
# than one that was never checked: the operator has been told it is fine, the
# plan prints in full, and the failure arrives from mkdir as a trace.
_UNSAFE_CHARS = '<>:"/\\|?*'


def _assert_path_safe(what: str, text: str, allow_empty: bool = False,
                      component: bool = True) -> None:
    """
    component=False for a value that is only ever PART of a directory name.

    The trailing-dot rule is about a name Windows can strip, which requires
    the dot to be at the END of the component. A slug prefix is spliced into
    the middle -- step_slug returns prefix + lever + value -- so "v2." can
    never end a directory name, and refusing it turns a natural namespace
    prefix into an error for a hazard that cannot occur there.
    """
    if not text:
        if allow_empty:
            return
        raise Ercot7kSweepError("the %s is empty" % what)
    reasons: List[str] = []
    bad = sorted({ch for ch in _UNSAFE_CHARS if ch in text})
    if bad:
        reasons.append("the character(s) %s"
                       % ", ".join(repr(ch) for ch in bad))
    if any(ord(ch) < 32 for ch in text):
        reasons.append("a control character")
    if text.strip() != text:
        reasons.append("leading or trailing whitespace")
    # Component-wise, not a substring test: "x..y" is a perfectly good
    # directory name and was being refused, while "." -- which collapses the
    # sweep directory back onto the sweeps root, scattering sweep.json and the
    # step records into the shared parent -- was being accepted.
    if text in (os.curdir, os.pardir):
        reasons.append("a path component meaning 'this directory' or 'the "
                       "parent directory'")
    # Windows silently strips a trailing dot from a directory name, so "foo."
    # and "foo" are the same directory while reading as two sweep ids -- and
    # text.strip() does not see it.
    if component and text.endswith("."):
        reasons.append("a trailing '.', which Windows strips, so it would "
                       "silently share a directory with the same name "
                       "without it")
    if reasons:
        raise Ercot7kSweepError(
            "the %s %r is not usable as a directory name (it contains %s). It "
            "names a directory under the sweeps root and a case layer, so it "
            "has to be a plain name." % (what, text, "; ".join(reasons)))


def plan_sweep(parent: Path, lever: str, target: str, mode: str,
               kmin: float, kmax: float, kstep: float,
               sweep_id: Optional[str] = None,
               slug_prefix: str = "",
               decimals: int = DEFAULT_DECIMALS) -> SweepPlan:
    parent = Path(parent).resolve()
    # Refuses an unimplemented lever, an unimplemented mode and an
    # implemented-but-unsweepable pair, each naming what it is.
    witness_for(lever, mode)

    entry = ec.STRESS_LEVERS[lever]
    if entry["target"] == "blank" and target:
        raise Ercot7kSweepError(
            "lever %s takes a blank target: %s" % (lever, entry["note"]))
    if entry["target"] != "blank" and not target:
        raise Ercot7kSweepError(
            "lever %s needs a %s as its target: %s"
            % (lever, entry["target"], entry["note"]))

    assert_witness_can_see_the_lever(parent, lever, mode, target)
    values = sweep_steps(kmin, kmax, kstep, decimals)
    assert_values_admissible(parent, lever, mode, target, values)
    key, pinned_by = resolve_pin(parent)

    if sweep_id is None:
        sweep_id = "%s-%s" % (lever, datetime.now().strftime("%Y%m%d-%H%M%S"))
    # Both of these become directory names -- sweeps_root/<sweep_id> and the
    # layer slug. The runner validates its own run name for separators; these
    # went unchecked, so a stray slash would have scattered a sweep's records
    # and layers across the filesystem.
    _assert_path_safe("sweep id", sweep_id)
    _assert_path_safe("slug prefix", slug_prefix, allow_empty=True,
                      component=False)

    return SweepPlan(sweep_id=sweep_id, parent=parent, lever=lever,
                     target=target, mode=mode, values=values, key=key,
                     pinned_by=Path(pinned_by), slug_prefix=slug_prefix,
                     decimals=decimals)


# ------------------------------------------------------------------------------
#   Running one step
# ------------------------------------------------------------------------------
@dataclass
class StepOutcome:
    """What one step of a sweep produced. Written to step_<nn>.json verbatim."""
    index: int
    value: float
    slug: str
    layer: str = ""
    run_dir: str = ""
    results_dir: str = ""
    returncode: int = -1
    seconds: float = 0.0
    results_mb: float = 0.0
    # What the step wrote BEFORE --prune, which is what the next step will
    # also transiently need. results_mb is what survived.
    peak_results_mb: float = 0.0
    witness: float = math.nan
    witness_written: float = math.nan
    witness_enforced: float = math.nan
    status: str = ""
    solves: int = 0
    figures: Dict[str, Any] = field(default_factory=dict)
    pruned: List[str] = field(default_factory=list)
    error: str = ""

    def ok(self) -> bool:
        return self.returncode == 0 and not self.error

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "schema": STEP_SCHEMA,
            "writer": DRIVER_ID,
            "recorded_utc": _utc_now(),
        }
        payload.update({
            key: _jsonable(getattr(self, key))
            for key in ("index", "value", "slug", "layer", "run_dir",
                        "results_dir", "returncode", "seconds", "results_mb",
                        "peak_results_mb",
                        "witness", "witness_written", "witness_enforced",
                        "status", "solves", "figures", "pruned", "error")
        })
        return payload


def _jsonable(value: Any) -> Any:
    """NaN is not JSON. It is written as null and read back as NaN, so that a
    'not measured' witness cannot come back from disk as a number."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _from_json(value: Any) -> float:
    return math.nan if value is None else float(value)


def outcome_from_dict(payload: Dict[str, Any]) -> StepOutcome:
    # A step record truncated mid-write (power loss, a full disk) would
    # otherwise raise a bare KeyError out of --resume or `check`, naming
    # nothing. The three required keys are named here so the message points at
    # the file to delete.
    missing = [key for key in ("index", "value", "slug") if key not in payload]
    if missing:
        raise Ercot7kSweepError(
            "a step record is missing %s, so it cannot be read. It was "
            "probably truncated mid-write; delete it and let --resume re-run "
            "that step." % ", ".join(missing))
    return StepOutcome(
        index=int(payload["index"]),
        value=float(payload["value"]),
        slug=payload["slug"],
        layer=payload.get("layer", ""),
        run_dir=payload.get("run_dir", ""),
        results_dir=payload.get("results_dir", ""),
        returncode=int(payload.get("returncode", -1)),
        seconds=float(payload.get("seconds", 0.0)),
        results_mb=float(payload.get("results_mb", 0.0)),
        peak_results_mb=float(payload.get("peak_results_mb") or 0.0),
        witness=_from_json(payload.get("witness")),
        witness_written=_from_json(payload.get("witness_written")),
        witness_enforced=_from_json(payload.get("witness_enforced")),
        status=payload.get("status", ""),
        solves=int(payload.get("solves", 0)),
        figures=payload.get("figures", {}),
        pruned=list(payload.get("pruned", [])),
        error=payload.get("error", ""),
    )


# ------------------------------------------------------------------------------
# pso_run_step()
#
# The default runner: ercot7k_pso.py, by subprocess, once per step.
#
# By subprocess and not by import, because ercot7k_pso.py executes at module
# level -- it prompts, creates directories and replaces sys.stdout -- so an
# import would hang the sweep before step 1. It is also the interpreter
# boundary: the sweep runs in the PyPSA env and the runner re-execs itself into
# the aimmspy env, which it can only do as its own process.
#
# stdin is DEVNULL, not a pipe with canned answers. The two gates the runner
# has are supplied by environment (DEVNET_PSO_RUN_NAME, DEVNET_PSO_ASSUME_YES),
# so nothing should read stdin at all; if a future prompt appears, EOFError
# stops the step loudly instead of a canned "Y" answering a question nobody
# knew was being asked.
#
# Output is NOT captured. A step is six minutes of near-silence with a heartbeat
# every 30 s, and the operator watching an hour-long sweep needs to see it. The
# runner writes its own log under the run directory either way, and the step
# record names the path.
# ------------------------------------------------------------------------------
def pso_run_step(case_csv: Path, run_name: str,
                 runs_root: Path,
                 timeout: Optional[float] = None) -> Tuple[int, Path, float]:
    script = SCRIPT_DIR / PSO_SCRIPT
    if not script.is_file():
        raise Ercot7kSweepError("%s not found beside this module" % PSO_SCRIPT)

    runs_root = Path(runs_root).resolve()
    child = dict(os.environ)
    child["DEVNET_PSO_CASE"] = str(Path(case_csv).resolve())
    child["DEVNET_PSO_RUN_NAME"] = run_name
    child["DEVNET_PSO_ASSUME_YES"] = "1"
    # The runner otherwise writes under the repo root, and the results path
    # returned below is computed from runs_root -- so without this the mapper
    # looks somewhere the solve did not write, and a step that solved correctly
    # fails as a missing file six minutes later.
    child["DEVNET_PSO_RUNS_ROOT"] = str(runs_root)
    # The runner sets this before re-execing itself; a stale value inherited
    # from an earlier step would make it refuse to re-exec at all.
    child.pop("DEVNET_PSO_RELAUNCHED", None)

    started = time.time()
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SCRIPT_DIR), env=child, stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
    seconds = time.time() - started
    results_dir = runs_root / run_name / "results"
    return completed.returncode, results_dir, seconds


BuildFn = Callable[[Path, Path, Sequence[Dict[str, str]], str], Dict[str, Any]]
RunFn = Callable[[Path, str, Path], Tuple[int, Path, float]]


# ------------------------------------------------------------------------------
# run_sweep()
#
# The loop. build_fn / run_fn / map_fn are injectable so the loop can be tested
# without an AIMMS seat: the seat is single and a step is six minutes, so a
# suite that needed one would never be run, and an untested sweep driver is how
# the inherited defects survived three months in devnet.
#
# A step record is written as each step finishes rather than at the end, so an
# hour of solving is not lost to a failure in step 9, and --resume can pick the
# sweep up where it stopped.
# ------------------------------------------------------------------------------
def run_sweep(plan: SweepPlan,
              sweeps_root: Path,
              derived_root: Path,
              runs_root: Path,
              build_fn: Optional[BuildFn] = None,
              run_fn: Optional[RunFn] = None,
              map_fn: Optional[Callable[..., Any]] = None,
              resume: bool = False,
              prune: bool = False,
              stop_on_error: bool = True,
              echo: Optional[Callable[[str], None]] = None) -> List[StepOutcome]:
    build_fn = build_fn or ec.build_stress_layer
    run_fn = run_fn or pso_run_step
    map_fn = map_fn or er.map_results
    say = echo or (lambda text: None)

    sweep_dir = Path(sweeps_root) / plan.sweep_id
    # Belt to _assert_path_safe's braces: whatever the validator has not
    # thought of, the filesystem has an opinion about, and that opinion must
    # not reach the operator as a stack trace after the plan has printed in
    # full. A directory that cannot be created is a refusal to start.
    try:
        sweep_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir = sweep_dir / ARTIFACTS_DIRNAME
        artifacts_dir.mkdir(exist_ok=True)
    except OSError as exc:
        raise Ercot7kSweepError(
            "could not create the sweep directory %s: %s. The sweep id has to "
            "be usable as a directory name on this platform."
            % (sweep_dir, exc))
    # sweep.json is the only record of what was ASKED for. Overwriting it with
    # a different plan under the same sweep id destroys that record and leaves
    # the step files describing a sweep nobody can reconstruct, so a changed
    # plan is refused before anything is written.
    #
    # And a resume with NO plan file is refused outright: with nothing to be
    # identical to, assert_plan_unchanged has nothing to say, and deleting one
    # ordinary file would otherwise reopen the whole hole below. Resuming is a
    # claim that this is the same sweep; without the plan that claim cannot be
    # checked, and an unverifiable claim is not a pass.
    if resume and not (sweep_dir / SWEEP_NAME).is_file():
        raise Ercot7kSweepError(
            "--resume was asked for but %s has no %s, so there is no recorded "
            "plan to check this one against. The step records alone cannot "
            "say which sweep they belong to. Start a fresh sweep id, or "
            "restore the plan file." % (sweep_dir, SWEEP_NAME))
    assert_plan_unchanged(sweep_dir, plan)
    write_plan(sweep_dir, plan)

    outcomes: List[StepOutcome] = []
    for index, value in enumerate(plan.values, start=1):
        rows = build_step_rows(plan.lever, plan.target, plan.mode, value,
                               plan.decimals)
        record = sweep_dir / step_record_name(index)
        if resume and record.is_file():
            existing = outcome_from_dict(json.loads(record.read_text("ascii")))
            # The record is keyed by step INDEX, which says nothing about what
            # that step was, and step_slug() deliberately omits the TARGET --
            # so slug and value together still cannot tell two k_line sweeps on
            # different branches apart. The authority on what a layer was built
            # from is the layer's own manifest, so the guard this path used to
            # skip is run here instead of being reasoned around: accepting a
            # record means accepting its layer, and that layer must match this
            # step's stress row exactly.
            if existing.ok() and existing.slug == plan.slug(value) \
                    and _same_value(existing.value, value, plan.decimals) \
                    and _layer_matches(existing.layer, rows[-1]):
                say("step %d/%d  value %s  RESUMED from %s"
                    % (index, len(plan.values), value_text(value,
                                                           plan.decimals),
                       record.name))
                outcomes.append(existing)
                continue
            if existing.ok():
                say("  the record in %s does not match this step (%s, %s on "
                    "%r) -- re-running rather than reporting it under the "
                    "wrong label"
                    % (record.name, value_text(value, plan.decimals),
                       plan.slug(value), plan.target))

        say(SUBSECTION_SEPARATOR.rstrip("\n"))
        say("step %d/%d  %s=%s" % (index, len(plan.values), plan.lever,
                                   value_text(value, plan.decimals)))

        if outcomes:
            fits, why = enough_disk_for_step(
                Path(runs_root),
                [o.peak_results_mb or o.results_mb for o in outcomes])
            if not fits:
                say("AMW-ERR: %s" % why)
                break
        outcome = _run_one_step(
            plan=plan, index=index, value=value, rows=rows,
            derived_root=Path(derived_root), runs_root=Path(runs_root),
            artifacts_dir=artifacts_dir,
            build_fn=build_fn, run_fn=run_fn, map_fn=map_fn,
            resume=resume, prune=prune, say=say,
        )
        # backslashreplace, not plain encode: outcome.error carries an
        # exception message and outcome.layer/run_dir carry filesystem paths,
        # either of which can hold a non-ASCII byte (a library's smart quote, a
        # non-ASCII username). A UnicodeEncodeError raised HERE, outside
        # _run_one_step's try, would throw away a six-minute solve along with
        # the record of it and leave nothing for --resume to find. The file
        # stays ASCII; the odd byte arrives escaped instead of fatal.
        record.write_bytes(
            (json.dumps(outcome.as_dict(), indent=2) + "\n")
            .encode("ascii", "backslashreplace"))
        outcomes.append(outcome)

        if not outcome.ok() and stop_on_error:
            say("AMW-ERR: step %d failed (%s). Stopping; the steps already "
                "done are on disk and --resume will skip them."
                % (index, outcome.error or "exit %d" % outcome.returncode))
            break

    return outcomes


def _run_one_step(plan: SweepPlan, index: int, value: float,
                  rows: Sequence[Dict[str, str]],
                  derived_root: Path, runs_root: Path, artifacts_dir: Path,
                  build_fn: BuildFn, run_fn: RunFn,
                  map_fn: Callable[..., Any],
                  resume: bool, prune: bool,
                  say: Callable[[str], None]) -> StepOutcome:
    slug = plan.slug(value)
    outcome = StepOutcome(index=index, value=value, slug=slug)

    layer = derived_root / ec.layer_dir_name(plan.parent, slug)
    outcome.layer = str(layer)

    try:
        if layer.exists():
            # Layers are write-once. On a resume that is the layer this step
            # already built; without --resume it is someone else's, and reusing
            # it silently would solve a case this sweep did not write.
            if not resume:
                raise Ercot7kSweepError(
                    "%s already exists. A layer is written once. Use --resume "
                    "if this sweep built it, or --slug-prefix / a different "
                    "sweep id if it belongs to another study." % layer)
            assert_layer_matches(layer, rows[-1])
            say("  layer exists and matches this step, reusing it (resume): %s"
                % layer.name)
        else:
            build_fn(plan.parent, layer, rows, slug)
            say("  layer built: %s" % layer.name)

        run_name = plan.run_name(index, value)
        case_csv = layer / ("%s.csv" % ec.case_prefix(layer))
        # A re-solve of this step reuses the run name, and the runner creates
        # its results directory with exist_ok=True and clears nothing -- so a
        # failed first attempt's files would survive and be read as this
        # attempt's. Cleared rather than merged, but only against a marker
        # proving the directory is this sweep's step; anything else is a
        # collision and is refused.
        _clear_previous_attempt(Path(runs_root) / run_name, plan, index, slug,
                                say)
        say("  solving: %s" % run_name)
        returncode, results_dir, seconds = run_fn(case_csv, run_name, runs_root)
        outcome.returncode = int(returncode)
        outcome.seconds = float(seconds)
        outcome.run_dir = str(Path(results_dir).parent)
        outcome.results_dir = str(results_dir)
        outcome.results_mb = _dir_mb(results_dir)
        outcome.peak_results_mb = outcome.results_mb

        if returncode != 0:
            outcome.error = ("%s exited %d -- see its own log under %s"
                             % (PSO_SCRIPT, returncode, outcome.run_dir))
            return outcome

        # The witness comes FIRST, before anything derived from the run. If the
        # lever did not reach the solver, every other number in this row is a
        # correct measurement of the wrong case.
        outcome.witness, outcome.witness_enforced = read_witness(
            plan.lever, plan.mode, plan.target, results_dir, plan.key)
        outcome.witness_written = written_witness(plan.lever, plan.mode,
                                                  plan.target, layer)
        say("  witness %s = %s %s (layer wrote %s)%s"
            % (plan.witness.column, _fmt(outcome.witness),
               plan.witness.unit, _fmt(outcome.witness_written),
               _enforced_text(plan.lever, plan.mode,
                              outcome.witness_enforced)))

        run = map_fn(results_dir, interval=plan.key.interval,
                     cycle=plan.key.cycle, scenario=plan.key.scenario,
                     case_dir=layer)
        er.write_artifacts(artifacts_dir, slug, run)
        (artifacts_dir / ("%s_dashboard.md" % slug)).write_text(
            er.dashboard_text(run, slug), encoding="ascii")
        outcome.status = run.summary.get("status", "")
        outcome.solves = int(run.dashboard.get("solves", 0))
        outcome.figures = _step_figures(run, plan.key)

        if prune:
            outcome.pruned = prune_results(results_dir)
            outcome.results_mb = _dir_mb(results_dir)
            # results_mb is now the RETAINED size, but the next step still
            # writes the full ~442 MB before anything is pruned, so the disk
            # guard has to size against the peak. Keeping both means the
            # summary reports what is on disk while the guard reserves what
            # the next step will transiently need.
            say("  pruned %d result file(s): %.0f MB -> %.0f MB"
                % (len(outcome.pruned), outcome.peak_results_mb,
                   outcome.results_mb))
    except Exception as exc:  # recorded, not swallowed: the record is the log
        outcome.error = "%s: %s" % (type(exc).__name__, exc)
        say("  AMW-ERR: %s" % outcome.error)
    return outcome


# ------------------------------------------------------------------------------
# assert_layer_matches()
#
# --resume reuses a layer instead of building it, which means the one check that
# normally guarantees a layer is this step's -- write_layer() refusing an
# existing directory -- is deliberately suspended. So it is replaced rather than
# dropped.
#
# The hole it closes is narrow and quiet: the slug omits the target (see
# step_slug), so a k_line sweep over the same values on a DIFFERENT branch
# produces the same directory names. Without this, --resume would solve last
# week's corridor and report it under this week's target, and only W3 would
# eventually notice, by way of a witness that had gone missing.
#
# The manifest records the stress rows verbatim next to what was written, so the
# comparison is against what the layer was ASKED for, not against a value
# recomputed here.
# ------------------------------------------------------------------------------
FIELDS = ("lever", "target", "mode", "value")


def _layer_matches(layer_dir: str, row: Dict[str, str]) -> bool:
    """assert_layer_matches as a predicate, for the resume-accept branch: a
    record whose layer does not match is re-run rather than refused, because
    unlike a fresh build there is a legitimate way forward."""
    if not layer_dir:
        return False
    try:
        assert_layer_matches(Path(layer_dir), row)
    except Ercot7kSweepError:
        return False
    return True


def assert_layer_matches(layer_dir: Path, row: Dict[str, str]) -> None:
    layer_dir = Path(layer_dir)
    if not ec.has_manifest(layer_dir):
        raise Ercot7kSweepError(
            "%s exists but carries no %s, so there is no way to tell what it "
            "was built from. It is not a layer this driver wrote; move it "
            "aside." % (layer_dir, ec.MANIFEST_NAME))
    stress = (ec.read_manifest(layer_dir).get("study") or {}).get("stress") or []
    if not stress:
        raise Ercot7kSweepError(
            "%s records no stress rows in its manifest, so it is not a stress "
            "layer and this step cannot reuse it." % layer_dir)
    asked = {key: str(row.get(key, "")).strip() for key in FIELDS}
    found = {key: str(stress[-1].get(key, "")).strip() for key in FIELDS}
    if found != asked:
        raise Ercot7kSweepError(
            "%s was built from %s but this step is %s. The layer slug does not "
            "carry the target, so two sweeps of the same lever and values on "
            "different targets land on the same directory name -- and resuming "
            "onto it would solve the wrong case and report it under this "
            "step's target. Use --slug-prefix to separate them."
            % (layer_dir,
               ", ".join("%s=%s" % (k, found[k]) for k in FIELDS),
               ", ".join("%s=%s" % (k, asked[k]) for k in FIELDS)))


# ------------------------------------------------------------------------------
# _step_figures()
#
# The response variables, from the mapped run. Deliberately a small fixed set:
# the full artifacts are written per step anyway, and a summary table wide
# enough to hold everything is one nobody reads.
#
# Both lmp_spread definitions are carried, unlabelled as headline. That question
# is open with Ashok and the campaign measured it mattering: on the derated
# corridor P95-P05 moved +0.51 where max-min moved +2.34, about 4.6x harder, so
# a sweep reported on P95-P05 alone understates a lever working exactly as
# intended.
# ------------------------------------------------------------------------------
def _step_figures(run: Any, key: er.ReportKey) -> Dict[str, Any]:
    dashboard = run.dashboard
    figures: Dict[str, Any] = {
        "lmp_spread_p95_p05": dashboard.get("lmp_spread_p95_p05", math.nan),
        "lmp_spread_maxmin": dashboard.get("lmp_spread_maxmin", math.nan),
        "max_loading_pu": dashboard.get("max_loading_pu", math.nan),
        "n_binding": dashboard.get("n_binding", 0),
        "n_paths": dashboard.get("n_paths", 0),
        "total_load_mw": run.summary.get("total_system_load_mw", math.nan),
    }
    for cycle, cost in (dashboard.get("objective_by_cycle") or {}).items():
        figures["cost_%s" % cycle] = cost

    for row in run.deliverability_rows:
        if row.get("int") != key.interval:
            continue
        for column in ("system_violation_mw", "system_penalty_usd",
                       "dc_p_mw", "dc_limit_violation_mw", "byog_p_mw"):
            if column in row:
                figures[column] = row[column]
        break
    return figures


# ------------------------------------------------------------------------------
# _clear_previous_attempt()
#
# Removes the results of an earlier attempt at THIS step before re-solving it,
# and ONLY when a marker proves the directory is this sweep's.
#
# The first version called the composed run name a guard. It is not -- it is
# the assumption under test, and a reviewer duly deleted a foreign run's
# results with it.
#
# So the driver writes a marker beside results/ at step start, and deletion
# requires it to match. What the marker has to carry is the part that took two
# goes to get right: sweep_id + step + slug is exactly what run_name is built
# from, so a marker holding only those is a re-encoding of the directory name
# it was derived from and can disagree only if hand-edited. It therefore also
# carries the PLAN DIGEST, which the directory name does not: ownership means
# "the same plan wrote here", not "something with this id did".
#
# What that does and does not defend, stated exactly, because the previous
# version of this comment claimed more than the code delivered:
#   - a directory this driver never wrote      -> REFUSED (no marker)
#   - a different plan reusing this sweep id   -> REFUSED (digest differs),
#     including when sweep.json has been deleted, which is the one path
#     assert_plan_unchanged cannot see
#   - the SAME plan re-running its own step    -> cleared, which is the point:
#     those files are a failed attempt at exactly this step, and merging into
#     them would read them as this attempt's
#
# Logs are never touched -- a failed attempt's log is the evidence of why it
# failed.
# ------------------------------------------------------------------------------
RUN_MARKER_NAME = "ercot7k_sweep_step.json"


def _write_run_marker(run_dir: Path, plan: SweepPlan, index: int,
                      slug: str) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {"writer": DRIVER_ID, "sweep_id": plan.sweep_id,
               "step": int(index), "slug": slug,
               "plan_digest": plan.identity_digest(),
               "written_utc": _utc_now()}
    (run_dir / RUN_MARKER_NAME).write_bytes(
        (json.dumps(payload, indent=2) + "\n").encode("ascii",
                                                      "backslashreplace"))


def _marker_matches(run_dir: Path, plan: SweepPlan, index: int,
                    slug: str) -> bool:
    path = Path(run_dir) / RUN_MARKER_NAME
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text("ascii"))
    except (ValueError, OSError):
        return False
    return (payload.get("sweep_id") == plan.sweep_id
            and payload.get("step") == int(index)
            and payload.get("slug") == slug
            and payload.get("plan_digest") == plan.identity_digest())


def _clear_previous_attempt(run_dir: Path, plan: SweepPlan, index: int,
                            slug: str,
                            say: Callable[[str], None]) -> List[str]:
    run_dir = Path(run_dir)
    results = run_dir / "results"
    # rglob, not iterdir: a nested tree under results/ is content too, and
    # listing only top-level files made a directory holding
    # results/sub/results_PC_Nd.csv read as empty -- ownership claimed, the
    # foreign tree merged into this step's output.
    present = (sorted(p for p in results.rglob("*") if p.is_file())
               if results.is_dir() else [])
    if not present:
        _write_run_marker(run_dir, plan, index, slug)
        return []
    if not _marker_matches(run_dir, plan, index, slug):
        raise Ercot7kSweepError(
            "%s already holds %d result file(s) that are not this step's: "
            "there is no marker saying step %d of sweep %r, running this "
            "exact plan, wrote them. A run directory can survive its layers, "
            "so the write-once layer check does not cover this, and deleting "
            "them is not this driver's call. Use a different --sweep-id or "
            "--runs-root, or move that directory aside."
            % (results, len(present), index, plan.sweep_id))
    names = [str(p.relative_to(results)) for p in present]
    for path in present:
        path.unlink()
    _write_run_marker(run_dir, plan, index, slug)
    say("  cleared %d file(s) left by an earlier attempt at this step; its "
        "logs are kept" % len(names))
    return names


# ------------------------------------------------------------------------------
# prune_results()
#
# Opt-in. A step writes 442 MB and a nine-step sweep is 4 GB, so an operator may
# want the bulk tables gone once the artifacts are written -- PC_Nd alone is
# 287 MB of per-node LMP that the mapped artifacts already carry at the pinned
# interval.
#
# Three rules, because deleting results is the one irreversible thing in here:
#   - opt-in, never a default
#   - only inside a directory that carries PSO's own results_MC_Solution.csv,
#     so a mistyped path cannot delete something that is not a results directory
#   - only files named results_*.csv, and never one of KEEP_TABLES, so the
#     costs, the solve census and the load can still be re-derived
# ------------------------------------------------------------------------------
KEEP_TABLES: Tuple[str, ...] = ("MC_Solution", "MC_Hrzn", "ED_Ara", "PN_Pth")


def prune_results(results_dir: Path) -> List[str]:
    results_dir = Path(results_dir)
    marker = results_dir / "results_MC_Solution.csv"
    if not marker.is_file():
        raise Ercot7kSweepError(
            "%s does not look like a PSO results directory (no %s), so nothing "
            "was pruned" % (results_dir, marker.name))
    keep = {("results_%s.csv" % name) for name in KEEP_TABLES}
    removed: List[str] = []
    for path in sorted(results_dir.glob("results_*.csv")):
        if path.name in keep:
            continue
        path.unlink()
        removed.append(path.name)
    return removed


def _dir_mb(path: Path) -> float:
    path = Path(path)
    if not path.is_dir():
        return 0.0
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return total / (1024.0 * 1024.0)


# ------------------------------------------------------------------------------
#   The verdict -- W1..W5
# ------------------------------------------------------------------------------
# This is the part devnet's sweep has no equivalent of, and the reason the
# module exists. Every check below can only be answered by the sweep's own
# output, which is the property the task notes asked for: "a sweep which failed
# to apply is detectable from its own output".
# ------------------------------------------------------------------------------
def check_sweep(plan: SweepPlan,
                outcomes: Sequence[StepOutcome]) -> List[ec.Finding]:
    findings: List[ec.Finding] = []
    witness = plan.witness
    done = [o for o in outcomes if o.ok()]

    if len(done) < len(plan.values):
        findings.append(ec.Finding(
            "W0", ec.LEVEL_ERROR,
            "%d of %d steps completed; the sweep is partial and its curve has "
            "holes. Failed steps: %s"
            % (len(done), len(plan.values),
               ", ".join("%s=%s (%s)" % (plan.lever,
                                         value_text(o.value, plan.decimals),
                                         o.error or "exit %d" % o.returncode)
                         for o in outcomes if not o.ok()) or "none recorded")))
    else:
        findings.append(ec.Finding(
            "W0", ec.LEVEL_OK,
            "all %d steps completed" % len(plan.values)))

    findings.append(_check_records_match_plan(plan, outcomes))

    if len(done) < 2:
        for check in ("W1", "W2", "W3", "W4", "W6"):
            findings.append(ec.Finding(
                check, ec.LEVEL_SKIP,
                "fewer than two completed steps, so no witness comparison is "
                "possible. A SKIP here is not a pass: the sweep is "
                "unverified."))
        return findings

    missing = [o for o in done if not _finite(o.witness)]
    if missing:
        detail = ""
        if plan.lever == "k_line":
            detail = (" The cause is the reporting scope: PN_Pth covers "
                      "enforced paths plus those security analysis identified "
                      "for enforcement, so branch %r is absent from any "
                      "interval where it was slack -- which is expected on a "
                      "step that does not derate it far enough to bind, and "
                      "is NOT by itself evidence of a broken sweep. The "
                      "documented remedy is PSO's ReportAllSolvedPaths option "
                      "(PN_Pth.md), which reports every monitored path; W6 "
                      "then carries the question of whether the limit was "
                      "actually enforced, which is the part that matters."
                      % plan.target)
        if plan.lever == "k_gen":
            detail = (" ED_Inj reports every injector in every interval, so an "
                      "absent witness here is NOT the PN_Pth reporting-scope "
                      "problem. It is read_witness() refusing to report a "
                      "Max of 0 under a positive Cap: ED_Inj.md sets Max to "
                      "zero when a unit is off or was not committed, and "
                      "neither partial mode can ask for a cap of zero, so that "
                      "reading is an unavailable unit rather than a derated "
                      "one. Injector %r was off at the pinned interval on "
                      "those steps -- pin an interval where it runs, or sweep "
                      "a unit that is committed there." % plan.target)
        # Severity follows W6's rule, and for the same physical reason: a
        # corridor slack at the top of the range and binding at the bottom is
        # the experiment worth running, and this check used to fail it with an
        # ERROR while its own message said the absence "is NOT by itself
        # evidence of a broken sweep". A check may not contradict its own text.
        # No step measured at all IS a broken sweep; some steps unmeasured is a
        # curve with holes in it, and the holes are named.
        all_missing = len(missing) == len(done)
        findings.append(ec.Finding(
            "W1", ec.LEVEL_ERROR if all_missing else ec.LEVEL_WARNING,
            "%s is not reported at the pinned interval for %d of %d steps "
            "(%s), so %s.%s"
            % (witness.column, len(missing), len(done),
               ", ".join(value_text(o.value, plan.decimals) for o in missing),
               "this sweep is unverified end to end" if all_missing
               else "those steps are UNVERIFIED -- read their response "
                    "columns as unchecked, not as passed",
               detail)))
    else:
        findings.append(ec.Finding(
            "W1", ec.LEVEL_OK,
            "%s is reported at the pinned interval for all %d steps"
            % (witness.column, len(done))))

    measured = [o for o in done if _finite(o.witness)]
    if len(measured) < 2:
        # Emitting NOTHING here is how relaxing W1 to a WARNING turned an
        # entirely unverified sweep green: with one measured step the checks
        # below simply did not run, and verdict_exit_code can only see
        # findings that EXIST -- so its stated safety net ("a SKIP is not a
        # pass") had nothing to fire on. The floor is lowered, not removed:
        # the comparison is skipped, says so, and the exit code refuses it.
        for check in ("W2", "W3", "W4", "W6"):
            findings.append(ec.Finding(
                check, ec.LEVEL_SKIP,
                "only %d step(s) have a measured witness, so there is nothing "
                "to compare across steps and the check this driver exists to "
                "perform did not run. A SKIP is not a pass: the sweep is "
                "UNVERIFIED." % len(measured)))

    if len(measured) >= 2:
        distinct = sorted({round(o.witness, 6) for o in measured})
        if len(distinct) == 1:
            findings.append(ec.Finding(
                "W2", ec.LEVEL_ERROR,
                "%s is %s at EVERY step, so the sweep did not happen: the "
                "lever never reached the solver and every response in this "
                "table is the same case solved %d times. This is devnet's "
                "run_sweep_line defect -- the loop variable labels the output "
                "row and is never applied -- and it is the one failure a sweep "
                "summary otherwise cannot show."
                % (witness.column, _fmt(distinct[0]), len(measured))))
        else:
            findings.append(ec.Finding(
                "W2", ec.LEVEL_OK,
                "%s takes %d distinct values across %d steps (%s .. %s)"
                % (witness.column, len(distinct), len(measured),
                   _fmt(distinct[0]), _fmt(distinct[-1]))))

        findings.append(_check_witness_matches_input(plan, measured, witness))
        findings.append(_check_monotone(plan, measured, witness))

    statuses = sorted({o.status for o in done if o.status})
    if statuses and statuses != ["Optimal"]:
        findings.append(ec.Finding(
            "W5", ec.LEVEL_WARNING,
            "not every step solved to Optimal: %s. That is a result, not "
            "necessarily a fault -- but the costs of a non-Optimal step are "
            "not comparable with the rest of the curve."
            % ", ".join(statuses)))
    elif statuses:
        findings.append(ec.Finding(
            "W5", ec.LEVEL_OK, "every step solved Optimal"))

    if len(measured) >= 2:
        findings.append(_check_enforced(plan, measured, witness))
    return findings


# ------------------------------------------------------------------------------
# _check_records_match_plan()  -- W7
#
# Does record i actually describe plan value i, and are there exactly as many
# records as steps?
#
# Nothing else asks this. W0 only COUNTS completed steps, and W3 compares
# `witness` against `witness_written` -- for an absolute lever those are two
# fields of the SAME record, so a record the plan never asked for agrees with
# itself perfectly and passes. That is the gap through which a resumed or
# hand-assembled sweep directory can report values nobody requested with a
# clean verdict, and it is also what makes `check` unable to audit a directory
# it is simply handed.
#
# A proportional lever is accidentally protected, because W3's ratio test
# notices a wrong value. Accidental protection for one of two levers is not a
# check.
# ------------------------------------------------------------------------------
def _check_records_match_plan(plan: SweepPlan,
                              outcomes: Sequence[StepOutcome]) -> ec.Finding:
    problems: List[str] = []
    # A sweep that stopped early -- a failed step, the disk guard, or `check`
    # run while it is still going -- has FEWER records than steps, and that is
    # not a correspondence failure: W0 already reports the hole, accurately.
    # Saying "nothing below is about the sweep that was asked for" of a
    # correct prefix would be this driver telling the operator more than it
    # knows, which is the thing it is otherwise careful never to do. Only
    # records BEYOND the plan are a mismatch.
    if len(outcomes) > len(plan.values):
        problems.append("the plan has %d steps and there are %d step records"
                        % (len(plan.values), len(outcomes)))
    for position, outcome in enumerate(outcomes):
        if position >= len(plan.values):
            problems.append("record %d (%s) has no step in the plan"
                            % (outcome.index,
                               value_text(outcome.value, plan.decimals)))
            continue
        expected = plan.values[position]
        if not _same_value(outcome.value, expected, plan.decimals):
            problems.append(
                "record %d says %s where the plan says %s"
                % (outcome.index, value_text(outcome.value, plan.decimals),
                   value_text(expected, plan.decimals)))
        elif outcome.slug != plan.slug(expected):
            problems.append(
                "record %d is slug %s where the plan's step %s is %s"
                % (outcome.index, outcome.slug,
                   value_text(expected, plan.decimals), plan.slug(expected)))
    if problems:
        return ec.Finding(
            "W7", ec.LEVEL_ERROR,
            "the step records do not correspond to the plan: %s. Every other "
            "check reads these records, so until this agrees nothing below it "
            "is about the sweep that was asked for."
            % "; ".join(problems))
    if len(outcomes) < len(plan.values):
        return ec.Finding(
            "W7", ec.LEVEL_OK,
            "the %d step record(s) present correspond to the plan's first %d "
            "steps; the sweep stopped early and W0 carries that"
            % (len(outcomes), len(outcomes)))
    return ec.Finding(
        "W7", ec.LEVEL_OK,
        "all %d step records correspond to the plan, step for step"
        % len(outcomes))


# ------------------------------------------------------------------------------
# _check_witness_matches_input()  -- W3
#
# The strong form: does the number PSO reported equal the number the case asked
# for? For an absolute lever both exist as artifacts on disk and the comparison
# is direct. For a proportional one the lever is a factor and the witness is a
# level, so the comparison is between ratios, referenced to the first step.
#
# A lever that applied on SOME steps and not others passes W2 and fails here,
# which is why W2 is not enough on its own.
# ------------------------------------------------------------------------------
def _check_witness_matches_input(plan: SweepPlan,
                                 measured: Sequence[StepOutcome],
                                 witness: Witness) -> ec.Finding:
    bad: List[str] = []
    if witness.kind == "absolute":
        for outcome in measured:
            if not _finite(outcome.witness_written):
                bad.append("%s: the layer records no written value"
                           % value_text(outcome.value, plan.decimals))
            elif not _close(outcome.witness, outcome.witness_written):
                bad.append("%s: case wrote %s, results report %s"
                           % (value_text(outcome.value, plan.decimals),
                              _fmt(outcome.witness_written),
                              _fmt(outcome.witness)))
        if bad:
            return ec.Finding(
                "W3", ec.LEVEL_ERROR,
                "%s disagrees with what the case file wrote on %d step(s): %s. "
                "The layer and the results are two independent artifacts; when "
                "they disagree, PSO did not enforce the value it was handed."
                % (witness.column, len(bad), "; ".join(bad)))
        return ec.Finding(
            "W3", ec.LEVEL_OK,
            "%s matches the value each layer wrote, on all %d steps"
            % (witness.column, len(measured)))

    reference = measured[0]
    if reference.value == 0.0 or not _finite(reference.witness):
        return ec.Finding(
            "W3", ec.LEVEL_SKIP,
            "the first step cannot be a ratio reference (value %s, witness "
            "%s), so the proportional check did not run. A SKIP is not a pass."
            % (value_text(reference.value, plan.decimals),
               _fmt(reference.witness)))
    for outcome in measured[1:]:
        expected = reference.witness * (outcome.value / reference.value)
        if not _close(outcome.witness, expected):
            bad.append("%s: expected %s, got %s"
                       % (value_text(outcome.value, plan.decimals),
                          _fmt(expected), _fmt(outcome.witness)))
    if bad:
        return ec.Finding(
            "W3", ec.LEVEL_ERROR,
            "%s does not scale with %s on %d step(s): %s. The lever is a "
            "multiplier on this quantity, so a step that moved by anything "
            "other than its own factor did not apply as asked."
            % (witness.column, plan.lever, len(bad), "; ".join(bad)))
    return ec.Finding(
        "W3", ec.LEVEL_OK,
        "%s scales with %s across all %d steps, referenced to %s=%s. NOTE "
        "this is a RELATIVE check: it fixes the shape of the curve, not its "
        "level, so a lever applied with a constant factor wrong at every step "
        "would pass it. Only the absolute form (k_line) compares against a "
        "number the case file states."
        % (witness.column, plan.lever, len(measured), plan.lever,
           value_text(reference.value, plan.decimals)))


# ------------------------------------------------------------------------------
# _check_enforced()  -- W6
#
# W3 asks whether the results echo the value the case asked for. W6 asks the
# question W3 cannot: was that value ever actually in the LP?
#
# For k_line the two are genuinely separable, and the gap is not theoretical.
# PN_Pth.Max is the limit; MinEnforced/MaxEnforced say whether it was enforced.
# This case carries Enforce=0 on all 9,140 branches, so nothing is enforced
# except what CYC_SAI discovery finds -- and the committed reference run, which
# reports all 1,171 monitored paths, is mostly rows of Max=<the file's number>
# with neither side enforced and SolverMw=0. Turn on ReportAllSolvedPaths (the
# documented fix for this study's open reporting-scope question) and every step
# of a k_line sweep would report its derated limit, agree with the layer to the
# digit, and mean nothing. W3 would be green on a sweep with no effect whatever.
#
# WARNING, paid for: read BOTH sides. The first version of this check tested
# MaxEnforced alone, and measured against the reference run that would have
# raised ERROR on the study's flagship corridor -- N210144_N210332_1 is
# enforced on Min in 168 of 168 RT intervals and on Max in none, because the
# flow runs Riesel to Hewitt and binds against the negative limit. A check that
# fails the one sweep already validated by hand is worse than no check.
#
# The rule is per-sweep rather than per-step, deliberately. A corridor that is
# slack at k=1.0 and binds at k=0.8 is a GOOD sweep, and failing its first step
# would punish exactly the experiment worth running. What cannot be tolerated
# is a sweep where the limit was enforced at no step at all: there the lever
# moved a number that never reached the solver.
# ------------------------------------------------------------------------------
# For k_gen there is no enforcement flag to read, and inventing an analogue of
# one would be the worse answer. An injector dispatch limit is not discovered
# the way a branch limit is: SCN_INJ_MAX restricts ED's own Max directly, so the
# question "did it reach the LP" has a different observable -- whether dispatch
# OBEYED it. That is a check with teeth rather than a tautology only because
# PSO's dispatch limits are SOFT: ED_Inj.LimitViolation is "(MW) violation of
# dispatch limits", so a cap reported and not applied shows up as a positive
# violation instead of an infeasible solve.
#
# It is a weaker claim than k_line's and says so. What it cannot distinguish is
# a cap that was applied from a cap that was never binding, which is why the
# absolute comparison in W3 carries the weight here: the MW in the case file
# against the MW in the result file, two independent artifacts.
def _check_enforced(plan: SweepPlan, measured: Sequence[StepOutcome],
                    witness: Witness) -> ec.Finding:
    if witness.enforcement == "none":
        return ec.Finding(
            "W6", ec.LEVEL_SKIP,
            "%s is consumed unconditionally by the power balance, so there is "
            "no separate 'was it enforced' question for %s"
            % (witness.column, plan.lever))

    if witness.enforcement == "respected":
        known = [o for o in measured if _finite(o.witness_enforced)]
        if not known:
            return ec.Finding(
                "W6", ec.LEVEL_WARNING,
                "no step reports a readable ED_Inj.P beside %s, so whether "
                "dispatch respected the cap cannot be established. The cap on "
                "its own is an echo of the case file: treat W3 as proof that "
                "the case was written, not that it constrained the solve."
                % witness.column)
        broken = [o for o in known if o.witness_enforced != 1.0]
        if broken:
            return ec.Finding(
                "W6", ec.LEVEL_ERROR,
                "%s was reported at every step, but at %d of %d the solution "
                "dispatched %s ABOVE it (ED_Inj.LimitViolation is positive, or "
                "P exceeds Max): %s. PSO's injector dispatch limits are soft "
                "slacks, so a cap that was written and reported can still be "
                "bought out rather than enforced -- read those steps as a "
                "priced overshoot, not as a derate."
                % (witness.column, len(broken), len(known), plan.target,
                   ", ".join("%s=%s" % (plan.lever,
                                        value_text(o.value, plan.decimals))
                             for o in broken[:5])))
        return ec.Finding(
            "W6", ec.LEVEL_OK,
            "dispatch of %s stayed at or below %s with no LimitViolation at "
            "all %d measured steps, so the cap was a constraint on the "
            "solution and not only a number in the report"
            % (plan.target, witness.column, len(known)))

    if witness.enforcement != "bit":
        raise Ercot7kSweepError(
            "witness %s declares enforcement %r, which _check_enforced() has "
            "no branch for. A new enforcement kind needs its own check, not "
            "the branch-limit one by default."
            % (witness.column, witness.enforcement))

    known = [o for o in measured if _finite(o.witness_enforced)]
    if not known:
        return ec.Finding(
            "W6", ec.LEVEL_WARNING,
            "these results carry no MinEnforced/MaxEnforced column, so "
            "whether the derated limit actually entered the LP cannot be "
            "established. %s on its own is an echo of the case file. Treat W3 "
            "as proof that the case was written, not that it was solved."
            % witness.column)

    enforced = [o for o in known if o.witness_enforced == 1.0]
    if not enforced:
        return ec.Finding(
            "W6", ec.LEVEL_ERROR,
            "%s was reported at every step but the limit was enforced at "
            "NEITHER bound at ALL %d of them, so the limit this sweep derates "
            "was never in the solution. The steps agree with the case file and "
            "changed nothing: on this case Enforce=0 on every branch, so a "
            "limit only reaches the LP if CYC_SAI discovery identifies it. "
            "Pick a corridor that binds, or derate far enough that it does."
            % (witness.column, len(known)))

    slack = [o for o in known if o.witness_enforced != 1.0]
    if slack:
        return ec.Finding(
            "W6", ec.LEVEL_WARNING,
            "the derated limit was enforced at %d of %d measured steps; not "
            "enforced at %s. Those steps are consistent with the case file but "
            "did not constrain the solution, which is expected where the "
            "corridor is still slack -- read their response columns as "
            "unchanged by the lever rather than as a response to it."
            % (len(enforced), len(known),
               ", ".join("%s=%s" % (plan.lever,
                                    value_text(o.value, plan.decimals))
                         for o in slack)))
    return ec.Finding(
        "W6", ec.LEVEL_OK,
        "the derated limit was enforced in the solution at all %d measured "
        "steps, so %s is evidence the lever reached the LP and not only the "
        "case file" % (len(enforced), witness.column))


def _enforced_text(lever: str, mode: str, enforced: float) -> str:
    witness = witness_for(lever, mode)
    if witness.enforcement == "none":
        return ""
    if witness.enforcement == "respected":
        if not _finite(enforced):
            return "  [cap respected: unknown -- no LimitViolation column]"
        return "  [cap respected: %s]" % ("yes" if enforced == 1.0 else "NO")
    if not _finite(enforced):
        return "  [enforced: unknown -- no MaxEnforced column]"
    return "  [enforced: %s]" % ("yes" if enforced == 1.0 else "NO")


# ------------------------------------------------------------------------------
# _check_monotone()  -- W4
#
# Both witnesses are a positive multiple of the lever value, so the readback
# must rise with it. A warning rather than an error: W3 is the quantitative
# check and would already have failed, so a monotonicity break that survives it
# is more likely to be something unmodelled than a broken sweep -- but it should
# never pass unremarked.
# ------------------------------------------------------------------------------
def _check_monotone(plan: SweepPlan, measured: Sequence[StepOutcome],
                    witness: Witness) -> ec.Finding:
    ordered = sorted(measured, key=lambda o: o.value)
    values = [o.witness for o in ordered]
    rising = all(b >= a for a, b in zip(values, values[1:]))
    if rising:
        return ec.Finding(
            "W4", ec.LEVEL_OK,
            "%s rises with %s, as a multiplier on it must"
            % (witness.column, plan.lever))
    return ec.Finding(
        "W4", ec.LEVEL_WARNING,
        "%s is not monotone in %s across the sweep: %s. Both implemented "
        "witnesses are positive multiples of the lever, so this should not "
        "happen; read W3 before reading any response column."
        % (witness.column, plan.lever,
           ", ".join("%s->%s" % (value_text(o.value, plan.decimals),
                                 _fmt(o.witness)) for o in ordered)))


# ------------------------------------------------------------------------------
#   Output
# ------------------------------------------------------------------------------
# The leading columns are fixed and in reading order: what was asked, what came
# back, and whether the two agree -- before any response variable. A reader who
# stops after four columns has still seen whether the sweep happened.
LEAD_COLUMNS: Tuple[str, ...] = (
    "step", "lever", "target", "value",
    # witness_expected, not witness_written: for an absolute lever it IS what
    # the layer wrote, but for a proportional one it is a value computed from
    # the reference step, and a column named "written" would be read as
    # provenance it does not have.
    "witness", "witness_expected", "witness_column", "witness_ok",
    "witness_enforced",
    "status", "solves", "seconds", "results_mb",
)
TAIL_COLUMNS: Tuple[str, ...] = ("layer", "run_dir", "error")


def summary_rows(plan: SweepPlan,
                 outcomes: Sequence[StepOutcome]) -> List[Dict[str, Any]]:
    witness = plan.witness
    rows: List[Dict[str, Any]] = []
    reference = next((o for o in outcomes if o.ok() and _finite(o.witness)),
                     None)
    for outcome in outcomes:
        if witness.kind == "absolute":
            expected = outcome.witness_written
        elif reference is not None and reference.value != 0.0:
            expected = reference.witness * (outcome.value / reference.value)
        else:
            expected = math.nan
        row: Dict[str, Any] = {
            "step": outcome.index,
            "lever": plan.lever,
            "target": plan.target,
            "value": outcome.value,
            "witness": outcome.witness,
            "witness_expected": expected,
            "witness_column": witness.column,
            "witness_ok": int(_close(outcome.witness, expected)),
            "witness_enforced": outcome.witness_enforced,
            "status": outcome.status,
            "solves": outcome.solves,
            "seconds": round(outcome.seconds, 1),
            "results_mb": round(outcome.results_mb, 1),
            "layer": outcome.layer,
            "run_dir": outcome.run_dir,
            "error": outcome.error,
        }
        row.update(outcome.figures)
        rows.append(row)
    return rows


def summary_columns(rows: Sequence[Dict[str, Any]]) -> List[str]:
    extra = sorted({key for row in rows for key in row}
                   - set(LEAD_COLUMNS) - set(TAIL_COLUMNS))
    return list(LEAD_COLUMNS) + extra + list(TAIL_COLUMNS)


def write_summary(sweep_dir: Path, plan: SweepPlan,
                  outcomes: Sequence[StepOutcome]) -> Path:
    rows = summary_rows(plan, outcomes)
    path = Path(sweep_dir) / SUMMARY_NAME
    er.write_frame_csv(path, rows, summary_columns(rows))
    return path


def write_plan(sweep_dir: Path, plan: SweepPlan) -> Path:
    path = Path(sweep_dir) / SWEEP_NAME
    text = json.dumps(plan.as_dict(), indent=2)
    path.write_bytes((text + "\n").encode("ascii"))
    return path


# The identity of a sweep: change any of these and the step records already on
# disk describe something else. Cost and cosmetic fields (slug_prefix aside,
# which changes directory names) are deliberately not in here.
PLAN_IDENTITY = ("parent", "lever", "target", "mode", "values", "slug_prefix",
                 "decimals")


def assert_plan_unchanged(sweep_dir: Path, plan: SweepPlan) -> None:
    """Refuses to reuse a sweep id whose recorded plan differs from this one."""
    path = Path(sweep_dir) / SWEEP_NAME
    if not path.is_file():
        return
    try:
        recorded = read_plan(path.parent).as_dict()
    except Ercot7kSweepError:
        raise
    current = plan.as_dict()
    differs = [key for key in PLAN_IDENTITY if recorded.get(key) != current.get(key)]
    if recorded.get("report") != current.get("report"):
        differs.append("report")
    if not differs:
        return
    raise Ercot7kSweepError(
        "sweep id %r already records a different sweep, differing in: %s. "
        "Reusing the id would overwrite %s -- the only record of what was "
        "asked for -- and, on --resume, report the earlier run's results "
        "under this plan's labels with every witness check passing. Use a new "
        "--sweep-id, or delete %s if the earlier sweep is finished with."
        % (plan.sweep_id, ", ".join(differs), SWEEP_NAME, sweep_dir))


def step_record_name(index: int) -> str:
    """Three digits so a lexicographic sort of step_*.json stays numeric: at
    two, step_100 sorts before step_99 and read_outcomes silently reorders the
    curve. A 17-step sweep is already among the devnet presets."""
    return "step_%03d.json" % index


def _same_value(left: float, right: float, decimals: int) -> bool:
    return _round(left, decimals) == _round(right, decimals)


def read_plan(sweep_dir: Path) -> SweepPlan:
    path = Path(sweep_dir) / SWEEP_NAME
    if not path.is_file():
        raise Ercot7kSweepError("%s has no %s" % (sweep_dir, SWEEP_NAME))
    payload = json.loads(path.read_text("ascii"))
    if payload.get("schema") != SWEEP_SCHEMA:
        raise Ercot7kSweepError(
            "%s has schema %r, expected %r"
            % (path, payload.get("schema"), SWEEP_SCHEMA))
    report = payload["report"]
    return SweepPlan(
        sweep_id=payload["sweep_id"],
        parent=Path(payload["parent"]),
        lever=payload["lever"],
        target=payload.get("target", ""),
        mode=payload["mode"],
        values=[float(v) for v in payload["values"]],
        key=er.ReportKey(cycle=report["cycle"], scenario=report["scenario"],
                         interval=int(report["interval"])),
        pinned_by=Path(payload.get("pinned_by", "")),
        slug_prefix=payload.get("slug_prefix", ""),
        decimals=int(payload.get("decimals", DEFAULT_DECIMALS)),
    )


def read_outcomes(sweep_dir: Path) -> List[StepOutcome]:
    sweep_dir = Path(sweep_dir)
    outcomes: List[StepOutcome] = []
    for path in sorted(sweep_dir.glob("step_*.json")):
        outcomes.append(outcome_from_dict(json.loads(path.read_text("ascii"))))
    return outcomes


def report_text(plan: SweepPlan, outcomes: Sequence[StepOutcome],
                findings: Sequence[ec.Finding]) -> str:
    witness = plan.witness
    lines: List[str] = []
    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    lines.append("ercot7k sweep report -- %s" % plan.sweep_id)
    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    lines.append("parent      : %s" % plan.parent)
    lines.append("lever       : %s %s%s"
                 % (plan.lever, plan.mode,
                    (" on %s" % plan.target) if plan.target else ""))
    lines.append("steps       : %s"
                 % ", ".join(value_text(v, plan.decimals)
                             for v in plan.values))
    lines.append("pinned at   : %s / %s / interval %d  (from %s)"
                 % (plan.key.cycle, plan.key.scenario, plan.key.interval,
                    plan.pinned_by))
    lines.append("witness     : %s (%s, %s)"
                 % (witness.column, witness.kind, witness.unit))
    lines.append("              %s" % witness.note)
    lines.append("")
    lines.append(SUBSECTION_SEPARATOR.rstrip("\n"))
    lines.append("%-6s %-12s %-14s %-14s %-9s %8s"
                 % ("step", plan.lever, witness.column, "expected", "agree",
                    "secs"))
    for row in summary_rows(plan, outcomes):
        lines.append("%-6d %-12s %-14s %-14s %-9s %8.1f"
                     % (row["step"], value_text(row["value"], plan.decimals),
                        _fmt(row["witness"]), _fmt(row["witness_expected"]),
                        "yes" if row["witness_ok"] else "NO",
                        row["seconds"]))
    lines.append("")
    lines.append(SUBSECTION_SEPARATOR.rstrip("\n"))
    lines.append("Verdict:")
    lines.append(ec.format_findings(list(findings)))
    lines.append("")
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    """'not measured' rather than 'nan', because the two are read differently:
    nan invites a reader to treat it as a missing number, and this one means the
    quantity was never reported at all."""
    if isinstance(value, float):
        return format(value, ",.3f") if math.isfinite(value) else "not measured"
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------
# verdict_exit_code()
#
# Non-zero on an ERROR, and equally on a SKIPPED witness comparison.
#
# The module says in several messages that a SKIP is not a pass, and the exit
# code has to agree or the sentence is decoration: a sweep whose witness could
# not be compared is UNVERIFIED, and CI reading only the exit status would
# record it as green. W4 and W6 may legitimately skip (monotonicity of one
# point, enforcement of a proportional lever); W1 and W3 are the comparison
# itself.
# ------------------------------------------------------------------------------
VERIFYING_CHECKS = ("W1", "W3")


def verdict_exit_code(findings: Sequence[ec.Finding]) -> int:
    if ec.has_errors(findings):
        return 1
    skipped = [f.check for f in findings
               if f.check in VERIFYING_CHECKS and f.level == ec.LEVEL_SKIP]
    return 1 if skipped else 0


# ------------------------------------------------------------------------------
# projection()
#
# Wall clock and disk, printed BEFORE a sweep starts. A nine-step sweep is close
# to an hour and 4 GB; both numbers are worth seeing while the command can still
# be retyped, and the disk one is worth refusing on -- filling the volume at
# step 7 loses the six steps already solved along with everything else on it.
# ------------------------------------------------------------------------------
def projection(plan: SweepPlan, target_dir: Path) -> Dict[str, float]:
    steps = len(plan.values)
    need_mb = steps * ESTIMATED_RUN_MB
    try:
        free_mb = shutil.disk_usage(str(target_dir)).free / (1024.0 * 1024.0)
    except OSError:
        free_mb = math.nan
    return {
        "steps": float(steps),
        "minutes": steps * ESTIMATED_RUN_MINUTES,
        "results_mb": need_mb,
        "free_mb": free_mb,
        # Unmeasurable free space is NOT a pass. It used to be: an unreadable
        # path gave NaN and the guard reported "fits", which is the module's
        # own "a SKIP is not a pass" rule broken by its own disk check.
        "fits": float(_finite(free_mb)
                      and free_mb - need_mb >= DISK_MARGIN_MB),
        "measured": float(_finite(free_mb)),
    }


# ------------------------------------------------------------------------------
#   CLI
# ------------------------------------------------------------------------------
def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--parent", required=True,
                        help="the case directory each step builds on")
    parser.add_argument("--lever", required=True,
                        help="sweepable lever/mode pairs: %s"
                             % sweepable_text())
    parser.add_argument("--target", default="",
                        help="branch for k_line, injector for k_gen; blank "
                             "for k_load")
    parser.add_argument("--mode", default="scale",
                        help="scale for k_line and k_load; for k_gen, derate "
                             "(an absolute MW cap on a unit with no "
                             "availability schedule) or avail (a factor on a "
                             "unit that has one)")
    parser.add_argument("--kmin", type=float, required=True)
    parser.add_argument("--kmax", type=float, required=True)
    parser.add_argument("--kstep", type=float, required=True)
    parser.add_argument("--decimals", type=int, default=DEFAULT_DECIMALS)
    parser.add_argument("--slug-prefix", default="",
                        help="disambiguates two sweeps of the same lever and "
                             "values on different targets")
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument("--sweeps-root", default=None)
    parser.add_argument("--derived-root", default=None)
    parser.add_argument("--runs-root", default=None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ercot7k_sweep.py",
        description=("Sweep one stress lever across a range on the ERCOT "
                     "Texas7k PSO case, with a witness that says whether the "
                     "lever was applied."),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    planner = sub.add_parser(
        "plan", help="print the steps, the witness and the cost, then stop")
    _add_plan_arguments(planner)

    runner = sub.add_parser("run", help="build, solve and map every step")
    _add_plan_arguments(runner)
    runner.add_argument("--resume", action="store_true",
                        help="skip steps whose record is already complete")
    runner.add_argument("--prune", action="store_true",
                        help="delete the bulk result tables of each step once "
                             "its artifacts are written (keeps %s)"
                             % ", ".join(KEEP_TABLES))
    runner.add_argument("--keep-going", action="store_true",
                        help="do not stop the sweep on a failed step")
    runner.add_argument("--skip-disk-check", action="store_true")

    checker = sub.add_parser(
        "check", help="re-run the verdict over an existing sweep directory")
    checker.add_argument("sweep_dir")
    return parser


# ------------------------------------------------------------------------------
# enough_disk_for_step()
#
# The between-steps disk check. `projection()` runs once, before the sweep,
# against a 450 MB/step estimate; this runs before each later step against the
# size the finished steps actually came to, which is the only figure that
# knows about --prune, a shorter horizon, or a case that writes more than the
# shipped one.
#
# The point is to stop with the completed steps intact. Running out of space
# mid-solve loses the step being written AND whatever else shares the volume,
# which on this machine includes the other repos.
# ------------------------------------------------------------------------------
def enough_disk_for_step(runs_root: Path,
                         measured_mb: Sequence[float]) -> Tuple[bool, str]:
    # These must be PEAK sizes, not post-prune ones: --prune shrinks what a
    # finished step leaves behind, but the next step still writes the whole
    # ~442 MB before anything is pruned, so sizing on the retained figure
    # would reserve about a tenth of what is actually needed.
    sizes = [mb for mb in measured_mb if mb > 0.0]
    need = (sum(sizes) / len(sizes)) if sizes else ESTIMATED_RUN_MB
    try:
        free_mb = shutil.disk_usage(
            str(_nearest_existing(runs_root))).free / (1024.0 * 1024.0)
    except OSError:
        return True, ""  # already reported before the sweep started
    if free_mb - need >= DISK_MARGIN_MB:
        return True, ""
    return False, (
        "only %.1f GB free at %s and the last steps averaged %.0f MB each, "
        "which leaves less than the %.1f GB margin. Stopping here so the "
        "completed steps survive; free space or use --prune, then --resume."
        % (free_mb / 1024.0, runs_root, need, DISK_MARGIN_MB / 1024.0))


def _nearest_existing(path: Path) -> Path:
    """The first ancestor that exists, so disk_usage measures the volume the
    sweep will write to rather than failing on a root two levels deep that has
    not been created yet."""
    path = Path(path).resolve()
    for candidate in [path] + list(path.parents):
        if candidate.exists():
            return candidate
    return path


def _roots(args: argparse.Namespace) -> Tuple[Path, Path, Path]:
    sweeps = Path(args.sweeps_root or (SCRIPT_DIR / SWEEPS_DIRNAME))
    derived = Path(args.derived_root or (SCRIPT_DIR / DERIVED_DIRNAME))
    runs = Path(args.runs_root or (SCRIPT_DIR / RUNS_DIRNAME))
    return sweeps, derived, runs


def _print_plan(plan: SweepPlan, projected: Dict[str, float]) -> None:
    witness = plan.witness
    print(SECTION_SEPARATOR, end="")
    print("ercot7k sweep plan -- %s" % plan.sweep_id)
    print(SECTION_SEPARATOR, end="")
    print("parent      : %s" % plan.parent)
    print("lever       : %s %s%s"
          % (plan.lever, plan.mode,
             (" on %s" % plan.target) if plan.target else ""))
    print("steps       : %d -- %s"
          % (len(plan.values),
             ", ".join(value_text(v, plan.decimals) for v in plan.values)))
    shown = [ec.layer_dir_name(plan.parent, plan.slug(v))
             for v in plan.values[:2]]
    if len(plan.values) > 3:
        shown.append("...")
    if len(plan.values) > 2:
        shown.append(ec.layer_dir_name(plan.parent, plan.slug(plan.values[-1])))
    print("layers      : %s" % ", ".join(shown))
    print("pinned at   : %s / %s / interval %d  (from %s)"
          % (plan.key.cycle, plan.key.scenario, plan.key.interval,
             plan.pinned_by))
    print("witness     : %s (%s, %s)"
          % (witness.column, witness.kind, witness.unit))
    print("              %s" % witness.note)
    print("")
    print("projected   : ~%.0f min, ~%.1f GB of results"
          % (projected["minutes"], projected["results_mb"] / 1024.0))
    if projected["measured"]:
        print("free space  : %.1f GB" % (projected["free_mb"] / 1024.0))
    else:
        print("free space  : could not be measured (not a pass -- 'run' will "
              "refuse without --skip-disk-check)")
    print("")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "check":
        sweep_dir = Path(args.sweep_dir)
        try:
            plan = read_plan(sweep_dir)
            outcomes = read_outcomes(sweep_dir)
        except Ercot7kSweepError as exc:
            # Every other path reports AMW-ERR and exits 2; this one used to
            # raise a traceback at a mistyped directory.
            print("AMW-ERR: %s" % exc, file=sys.stderr)
            return 2
        findings = check_sweep(plan, outcomes)
        # The summary is rewritten too. Refreshing only the report left the two
        # artifacts in one directory disagreeing with each other, and the CSV
        # is the one most likely to be read by something other than a human.
        write_summary(sweep_dir, plan, outcomes)
        text = report_text(plan, outcomes, findings)
        (sweep_dir / REPORT_NAME).write_text(
            text, encoding="ascii", errors="backslashreplace")
        print(text, end="")
        return verdict_exit_code(findings)

    try:
        plan = plan_sweep(
            parent=Path(args.parent), lever=args.lever, target=args.target,
            mode=args.mode, kmin=args.kmin, kmax=args.kmax, kstep=args.kstep,
            sweep_id=args.sweep_id, slug_prefix=args.slug_prefix,
            decimals=args.decimals,
        )
    except (Ercot7kSweepError, ec.Ercot7kCaseError) as exc:
        print("AMW-ERR: %s" % exc, file=sys.stderr)
        return 2

    sweeps_root, derived_root, runs_root = _roots(args)
    projected = projection(plan, _nearest_existing(runs_root))
    _print_plan(plan, projected)

    if args.command == "plan":
        print("Nothing was built or solved. Re-run with 'run' to start.")
        return 0

    if not projected["fits"] and not args.skip_disk_check:
        if not projected["measured"]:
            print("AMW-ERR: free space at %s could not be measured, so the "
                  "~%.1f GB this sweep projects cannot be checked against it. "
                  "An unmeasurable disk is not a pass; pass "
                  "--skip-disk-check to go ahead anyway."
                  % (runs_root, projected["results_mb"] / 1024.0),
                  file=sys.stderr)
        else:
            print("AMW-ERR: this sweep projects ~%.1f GB against %.1f GB "
                  "free, leaving less than the %.1f GB margin. Free space, "
                  "use --prune, shorten the sweep, or pass --skip-disk-check."
                  % (projected["results_mb"] / 1024.0,
                     projected["free_mb"] / 1024.0, DISK_MARGIN_MB / 1024.0),
                  file=sys.stderr)
        return 2

    try:
        outcomes = run_sweep(
            plan, sweeps_root=sweeps_root, derived_root=derived_root,
            runs_root=runs_root, resume=args.resume, prune=args.prune,
            stop_on_error=not args.keep_going,
            echo=lambda text: print(text, flush=True),
        )
    except (Ercot7kSweepError, ec.Ercot7kCaseError) as exc:
        # A refusal to START is not a failed sweep, and must not share exit 1
        # with one: nothing has been built or solved here. Everything after
        # plan_sweep used to be outside this guard, so the refusals added for
        # the resume identity holes surfaced as tracebacks.
        print("AMW-ERR: %s" % exc, file=sys.stderr)
        return 2

    sweep_dir = sweeps_root / plan.sweep_id
    summary = write_summary(sweep_dir, plan, outcomes)
    findings = check_sweep(plan, outcomes)
    text = report_text(plan, outcomes, findings)
    (sweep_dir / REPORT_NAME).write_text(
        text, encoding="ascii", errors="backslashreplace")
    print(text, end="")
    print("summary     : %s" % summary)
    print("report      : %s" % (sweep_dir / REPORT_NAME))
    return verdict_exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())

# ------------------------------------------------------------------------------
# END OF ercot7k_sweep.py
# ------------------------------------------------------------------------------
