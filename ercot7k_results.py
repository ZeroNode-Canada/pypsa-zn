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

# ercot7k_results.py
#
# Purpose
#   Read a solved PSO run's result CSVs back into the artifact shapes this repo
#   already produces (lib/devnet_stress_lib.py: collect_results +
#   write_outputs), so the existing dashboards, index.html scraper and plot
#   scripts consume a 7000-bus PSO run unchanged. Nothing about an ERCOT
#   Texas7k study is visible until this exists.
#
#   Strictly read-only. This module opens no case file for writing and touches
#   no results file at all, so it cannot corrupt a case or a run.
#
#   Importable-only, for the same reason ercot7k_case.py is: no prints, no
#   prompts, no directory creation, no logging setup and no sys.stdout
#   replacement at import time. The argparse entry at the bottom runs only
#   under __main__.
#
# What it does
#   - Streams the large result tables with the csv module, filtering on the
#     pinned reporting triple (cyc, scn, int) as it goes. results_PC_Nd.csv is
#     287 MB / 3.4M rows in the shipped case; it is never handed to pandas.
#   - Pins the reported interval ONCE, as the peak-CONGESTION interval of the
#     reported cycle, and persists it in a small study.json. map_results()
#     takes the interval as an argument and never guesses: a k_load change
#     moves the peak hour, and comparing hour 88 against hour 91 moves LMP
#     spread for reasons that have nothing to do with the lever. See
#     pin_interval() for why the rule is congestion and not load -- at the
#     peak-load hour of the shipped case nothing binds at all.
#   - Reads the study context (the datacenter injector names) from the case's
#     pso_case_manifest.json, never by string-matching an injector prefix.
#   - Derives the asymptote metric: the DC load injector's own LimitViolation
#     and Penalty next to the system's, per interval, so a run can say whether
#     the grid or the datacenter gave way first.
#
# Outputs (under <outdir>, all named <tag>_*)
#   - <tag>_lmp.csv                    node -> LMP at the reported interval
#   - <tag>_line_loading_pu.csv        path -> abs(Mw)/Max
#   - <tag>_generator_dispatch_mw.csv  injector -> P
#   - <tag>_bus_net_import_mw.csv      node -> load - generation
#   - <tag>_objective.csv              objective + total_system_load_mw
#   - <tag>.json                       collect_results keys + status + triple
#   - <tag>_binding.csv                binding paths at the reported interval
#   - <tag>_deliverability.csv         per interval, the asymptote metric
#   - <tag>_chronology.csv             per interval, the whole reported cycle
#
# Run: python ercot7k_results.py pin <results_dir>
#      python ercot7k_results.py map <results_dir> <outdir> <tag> --interval N
# ------------------------------------------------------------------------------

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from array import array
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import ercot7k_case as ec

# Global defines
SECTION_SEPARATOR = "="*80 + "\n"  # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n"  # for print separation

READER_ID = "ercot7k_results.py/1"

# The reported triple defaults. RT is the cycle a study reports on; SC and DA
# are the commitment cycles feeding it.
DEFAULT_CYCLE = "RT"
DEFAULT_SCENARIO = "ScnRT"

# PC_Nd reports synthetic reference nodes alongside the electrical ones. They
# carry an LMP but are not buses, so they are dropped from every nodal artifact.
REFERENCE_NODE_PREFIX = "Reference_"

RESULT_FILE_TEMPLATE = "results_%s.csv"

# The study pin, written next to a derived case. Small on purpose: it exists so
# that two runs of a sweep report the same hour.
STUDY_NAME = "study.json"
STUDY_SCHEMA = "ercot7k-study/1"

# Matches lib/devnet_stress_lib.py's near-binding threshold exactly, because
# update_index_html scrapes the count under that name.
NEAR_BIND_THRESHOLD = 0.95

# Every per-entity dashboard listing is capped here. Uncapped, a 6717-bus
# listing is a 7000-line <pre> block inside index.html.
DASHBOARD_TOP_N = 10

# The percentiles carried by the chronology and by the dashboard lmp_spread.
LMP_PERCENTILES = (0.0, 5.0, 50.0, 95.0, 100.0)

# Output datetime format. Deliberately ISO-ish and NOT the AIMMS "%Y.%m.%d"
# input format: these strings are read by humans and by pandas, not by PSO.
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


# ------------------------------------------------------------------------------
#   Errors
# ------------------------------------------------------------------------------
class Ercot7kResultsError(Exception):
    """A results directory could not be read as the run it claims to be."""


# ------------------------------------------------------------------------------
#   Reader mechanics
# ------------------------------------------------------------------------------
# PSO comment-prefixes the FIRST header cell only: "//cyc", "//slv", "//ste".
# The prefixed name is never assumed -- the "//" is stripped from whatever cell
# zero happens to be, so a table whose first index is renamed still reads.
#
# Every large table is read with csv.reader by column INDEX, not DictReader by
# name: PC_Nd is 3.4M rows and building a dict per row triples the runtime for
# nothing. Small tables (ED_Ara, MC_Hrzn, MC_Solution, PF_AraNde) go through
# read_result_records() because clarity is worth more there than speed.
# ------------------------------------------------------------------------------
def result_path(results_dir: Path, table: str) -> Path:
    return Path(results_dir) / (RESULT_FILE_TEMPLATE % table)


def _decomment(header_cell: str) -> str:
    """Strips PSO's leading comment marker from a header cell."""
    return header_cell.lstrip("/")


def _normalize_header(cells: Sequence[str]) -> List[str]:
    if not cells:
        raise Ercot7kResultsError("result table has an empty header line")
    return [_decomment(cells[0])] + [cell for cell in cells[1:]]


def require_result(results_dir: Path, table: str) -> Path:
    path = result_path(results_dir, table)
    if not path.is_file():
        raise Ercot7kResultsError(
            "%s is missing. A complete PSO run writes it; an absent "
            "results_MC_Solution.csv in particular means the run validated "
            "rather than solved." % path
        )
    return path


@contextmanager
def result_reader(path: Path) -> Iterator[Tuple[List[str], Iterator[List[str]]]]:
    """Yields (columns, row iterator) for one result CSV, streaming."""
    with open(path, "r", newline="", encoding="ascii", errors="strict") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise Ercot7kResultsError("%s is empty" % path)
        yield _normalize_header(header), reader


def result_columns(path: Path) -> List[str]:
    with result_reader(path) as (columns, _rows):
        return columns


def read_result_records(path: Path) -> List[Dict[str, str]]:
    """Whole-file read, for the small tables only."""
    with result_reader(path) as (columns, rows):
        width = len(columns)
        out: List[Dict[str, str]] = []
        for number, row in enumerate(rows, start=2):
            if len(row) != width:
                raise Ercot7kResultsError(
                    "%s line %d has %d fields, header has %d"
                    % (path, number, len(row), width)
                )
            out.append(dict(zip(columns, row)))
        return out


def column_index(columns: Sequence[str], name: str, path: Path) -> int:
    try:
        return list(columns).index(name)
    except ValueError:
        raise Ercot7kResultsError(
            "%s has no column %r; header is %s"
            % (path, name, ",".join(columns))
        )


def column_indexes(columns: Sequence[str], names: Sequence[str],
                   path: Path) -> List[int]:
    return [column_index(columns, name, path) for name in names]


# ------------------------------------------------------------------------------
# _num() / _flag()
#
# A blank PSO result field is "not reported", not zero -- ED_Ara.Violation and
# ED_Inj.LimitViolation are documented sparse fields. Blank therefore becomes
# NaN and propagates as NaN, never as a silent 0.0 that would read as "no
# violation" when the truth is "no answer".
# ------------------------------------------------------------------------------
def _num(text: str) -> float:
    text = text.strip()
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def _flag(text: str) -> bool:
    return text.strip() not in ("", "0")


def _finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


# ------------------------------------------------------------------------------
#   The reported triple
# ------------------------------------------------------------------------------
@dataclass(frozen=True)
class ReportKey:
    """I = (cyc, scn, int). Every artifact in this module is filtered on it."""
    cycle: str
    scenario: str
    interval: int

    def matches(self, cycle: str, scenario: str) -> bool:
        return cycle == self.cycle and scenario == self.scenario

    def as_dict(self) -> Dict[str, Any]:
        return {"cycle": self.cycle, "scenario": self.scenario,
                "interval": int(self.interval)}


# ------------------------------------------------------------------------------
# scenario_for_cycle()
#
# CYC_SCN pairs one named scenario with each cycle, and the results echo that
# pairing. Resolving it from the run rather than defaulting to "ScnRT" means a
# renamed scenario does not silently filter every artifact down to nothing.
# ------------------------------------------------------------------------------
def scenario_for_cycle(results_dir: Path, cycle: str) -> str:
    path = require_result(results_dir, "ED_Ara")
    found: List[str] = []
    for record in read_result_records(path):
        if record["cyc"] == cycle and record["scn"] not in found:
            found.append(record["scn"])
    if not found:
        raise Ercot7kResultsError(
            "%s reports no rows for cycle %r; cycles present are %s"
            % (path, cycle, ", ".join(sorted(
                {r["cyc"] for r in read_result_records(path)})))
        )
    if len(found) > 1:
        raise Ercot7kResultsError(
            "cycle %r reports %d scenarios (%s); pass one explicitly"
            % (cycle, len(found), ", ".join(found))
        )
    return found[0]


# ------------------------------------------------------------------------------
# area_load_by_interval()
#
# ED_Ara.Load is "(MW) fixed area load" and is documented as NOT affected by
# Violation: it does not change with load shedding. It is an INPUT ECHO, not a
# served-load metric. It is used here for two things only -- pinning the peak
# interval, and reporting total_system_load_mw -- and both want the input echo.
#
# A LoadFlag=1 injector (which is what a datacenter is) never appears in it, so
# adding a datacenter does not move this number. That is why deliverability is
# measured on ED_Inj and not here.
# ------------------------------------------------------------------------------
def area_load_by_interval(results_dir: Path, cycle: str,
                          scenario: str) -> Dict[int, float]:
    path = require_result(results_dir, "ED_Ara")
    totals: Dict[int, float] = {}
    for record in read_result_records(path):
        if record["cyc"] != cycle or record["scn"] != scenario:
            continue
        interval = int(record["int"])
        value = _num(record["Load"])
        totals[interval] = totals.get(interval, 0.0) + (
            value if _finite(value) else 0.0
        )
    if not totals:
        raise Ercot7kResultsError(
            "%s reports no rows for (%s, %s)" % (path, cycle, scenario)
        )
    return totals


# ------------------------------------------------------------------------------
# area_metrics_by_interval()
#
# ED_Ara.Violation / Penalty per interval: the SYSTEM half of the asymptote.
# ------------------------------------------------------------------------------
def area_metrics_by_interval(results_dir: Path, cycle: str,
                             scenario: str) -> Dict[int, Dict[str, float]]:
    path = require_result(results_dir, "ED_Ara")
    out: Dict[int, Dict[str, float]] = {}
    for record in read_result_records(path):
        if record["cyc"] != cycle or record["scn"] != scenario:
            continue
        interval = int(record["int"])
        slot = out.setdefault(
            interval, {"load_mw": 0.0, "violation_mw": 0.0, "penalty_usd": 0.0}
        )
        for key, column in (("load_mw", "Load"),
                            ("violation_mw", "Violation"),
                            ("penalty_usd", "Penalty")):
            value = _num(record[column])
            if _finite(value):
                slot[key] += value
    return out


# ------------------------------------------------------------------------------
# path_limit_by_interval()
#
# PN_Pth.Max for ONE named path, per interval, WITH the bit that says whether
# that limit was actually in the solution.
#
# Max is an INPUT ECHO of BRN_ID.NormalLimit as any SCN_BRN_LMT row amended it,
# which is what makes it the readback a k_line sweep is checked against: a
# response variable moving proves the model did something, but only an input
# echo proves it did what was asked.
#
# WARNING: Max on its own is NOT evidence that the limit reached the LP, and an
# earlier version of this docstring said it was. PN_Pth.md is explicit: Max is
# "(MW) maximum flow limit", while "MinEnforced and MaxEnforced identifies
# constraints enforced in solution" -- a separate bit. The report covers "all
# enforced paths AND any monitored paths identified for enforcement by security
# analysis", and option "ReportAllSolvedPaths" reports every monitored path
# "even if not identified by security analysis for enforcement".
#
# This is not hypothetical. In the committed reference run, which does report
# all 1,171 monitored paths per cycle, the ordinary row is exactly
# Max=1371.200, MaxEnforced=0, Binding=0, SolverMw=0 -- the limit echoed back
# from the file, having played no part in dispatch. This whole case is that
# shape: Enforce=0 on all 9,140 branches, so every limit that binds does so
# only because CYC_SAI discovery found it.
#
# So `enforced` travels with max_mw, and the caller is expected to require it.
# Without it a k_line sweep degrades into a round trip of the CSV it just
# wrote: every step "agrees" to the digit while the derate changed nothing.
#
# `enforced` is MinEnforced OR MaxEnforced, and reading only the Max side
# would be wrong. BRN_ID.NormalLimit is a "(MW) Normal BI-DIRECTIONAL limit",
# so a derate moves Min and Max together (-NormalLimit and +NormalLimit) and
# which side is enforced depends on the direction of flow. MEASURED on the
# committed reference run for the study's own corridor
# N210144_N210332_1 (HEWITT <- RIESEL), across all 168 RT intervals:
# MinEnforced=1 168 times, MaxEnforced=1 zero times, flow -1328.300 against
# Min -1328.300, Binding=1, SP 30.459. Reading MaxEnforced alone would call
# the case's most persistent constraint unenforced.
# (Consistency check while there: of 196,728 RT rows, zero are Binding with
# neither side enforced -- so PN_Pth.md's "a path can be binding only when
# enforced" holds, once both sides are read.)
#
# `enforced` is NaN, not 0, where the columns are absent: "this results set
# cannot answer" and "the limit was not enforced" are different findings and
# the second must not be manufactured from the first.
#
# A path that is not reported is ABSENT from the mapping, never 0.0 -- a 0.0
# would read as "limit of zero", which BRN_ID.md gives a specific and opposite
# meaning ("if NormalLimit = 0, limits are ignored").
# ------------------------------------------------------------------------------
def path_limit_by_interval(results_dir: Path, cycle: str, scenario: str,
                           path_name: str) -> Dict[int, Dict[str, float]]:
    path = require_result(results_dir, "PN_Pth")
    columns_present = result_columns(path)
    out: Dict[int, Dict[str, float]] = {}
    with result_reader(path) as (columns, rows):
        i_cyc, i_scn, i_pth, i_int, i_max = column_indexes(
            columns, ("cyc", "scn", "pth", "int", "Max"), path
        )
        i_min_enf = (column_index(columns, "MinEnforced", path)
                     if "MinEnforced" in columns_present else -1)
        i_max_enf = (column_index(columns, "MaxEnforced", path)
                     if "MaxEnforced" in columns_present else -1)
        i_bind = (column_index(columns, "Binding", path)
                  if "Binding" in columns_present else -1)
        for row in rows:
            if row[i_cyc] != cycle or row[i_scn] != scenario:
                continue
            if row[i_pth] != path_name:
                continue
            # Both columns absent -> unknown. Both present -> the OR. Exactly
            # ONE present and false is still UNKNOWN, not false: the missing
            # side could have been the enforced one, and this function's own
            # rule is that "cannot answer" must never become "was not
            # enforced". Only a true reading is conclusive on its own.
            sides = [_flag(row[i]) for i in (i_min_enf, i_max_enf) if i >= 0]
            if any(sides):
                enforced = 1.0
            elif len(sides) == 2:
                enforced = 0.0
            else:
                enforced = math.nan
            out[int(row[i_int])] = {
                "max_mw": _num(row[i_max]),
                "enforced": enforced,
                "binding": (1.0 if _flag(row[i_bind]) else 0.0)
                           if i_bind >= 0 else math.nan,
            }
    return out


# ------------------------------------------------------------------------------
# injector_limit_by_interval()
#
# The k_gen derate witness: ED_Inj.Max for ONE injector, per interval.
#
# ED_Inj.md defines Max as the dispatch limit and says it is "de-rated by
# fixed-dispatch (SCN_INJ_DSP) or dispatch limits (SCN_INJ_MAX)" -- so on a
# capped unit it is the cap read back out of the solution, an input echo in the
# input's own units. That is what makes it usable the way PN_Pth.Max is for
# k_line, and unlike PN_Pth there is no reporting-scope question: ED_Inj carries
# every injector in every interval of every cycle.
#
# Two things ride along, and neither is decoration:
#
#   Cap ("installed seasonal capacity") is NOT derated by SCN_INJ_MAX. It is the
#   only way to tell a capped unit from an unavailable one, because the same
#   sentence in ED_Inj.md says Max is "set to zero when off due to scheduled
#   outage, forced outage, failed startup, or unavailable for commitment". A
#   unit the solve left uncommitted therefore reports Max=0 at that interval
#   whatever cap the case asked for -- 33,675 of the validated run's 106,848 RT
#   rows are exactly that -- and reading it as the witness would say the lever
#   derated the unit to nothing.
#
#   LimitViolation is the enforcement half. PSO's injector dispatch limits are
#   soft slacks rather than hard constraints, so "the cap was reported" and "the
#   cap was respected" are separable here in the same way MaxEnforced separates
#   them for a branch: dispatch above the cap appears as a positive
#   LimitViolation rather than as an infeasibility.
#
# An injector absent from the results is ABSENT from the mapping, never 0.0.
# ------------------------------------------------------------------------------
def injector_limit_by_interval(results_dir: Path, cycle: str, scenario: str,
                               injector: str) -> Dict[int, Dict[str, float]]:
    path = require_result(results_dir, "ED_Inj")
    columns_present = result_columns(path)
    out: Dict[int, Dict[str, float]] = {}
    with result_reader(path) as (columns, rows):
        i_cyc, i_scn, i_inj, i_int, i_max, i_p = column_indexes(
            columns, ("cyc", "scn", "inj", "int", "Max", "P"), path
        )
        # Cap and LimitViolation are read where present and reported as NaN
        # where not. "This results set cannot answer" and "the cap was
        # respected" are different findings, and the second must not be
        # manufactured from the first.
        i_cap = (column_index(columns, "Cap", path)
                 if "Cap" in columns_present else -1)
        i_limvio = (column_index(columns, "LimitViolation", path)
                    if "LimitViolation" in columns_present else -1)
        for row in rows:
            if row[i_cyc] != cycle or row[i_scn] != scenario:
                continue
            if row[i_inj] != injector:
                continue
            out[int(row[i_int])] = {
                "max_mw": _num(row[i_max]),
                "cap_mw": _num(row[i_cap]) if i_cap >= 0 else math.nan,
                "p_mw": _num(row[i_p]),
                "limit_violation_mw": (_num(row[i_limvio]) if i_limvio >= 0
                                       else math.nan),
            }
    return out


# ------------------------------------------------------------------------------
# pin_interval()
#
# The reported interval must be pinned by the study, not recomputed per run.
# This is the ONE place that chooses it, and the rule is peak CONGESTION:
# the interval of the reported cycle with the most binding paths.
#
# It used to be the peak ED_Ara.Load interval, which reads well and measures
# nothing. MEASURED on the validated run: at the RT peak-load interval (184,
# 46,794.5 MW) the network is completely uncongested -- all 6,717 nodes price at
# 53.710, lmp_spread is 0.000 and not one path binds. Pinned there, the headline
# metric starts at zero and a stress lever has to manufacture congestion out of
# nothing before it moves at all. Under this rule RT pins 103 instead:
# 5 binding paths, lmp_spread 7.45, max_loading 1.000. The metric is live.
#
# Ties are broken on lmp_spread (P95 - P05) and then on the lowest interval, so
# the answer is deterministic. The tie-break is not decorative: RT's top binding
# count of 5 is shared by intervals 101, 102 and 103.
#
# Binding is a PSO flag rather than a derived quantity, which is deliberate --
# it keeps the rule independent of the still-open question of whether
# lmp_spread is P95-P05 or max-min. Note the two do not agree on the worst
# hour: interval 236 carries the largest spread (12.67) on only 4 binding
# paths, so it is NOT the pin.
#
# PN_Pth alone answers this in one pass. The 287 MB PC_Nd scan happens only to
# break an actual tie.
# ------------------------------------------------------------------------------
def pin_interval(results_dir: Path, cycle: str = DEFAULT_CYCLE,
                 scenario: Optional[str] = None) -> int:
    if scenario is None:
        scenario = scenario_for_cycle(results_dir, cycle)

    # A ReportKey needs an interval before either scan can be called, and the
    # scans use it only for a single-interval slice that is discarded here.
    intervals = sorted(area_load_by_interval(results_dir, cycle, scenario))
    probe = ReportKey(cycle=cycle, scenario=scenario, interval=intervals[0])

    n_binding = scan_paths(results_dir, probe).n_binding
    most = max(n_binding.values()) if n_binding else 0
    if most == 0:
        raise Ercot7kResultsError(
            "no path binds in any of the %d intervals of cycle %s, so there is "
            "no peak-congestion interval to pin. An uncongested case has no "
            "hour where lmp_spread can move; pin it by hand with "
            "write_study() if that is genuinely what is being studied."
            % (len(n_binding), cycle)
        )

    tied = sorted(interval for interval, n in n_binding.items() if n == most)
    if len(tied) == 1:
        return tied[0]

    percentiles = scan_nodes(results_dir, probe).percentiles

    def spread(interval: int) -> float:
        value = percentiles.get(interval, {}).get("spread_p95_p05", math.nan)
        return value if _finite(value) else -math.inf

    widest = max(spread(interval) for interval in tied)
    return min(interval for interval in tied if spread(interval) == widest)


# ------------------------------------------------------------------------------
#   study.json -- where the pin lives
# ------------------------------------------------------------------------------
def study_path(case_dir: Path) -> Path:
    return Path(case_dir) / STUDY_NAME


def has_study(case_dir: Path) -> bool:
    return study_path(case_dir).is_file()


def read_study(case_dir: Path) -> Dict[str, Any]:
    path = study_path(case_dir)
    if not path.is_file():
        raise Ercot7kResultsError("%s has no %s" % (case_dir, STUDY_NAME))
    with open(path, "r", encoding="ascii") as handle:
        study = json.load(handle)
    schema = study.get("schema")
    if schema != STUDY_SCHEMA:
        raise Ercot7kResultsError(
            "%s has schema %r, expected %r" % (path, schema, STUDY_SCHEMA)
        )
    return study


def write_study(case_dir: Path, key: ReportKey,
                results_dir: Optional[Path] = None,
                force: bool = False) -> Path:
    """Persists the pinned triple. Refuses to move a pin unless asked twice."""
    path = study_path(case_dir)
    if path.exists() and not force:
        raise Ercot7kResultsError(
            "%s already pins interval %d. Re-pinning is what makes two runs "
            "of a sweep compare different hours; pass force=True only if you "
            "mean to invalidate every artifact already derived under the old "
            "pin." % (path, read_study(case_dir)["report"]["interval"])
        )
    study = {
        "schema": STUDY_SCHEMA,
        "writer": READER_ID,
        "report": key.as_dict(),
        "pinned_from": str(results_dir) if results_dir is not None else None,
        "pin_rule": ("peak-congestion interval of the reported cycle: most "
                     "binding PN_Pth paths, ties broken on lmp_spread "
                     "(P95 - P05) then the lowest interval"),
    }
    text = json.dumps(study, indent=2, sort_keys=False, ensure_ascii=True)
    path.write_bytes((text + "\n").encode("ascii"))
    return path


def pinned_report_key(case_dir: Path) -> ReportKey:
    report = read_study(case_dir)["report"]
    return ReportKey(cycle=report["cycle"], scenario=report["scenario"],
                     interval=int(report["interval"]))


# ------------------------------------------------------------------------------
#   Solver status and the objective
# ------------------------------------------------------------------------------
# MC_Solution.Objective is NOT the run's objective at 7k. The shipped case
# reports 190 rows -- one per solve, per loop, per iteration -- so iloc[0] is
# the first SC iteration and nothing more. Summing them double-counts, because
# SC and DA horizons OVERLAP: DA's horizon is 48 h with a DeltaTime of 24, so
# the second day of every DA horizon is re-solved by the next one.
#
# MC_Hrzn.DeltaCost is documented as "Real cost from periods in DeltaTime of
# horizon", i.e. exactly the non-overlapping slice, and is what this module
# sums. Verified against the shipped run: RT 12,008,467 / DA 20,297,189 /
# SC 11,727,677. MC_Hrzn.AllCost for DA is 31,244,658, which is the
# double-counted number the naive read produces.
# ------------------------------------------------------------------------------
@dataclass
class SolutionStatus:
    solves: int
    counts: Dict[str, int]
    status: str


def solution_status(results_dir: Path) -> SolutionStatus:
    path = require_result(results_dir, "MC_Solution")
    counts: Dict[str, int] = {}
    for record in read_result_records(path):
        value = record.get("Status", "").strip() or "(blank)"
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        raise Ercot7kResultsError("%s reports no solves" % path)
    if len(counts) == 1:
        status = next(iter(counts))
    else:
        status = "MIXED:" + ",".join(
            "%s=%d" % (name, counts[name]) for name in sorted(counts)
        )
    return SolutionStatus(solves=sum(counts.values()), counts=counts,
                          status=status)


def objective_by_cycle(results_dir: Path) -> Dict[str, float]:
    """Sum of MC_Hrzn.DeltaCost per cycle -- the non-overlapping real cost."""
    path = require_result(results_dir, "MC_Hrzn")
    out: Dict[str, float] = {}
    for record in read_result_records(path):
        value = _num(record["DeltaCost"])
        if not _finite(value):
            continue
        out[record["cyc"]] = out.get(record["cyc"], 0.0) + value
    return out


def objective_by_interval(results_dir: Path, cycle: str,
                          scenario: str) -> Dict[int, float]:
    """
    MC_Hrzn.DeltaCost keyed by the horizon's FirstInterval.

    RT has DeltaTime = 1 in this case, so every interval of the reported cycle
    carries its own cost. SC and DA have DeltaTime = 24, so only every 24th
    interval does; the chronology leaves the rest blank rather than smearing
    a horizon cost across the hours inside it.
    """
    path = require_result(results_dir, "MC_Hrzn")
    out: Dict[int, float] = {}
    for record in read_result_records(path):
        if record["cyc"] != cycle or record["scn"] != scenario:
            continue
        interval = int(record["FirstInterval"])
        value = _num(record["DeltaCost"])
        if _finite(value):
            out[interval] = out.get(interval, 0.0) + value
    return out


# ------------------------------------------------------------------------------
#   Area-to-node load distribution
# ------------------------------------------------------------------------------
# There is NO per-node load MW anywhere in a PSO results directory. ED_Ara
# carries area load; ED_Inj carries injector dispatch; nothing carries the
# distributed load that a bus_net_import artifact needs. So the area load must
# be redistributed through PF_AraNde.LoadFactor, which is documented as a
# normalized distribution factor summing to 1 over the area's nodes.
#
# MEASURED, and it matters: in the shipped run the LoadFactor column sums to
# 1.13204781, not 1.0. The report quantizes the field (values >= 0.001 print as
# "%.3f", smaller ones as "%.3e"), so a node whose true share is 0.0015 prints
# as 0.002 -- a 33% error on that row, and a 13% error on the total. Using the
# column raw would inflate distributed load by 13% and make sum(load_at_node)
# disagree with ED_Ara.Load, the one number that is exact.
#
# This module therefore RENORMALIZES each area's factors by their own sum. That
# makes the distributed total exact by construction and leaves the quantization
# only in the per-node split, which is where it is unavoidable. The raw sum is
# kept and reported so the quantization stays visible rather than being
# silently absorbed.
# ------------------------------------------------------------------------------
@dataclass
class LoadDistribution:
    raw: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def areas(self) -> List[str]:
        return list(self.raw)

    def raw_sum(self, area: str) -> float:
        return sum(self.raw.get(area, {}).values())

    def normalized(self, area: str) -> Dict[str, float]:
        factors = self.raw.get(area, {})
        total = sum(factors.values())
        if total <= 0.0:
            raise Ercot7kResultsError(
                "PF_AraNde load factors for area %r sum to %r, so area load "
                "cannot be distributed" % (area, total)
            )
        return {node: value / total for node, value in factors.items()}

    def nodes(self) -> List[str]:
        seen: List[str] = []
        for factors in self.raw.values():
            for node in factors:
                if node not in seen:
                    seen.append(node)
        return seen


def load_distribution(results_dir: Path) -> LoadDistribution:
    path = require_result(results_dir, "PF_AraNde")
    out: Dict[str, Dict[str, float]] = {}
    for record in read_result_records(path):
        value = _num(record["LoadFactor"])
        if not _finite(value) or value == 0.0:
            continue
        # ste is summed over: a node mapped through more than one state still
        # contributes its whole share of the area's load.
        area = out.setdefault(record["ara"], {})
        area[record["nde"]] = area.get(record["nde"], 0.0) + value
    if not out:
        raise Ercot7kResultsError("%s reports no load factors" % path)
    return LoadDistribution(raw=out)


# ------------------------------------------------------------------------------
#   The case side: injector -> node, the DC injectors, and the clock
# ------------------------------------------------------------------------------
# INJ_NET.Node is read through ercot7k_case.read_table so that exactly one
# byte-fidelity CSV reader exists in this repo. A blank Node means the injector
# is placed by area distribution (STE_NDE) rather than at a named bus, and such
# an injector cannot be attributed to a node; it is counted, not dropped
# silently.
# ------------------------------------------------------------------------------
def injector_node_map(case_dir: Path) -> Dict[str, str]:
    case_dir = Path(case_dir)
    prefix = ec.case_prefix(case_dir)
    path = case_dir / ("%s_INJ_NET.csv" % prefix)
    if not path.is_file():
        raise Ercot7kResultsError("%s is missing" % path)
    table = ec.read_table(path)
    out: Dict[str, str] = {}
    for record in table.records():
        node = (record.get("Node") or "").strip()
        if node:
            out[record["Injector"]] = node
    return out


# ------------------------------------------------------------------------------
# datacenters_from_manifest()
#
# The DC injector names come from the manifest's study section, never from a
# prefix match on the injector name. A prefix match is exactly the silent
# failure this study cannot afford: it would find the wrong injector, or none,
# and report a clean zero violation either way.
#
# No manifest is not an error. A base run has no datacenter, so the system
# columns are emitted and the DC columns are simply absent.
# ------------------------------------------------------------------------------
def datacenters_from_manifest(case_dir: Optional[Path]) -> List[Dict[str, str]]:
    if case_dir is None or not ec.has_manifest(Path(case_dir)):
        return []
    manifest = ec.read_manifest(Path(case_dir))
    study = manifest.get("study") or {}
    out: List[Dict[str, str]] = []
    for entry in study.get("datacenters") or []:
        out.append({
            "dc_name": str(entry.get("dc_name", "")),
            "node": str(entry.get("node", "")),
            "load_injector": str(entry.get("load_injector", "")),
            "byog_injector": str(entry.get("byog_injector", "")),
        })
    return out


# ------------------------------------------------------------------------------
# IntervalClock
#
# Interval 1 is MDL_ID.MinDate, not StartDate: PSO numbers intervals from the
# start of the valid time window, and the reported window begins at StartDate.
# In the shipped case MinDate is 2018.04.06 00:00 and StartDate is
# 2018.04.09 00:00, exactly 72 hours later, and the first reported interval is
# 73 -- which is the arithmetic confirming the convention.
# ------------------------------------------------------------------------------
@dataclass(frozen=True)
class IntervalClock:
    start: datetime
    step: timedelta

    def at(self, interval: int) -> datetime:
        return self.start + (int(interval) - 1) * self.step

    def text(self, interval: int) -> str:
        return self.at(interval).strftime(DATETIME_FORMAT)


def interval_clock(case_dir: Optional[Path]) -> Optional[IntervalClock]:
    """The clock from a case directory's MDL_ID, or None if there is no case."""
    if case_dir is None:
        return None
    case_dir = Path(case_dir)
    prefix = ec.case_prefix(case_dir)
    tables: Dict[str, ec.Table] = {}
    for name in ("MDL_ID", ec.CONTROL_TABLE):
        filename = ("%s.csv" % prefix if name == ec.CONTROL_TABLE
                    else "%s_%s.csv" % (prefix, name))
        path = case_dir / filename
        if path.is_file():
            tables[name] = ec.read_table(path, name=name)
    if "MDL_ID" not in tables:
        return None
    mdl = ec.model_id(tables)
    fmt = ec.aimms_date_format(tables)
    return IntervalClock(start=datetime.strptime(mdl["MinDate"], fmt),
                         step=ec.interval_delta(mdl))


# ------------------------------------------------------------------------------
#   Study context
# ------------------------------------------------------------------------------
@dataclass
class StudyContext:
    results_dir: Path
    case_dir: Optional[Path]
    key: ReportKey
    datacenters: List[Dict[str, str]] = field(default_factory=list)
    injector_node: Dict[str, str] = field(default_factory=dict)
    clock: Optional[IntervalClock] = None

    @property
    def has_datacenter(self) -> bool:
        return bool(self.datacenters)

    def dc_load_injectors(self) -> List[str]:
        return [d["load_injector"] for d in self.datacenters
                if d.get("load_injector")]

    def dc_byog_injectors(self) -> List[str]:
        return [d["byog_injector"] for d in self.datacenters
                if d.get("byog_injector")]

    def datetime_text(self, interval: Optional[int] = None) -> str:
        if self.clock is None:
            return ""
        return self.clock.text(self.key.interval if interval is None
                               else interval)


def study_context(results_dir: Path, key: ReportKey,
                  case_dir: Optional[Path] = None) -> StudyContext:
    case_dir = Path(case_dir) if case_dir is not None else None
    return StudyContext(
        results_dir=Path(results_dir),
        case_dir=case_dir,
        key=key,
        datacenters=datacenters_from_manifest(case_dir),
        injector_node=(injector_node_map(case_dir)
                       if case_dir is not None else {}),
        clock=interval_clock(case_dir),
    )


# ------------------------------------------------------------------------------
#   Streaming scans of the large tables
# ------------------------------------------------------------------------------
# One pass per file. Each scan collects BOTH the reported interval's slice and
# the per-interval aggregates the chronology needs, because re-reading a 287 MB
# file 168 times is not a shape, it is a wait.
# ------------------------------------------------------------------------------
@dataclass
class NodeScan:
    lmp: Dict[str, float] = field(default_factory=dict)
    percentiles: Dict[int, Dict[str, float]] = field(default_factory=dict)
    reference_nodes: List[str] = field(default_factory=list)


def scan_nodes(results_dir: Path, key: ReportKey) -> NodeScan:
    """
    PC_Nd in one pass: the reported interval's LMP by node, plus the LMP
    distribution of every interval of the reported cycle.

    Node order is file order, so the artifact index is stable across runs of
    the same case.
    """
    path = require_result(results_dir, "PC_Nd")
    scan = NodeScan()
    samples: Dict[int, array] = {}
    with result_reader(path) as (columns, rows):
        i_cyc, i_scn, i_nd, i_int, i_lmp = column_indexes(
            columns, ("cyc", "scn", "nd", "int", "LMP"), path
        )
        for row in rows:
            if row[i_cyc] != key.cycle or row[i_scn] != key.scenario:
                continue
            node = row[i_nd]
            if node.startswith(REFERENCE_NODE_PREFIX):
                if node not in scan.reference_nodes:
                    scan.reference_nodes.append(node)
                continue
            interval = int(row[i_int])
            value = _num(row[i_lmp])
            bucket = samples.get(interval)
            if bucket is None:
                bucket = samples[interval] = array("d")
            bucket.append(value)
            if interval == key.interval:
                scan.lmp[node] = value
    if not scan.lmp:
        raise Ercot7kResultsError(
            "%s reports no nodes for cycle=%s scenario=%s interval=%d"
            % (path, key.cycle, key.scenario, key.interval)
        )
    for interval in sorted(samples):
        scan.percentiles[interval] = _percentiles(samples[interval])
    return scan


def _percentiles(values: array) -> Dict[str, float]:
    data = np.frombuffer(values, dtype=np.float64)
    if data.size == 0 or not np.isfinite(data).any():
        blank = {name: math.nan for name in
                 ("min", "p05", "p50", "p95", "max")}
        blank["spread_p95_p05"] = math.nan
        return blank
    low, p05, p50, p95, high = np.nanpercentile(data, LMP_PERCENTILES)
    return {"min": float(low), "p05": float(p05), "p50": float(p50),
            "p95": float(p95), "max": float(high),
            "spread_p95_p05": float(p95 - p05)}


@dataclass
class PathScan:
    loading: Dict[str, float] = field(default_factory=dict)
    binding: List[Dict[str, Any]] = field(default_factory=list)
    n_binding: Dict[int, int] = field(default_factory=dict)
    max_loading: Dict[int, float] = field(default_factory=dict)
    zero_limit_paths: List[str] = field(default_factory=list)


def scan_paths(results_dir: Path, key: ReportKey) -> PathScan:
    """
    PN_Pth in one pass: loading at the reported interval, the binding rows
    there, and per-interval binding counts and worst loading.

    loading = abs(Mw) / Max, which is what lib/devnet_stress_lib.py means by
    line_loading_pu (abs(p0) / s_nom). Max is the maximum flow limit; a path
    flowing against it is measured against Min in reality, so a value near 1.0
    on a reverse flow is an under-report by the ratio Max/abs(Min). The repo's
    definition is kept deliberately, so PSO and PyPSA artifacts stay
    comparable. Max == 0 gives NaN, never a division by zero: a path with no
    limit has no loading, and 0.0 would read as "empty".
    """
    path = require_result(results_dir, "PN_Pth")
    scan = PathScan()
    with result_reader(path) as (columns, rows):
        (i_cyc, i_scn, i_pth, i_int, i_mw, i_min, i_max, i_vio,
         i_bind, i_pen, i_sp, i_sac) = column_indexes(
            columns, ("cyc", "scn", "pth", "int", "Mw", "Min", "Max",
                      "Violation", "Binding", "Penalty", "SP", "SAC"), path
        )
        for row in rows:
            if row[i_cyc] != key.cycle or row[i_scn] != key.scenario:
                continue
            interval = int(row[i_int])
            limit = _num(row[i_max])
            flow = _num(row[i_mw])
            if _finite(limit) and limit != 0.0 and _finite(flow):
                loading = abs(flow) / limit
            else:
                loading = math.nan
                if _finite(limit) and limit == 0.0:
                    if row[i_pth] not in scan.zero_limit_paths:
                        scan.zero_limit_paths.append(row[i_pth])
            binding = _flag(row[i_bind])
            if binding:
                scan.n_binding[interval] = scan.n_binding.get(interval, 0) + 1
            else:
                scan.n_binding.setdefault(interval, 0)
            if _finite(loading):
                current = scan.max_loading.get(interval, math.nan)
                if not _finite(current) or loading > current:
                    scan.max_loading[interval] = loading
            else:
                scan.max_loading.setdefault(interval, math.nan)
            if interval != key.interval:
                continue
            scan.loading[row[i_pth]] = loading
            if binding:
                scan.binding.append({
                    "pth": row[i_pth],
                    "Mw": flow,
                    "Min": _num(row[i_min]),
                    "Max": limit,
                    "loading_pu": loading,
                    "Violation": _num(row[i_vio]),
                    "Penalty": _num(row[i_pen]),
                    "SP": _num(row[i_sp]),
                    "SAC": 1 if _flag(row[i_sac]) else 0,
                })
    return scan


@dataclass
class InjectorScan:
    dispatch: Dict[str, float] = field(default_factory=dict)
    tracked: Dict[str, Dict[int, Dict[str, float]]] = field(default_factory=dict)


def scan_injectors(results_dir: Path, key: ReportKey,
                   tracked: Sequence[str] = ()) -> InjectorScan:
    """
    ED_Inj in one pass: dispatch at the reported interval, plus every interval
    of the tracked injectors (the datacenter's, for the asymptote metric).

    ED_Inj.P is documented as "(MW) dispatch (LoadFlag adjusted)", so a
    LoadFlag=1 injector's P is a WITHDRAWAL and carries the opposite sign to a
    generator's. That is why nothing here sums P across injectors: the
    per-injector artifact is signed as PSO reports it, and bus_net_import()
    does the one sum that exists, deliberately, so the sign convention is
    stated in exactly one place.
    """
    path = require_result(results_dir, "ED_Inj")
    scan = InjectorScan()
    watch = set(name for name in tracked if name)
    for name in watch:
        scan.tracked[name] = {}
    with result_reader(path) as (columns, rows):
        (i_cyc, i_scn, i_inj, i_int, i_p, i_max, i_min,
         i_limvio, i_rampvio, i_pen) = column_indexes(
            columns, ("cyc", "scn", "inj", "int", "P", "Max", "Min",
                      "LimitViolation", "RampViolation", "Penalty"), path
        )
        for row in rows:
            if row[i_cyc] != key.cycle or row[i_scn] != key.scenario:
                continue
            injector = row[i_inj]
            interval = int(row[i_int])
            if interval == key.interval:
                scan.dispatch[injector] = _num(row[i_p])
            if injector in watch:
                scan.tracked[injector][interval] = {
                    "p_mw": _num(row[i_p]),
                    "max_mw": _num(row[i_max]),
                    "min_mw": _num(row[i_min]),
                    "limit_violation_mw": _num(row[i_limvio]),
                    "ramp_violation_mw_min": _num(row[i_rampvio]),
                    "penalty_usd": _num(row[i_pen]),
                }
    if not scan.dispatch:
        raise Ercot7kResultsError(
            "%s reports no injectors for cycle=%s scenario=%s interval=%d"
            % (path, key.cycle, key.scenario, key.interval)
        )
    return scan


# ------------------------------------------------------------------------------
# bus_net_import()
#
# The hardest artifact here, because half of it does not exist in the results.
#
#   load_at_node = ED_Ara.Load(I) * renormalized PF_AraNde.LoadFactor(nde)
#   gen_at_node  = sum of ED_Inj.P(I) over injectors mapped to that node
#   net_import   = load_at_node - gen_at_node
#
# Sign convention, matching lib/devnet_stress_lib.py exactly:
#   > 0  the node imports from the grid
#   < 0  the node exports to the grid
#
# ED_Inj.P is LoadFlag adjusted, so a datacenter load injector's P is negative
# and subtracting it ADDS to that node's net import -- which is right, and is
# the reason gen_at_node is a plain signed sum rather than a filtered one.
#
# The node universe is the reported node set (PC_Nd minus the reference nodes),
# so this artifact's index matches <tag>_lmp.csv's. Any load node or injector
# node outside that set is APPENDED rather than dropped, because a node
# carrying load that no report mentions is a finding, not a rounding error.
# ------------------------------------------------------------------------------
def bus_net_import(area_load: Dict[str, float],
                   distribution: LoadDistribution,
                   dispatch: Dict[str, float],
                   injector_node: Dict[str, str],
                   node_order: Sequence[str]) -> Dict[str, float]:
    load_at_node: Dict[str, float] = {}
    for area, load in area_load.items():
        if not _finite(load):
            continue
        for node, factor in distribution.normalized(area).items():
            load_at_node[node] = load_at_node.get(node, 0.0) + load * factor

    gen_at_node: Dict[str, float] = {}
    for injector, value in dispatch.items():
        node = injector_node.get(injector)
        if node is None or not _finite(value):
            continue
        gen_at_node[node] = gen_at_node.get(node, 0.0) + value

    nodes: List[str] = list(node_order)
    known = set(nodes)
    for extra in list(load_at_node) + list(gen_at_node):
        if extra not in known:
            known.add(extra)
            nodes.append(extra)

    return {node: load_at_node.get(node, 0.0) - gen_at_node.get(node, 0.0)
            for node in nodes}


# ------------------------------------------------------------------------------
#   The mapper
# ------------------------------------------------------------------------------
@dataclass
class MappedRun:
    """Everything one reported interval of one PSO run has to say."""
    summary: Dict[str, Any]
    binding_rows: List[Dict[str, Any]] = field(default_factory=list)
    deliverability_rows: List[Dict[str, Any]] = field(default_factory=list)
    chronology_rows: List[Dict[str, Any]] = field(default_factory=list)
    dashboard: Dict[str, Any] = field(default_factory=dict)
    context: Optional[StudyContext] = None


def map_results(results_dir: Path,
                interval: int,
                cycle: str = DEFAULT_CYCLE,
                scenario: Optional[str] = None,
                case_dir: Optional[Path] = None) -> MappedRun:
    """
    Maps one PSO run at ONE pinned interval.

    interval is required and is never guessed. Use pin_interval() once, persist
    it with write_study(), and pass the same number for every run of a sweep.
    """
    results_dir = Path(results_dir)
    if scenario is None:
        scenario = scenario_for_cycle(results_dir, cycle)
    key = ReportKey(cycle=cycle, scenario=scenario, interval=int(interval))
    context = study_context(results_dir, key, case_dir=case_dir)

    status = solution_status(results_dir)
    objectives = objective_by_cycle(results_dir)
    objective = objectives.get(cycle, math.nan)
    interval_cost = objective_by_interval(results_dir, cycle, scenario)
    area_metrics = area_metrics_by_interval(results_dir, cycle, scenario)
    if key.interval not in area_metrics:
        raise Ercot7kResultsError(
            "interval %d is not reported for (%s, %s); reported intervals are "
            "%d..%d" % (key.interval, cycle, scenario,
                        min(area_metrics), max(area_metrics))
        )

    nodes = scan_nodes(results_dir, key)
    paths = scan_paths(results_dir, key)
    tracked = context.dc_load_injectors() + context.dc_byog_injectors()
    injectors = scan_injectors(results_dir, key, tracked=tracked)

    total_load = area_metrics[key.interval]["load_mw"]

    # bus_net_import needs the case's INJ_NET to place injectors at nodes. With
    # no case directory it is not approximated, it is omitted -- write_outputs
    # already skips an empty mapping, so a results-only map stays valid.
    net_import: Dict[str, float] = {}
    distribution: Optional[LoadDistribution] = None
    if context.injector_node:
        distribution = load_distribution(results_dir)
        area_load_at_interval = _area_load_at(results_dir, key)
        net_import = bus_net_import(
            area_load=area_load_at_interval,
            distribution=distribution,
            dispatch=injectors.dispatch,
            injector_node=context.injector_node,
            node_order=list(nodes.lmp),
        )

    dc_dispatch = math.nan
    byog = context.dc_byog_injectors()
    if byog:
        values = [injectors.dispatch.get(name, math.nan) for name in byog]
        finite = [v for v in values if _finite(v)]
        dc_dispatch = float(sum(finite)) if finite else math.nan

    summary: Dict[str, Any] = {
        "snapshot": context.datetime_text() or "int %d" % key.interval,
        "objective": float(objective),
        "total_system_load_mw": float(total_load),
        "generator_dispatch_mw": {k: float(v)
                                  for k, v in injectors.dispatch.items()},
        "bus_net_import_mw": {k: float(v) for k, v in net_import.items()},
        "dc_dispatch_mw": dc_dispatch,
        "lmp": {k: float(v) for k, v in nodes.lmp.items()},
        "line_loading_pu": {k: float(v) for k, v in paths.loading.items()},
        "status": status.status,
        "cycle": key.cycle,
        "scenario": key.scenario,
        "interval": int(key.interval),
        "datetime": context.datetime_text(),
    }

    run = MappedRun(summary=summary, context=context)
    run.binding_rows = list(paths.binding)
    run.deliverability_rows = _deliverability_rows(
        context, area_metrics, injectors
    )
    run.chronology_rows = _chronology_rows(
        context, area_metrics, interval_cost, nodes, paths, injectors
    )
    run.dashboard = _dashboard_figures(
        context, summary, status, objectives, nodes, paths, injectors,
        distribution
    )
    return run


def _area_load_at(results_dir: Path, key: ReportKey) -> Dict[str, float]:
    """ED_Ara.Load per area at the reported interval."""
    path = require_result(results_dir, "ED_Ara")
    out: Dict[str, float] = {}
    for record in read_result_records(path):
        if record["cyc"] != key.cycle or record["scn"] != key.scenario:
            continue
        if int(record["int"]) != key.interval:
            continue
        value = _num(record["Load"])
        if _finite(value):
            out[record["ara"]] = out.get(record["ara"], 0.0) + value
    return out


# ------------------------------------------------------------------------------
# _deliverability_rows()
#
# The asymptote metric, and the point of the whole exercise.
#
# PSO's injector dispatch limits are SOFT: ED.ams computes
# LimitV(inj,tpRP) := xKPmax(inj,tpRP) - xKPmin(inj,tpRP) over penalized slack
# variables, and reports the result per injector. So a datacenter pinned by
# SCN_INJ_DSP that cannot be delivered does NOT make the model infeasible and
# does NOT vanish into a system-wide number: it produces a priced violation
# attributed to its own injector.
#
#   DC deliverability : ED_Inj.LimitViolation / Penalty on the DC load injector
#   system shortfall  : ED_Ara.Violation / Penalty
#
# Both come out of one run, side by side, which is what lets a run say whether
# the grid or the datacenter gave way first.
#
# With no manifest there is no datacenter, so only the system columns are
# emitted. A base run still maps.
# ------------------------------------------------------------------------------
def _deliverability_rows(context: StudyContext,
                         area_metrics: Dict[int, Dict[str, float]],
                         injectors: InjectorScan) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for interval in sorted(area_metrics):
        base: Dict[str, Any] = {
            "int": interval,
            "datetime": context.datetime_text(interval),
            "system_violation_mw": area_metrics[interval]["violation_mw"],
            "system_penalty_usd": area_metrics[interval]["penalty_usd"],
        }
        if not context.has_datacenter:
            rows.append(base)
            continue
        for spec in context.datacenters:
            row = dict(base)
            row["dc_name"] = spec.get("dc_name", "")
            row["dc_node"] = spec.get("node", "")
            for prefix, injector in (("dc", spec.get("load_injector", "")),
                                     ("byog", spec.get("byog_injector", ""))):
                sample = injectors.tracked.get(injector, {}).get(interval, {})
                row["%s_injector" % prefix] = injector
                row["%s_p_mw" % prefix] = sample.get("p_mw", math.nan)
                row["%s_max_mw" % prefix] = sample.get("max_mw", math.nan)
                row["%s_limit_violation_mw" % prefix] = sample.get(
                    "limit_violation_mw", math.nan)
                row["%s_penalty_usd" % prefix] = sample.get(
                    "penalty_usd", math.nan)
            rows.append(row)
    return rows


# ------------------------------------------------------------------------------
# _chronology_rows()
#
# One row per interval of the reported cycle. This is what makes a single run
# readable without a sweep: the pinned interval is one row of it, and the shape
# of the day around that row is what says whether the pin is representative.
# ------------------------------------------------------------------------------
def _chronology_rows(context: StudyContext,
                     area_metrics: Dict[int, Dict[str, float]],
                     interval_cost: Dict[int, float],
                     nodes: NodeScan,
                     paths: PathScan,
                     injectors: InjectorScan) -> List[Dict[str, Any]]:
    dc_injectors = context.dc_load_injectors()
    rows: List[Dict[str, Any]] = []
    for interval in sorted(area_metrics):
        stats = nodes.percentiles.get(interval, {})
        dc_violation = math.nan
        if dc_injectors:
            values = [
                injectors.tracked.get(name, {}).get(interval, {}).get(
                    "limit_violation_mw", math.nan)
                for name in dc_injectors
            ]
            finite = [v for v in values if _finite(v)]
            dc_violation = float(sum(finite)) if finite else math.nan
        rows.append({
            "int": interval,
            "datetime": context.datetime_text(interval),
            "load_mw": area_metrics[interval]["load_mw"],
            "objective_interval": interval_cost.get(interval, math.nan),
            "lmp_min": stats.get("min", math.nan),
            "lmp_p05": stats.get("p05", math.nan),
            "lmp_p50": stats.get("p50", math.nan),
            "lmp_p95": stats.get("p95", math.nan),
            "lmp_max": stats.get("max", math.nan),
            "lmp_spread_p95_p05": stats.get("spread_p95_p05", math.nan),
            "n_binding": paths.n_binding.get(interval, 0),
            "max_loading_pu": paths.max_loading.get(interval, math.nan),
            "dc_limit_violation_mw": dc_violation,
        })
    return rows


CHRONOLOGY_COLUMNS: Tuple[str, ...] = (
    "int", "datetime", "load_mw", "objective_interval",
    "lmp_min", "lmp_p05", "lmp_p50", "lmp_p95", "lmp_max",
    "lmp_spread_p95_p05", "n_binding", "max_loading_pu",
    "dc_limit_violation_mw",
)

BINDING_COLUMNS: Tuple[str, ...] = (
    "pth", "Mw", "Min", "Max", "loading_pu", "Violation", "Penalty", "SP",
    "SAC",
)


# ------------------------------------------------------------------------------
# _dashboard_figures()
#
# The scalars the dashboard prints. Kept separate from the summary dict because
# the summary is the <tag>.json payload and must carry collect_results' keys
# and nothing else -- update_index_html and the plot scripts read that file.
# ------------------------------------------------------------------------------
def _dashboard_figures(context: StudyContext,
                       summary: Dict[str, Any],
                       status: SolutionStatus,
                       objectives: Dict[str, float],
                       nodes: NodeScan,
                       paths: PathScan,
                       injectors: InjectorScan,
                       distribution: Optional[LoadDistribution]
                       ) -> Dict[str, Any]:
    key = context.key
    stats = nodes.percentiles.get(key.interval, {})
    lmp = summary["lmp"]
    loading = summary["line_loading_pu"]

    finite_lmp = {k: v for k, v in lmp.items() if _finite(v)}
    max_lmp_node = (max(finite_lmp, key=finite_lmp.__getitem__)
                    if finite_lmp else "")
    min_lmp_node = (min(finite_lmp, key=finite_lmp.__getitem__)
                    if finite_lmp else "")

    finite_loading = {k: v for k, v in loading.items() if _finite(v)}
    max_loading_path = (max(finite_loading, key=finite_loading.__getitem__)
                        if finite_loading else "")

    dc_lmp: Dict[str, float] = {}
    for spec in context.datacenters:
        node = spec.get("node", "")
        if node:
            dc_lmp[node] = lmp.get(node, math.nan)

    dc_figures: List[Dict[str, Any]] = []
    for spec in context.datacenters:
        entry: Dict[str, Any] = {"dc_name": spec.get("dc_name", "")}
        for prefix, injector in (("dc", spec.get("load_injector", "")),
                                 ("byog", spec.get("byog_injector", ""))):
            sample = injectors.tracked.get(injector, {})
            at_interval = sample.get(key.interval, {})
            violations = [v["limit_violation_mw"] for v in sample.values()
                          if _finite(v["limit_violation_mw"])]
            entry["%s_injector" % prefix] = injector
            entry["%s_p_mw" % prefix] = at_interval.get("p_mw", math.nan)
            entry["%s_limit_violation_mw" % prefix] = at_interval.get(
                "limit_violation_mw", math.nan)
            entry["%s_penalty_usd" % prefix] = at_interval.get(
                "penalty_usd", math.nan)
            entry["%s_violation_intervals" % prefix] = sum(
                1 for v in violations if v != 0.0)
            entry["%s_worst_violation_mw" % prefix] = (
                max(violations, key=abs) if violations else math.nan)
        dc_figures.append(entry)

    return {
        "solves": status.solves,
        "status_counts": dict(status.counts),
        "objective_by_cycle": dict(objectives),
        "lmp_stats": dict(stats),
        "lmp_spread_p95_p05": stats.get("spread_p95_p05", math.nan),
        "lmp_spread_maxmin": stats.get("max", math.nan) - stats.get(
            "min", math.nan),
        "max_lmp": finite_lmp.get(max_lmp_node, math.nan),
        "max_lmp_node": max_lmp_node,
        "min_lmp": finite_lmp.get(min_lmp_node, math.nan),
        "min_lmp_node": min_lmp_node,
        "n_nodes": len(lmp),
        "n_paths": len(loading),
        "n_injectors": len(summary["generator_dispatch_mw"]),
        "max_loading_pu": finite_loading.get(max_loading_path, math.nan),
        "max_loading_path": max_loading_path,
        "near_bind_ct": sum(1 for v in finite_loading.values()
                            if v >= NEAR_BIND_THRESHOLD),
        "n_binding": len(paths.binding),
        "zero_limit_paths": len(paths.zero_limit_paths),
        "dc_lmp": dc_lmp,
        "datacenters": dc_figures,
        "load_factor_raw_sum": (
            {area: distribution.raw_sum(area)
             for area in distribution.areas()}
            if distribution is not None else {}
        ),
    }


# ------------------------------------------------------------------------------
#   Artifact writing
# ------------------------------------------------------------------------------
# Byte format is not negotiable: update_index_html and the plot scripts already
# consume artifacts written by pd.Series.to_csv, so these go out through the
# same call. That fixes the header (",<name>"), the float repr
# ("58.333333333333336", "0.0"), the blank for NaN and the platform line
# terminator, all of which a hand-rolled writer would have to reproduce by
# agreement rather than by construction. The committed reference run under
# devnet-reference-runs/ is the format of record.
#
# The large tables are still read with the csv module. pandas appears here for
# WRITING a few thousand rows, never for reading 287 MB.
# ------------------------------------------------------------------------------
def write_series_csv(path: Path, mapping: Dict[str, float],
                     name: str) -> None:
    pd.Series(mapping, name=name, dtype="float64").to_csv(path)


def write_frame_csv(path: Path, rows: Sequence[Dict[str, Any]],
                    columns: Sequence[str]) -> None:
    frame = pd.DataFrame(list(rows), columns=list(columns))
    frame.to_csv(path, index=False)


def write_artifacts(outdir: Path, tag: str, run: MappedRun) -> Dict[str, Path]:
    """Writes every artifact and returns {kind: path} for the ones written."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = run.summary
    written: Dict[str, Path] = {}

    path = outdir / ("%s.json" % tag)
    with path.open("w", encoding="ascii") as handle:
        json.dump(summary, handle, indent=2)
    written["json"] = path

    for kind, key, column in (
        ("lmp", "lmp", "lmp"),
        ("line_loading_pu", "line_loading_pu", "loading_pu"),
        ("generator_dispatch_mw", "generator_dispatch_mw", "dispatch_mw"),
        ("bus_net_import_mw", "bus_net_import_mw", "net_import_mw"),
    ):
        mapping = summary.get(key) or {}
        if not mapping:
            continue
        path = outdir / ("%s_%s.csv" % (tag, kind))
        write_series_csv(path, mapping, column)
        written[kind] = path

    path = outdir / ("%s_objective.csv" % tag)
    pd.Series({"objective": summary.get("objective", math.nan),
               "total_system_load_mw": summary.get("total_system_load_mw",
                                                   math.nan)}).to_csv(path)
    written["objective"] = path

    path = outdir / ("%s_binding.csv" % tag)
    write_frame_csv(path, run.binding_rows, BINDING_COLUMNS)
    written["binding"] = path

    path = outdir / ("%s_deliverability.csv" % tag)
    write_frame_csv(path, run.deliverability_rows,
                    deliverability_columns(run))
    written["deliverability"] = path

    path = outdir / ("%s_chronology.csv" % tag)
    write_frame_csv(path, run.chronology_rows, CHRONOLOGY_COLUMNS)
    written["chronology"] = path

    return written


def deliverability_columns(run: MappedRun) -> List[str]:
    """
    System columns always; the DC columns only when a manifest named a
    datacenter. A base run's deliverability file is the system half alone,
    which is the honest answer rather than a column of NaN pretending a
    datacenter was measured.
    """
    columns = ["int", "datetime", "system_violation_mw", "system_penalty_usd"]
    if run.context is not None and run.context.has_datacenter:
        columns += ["dc_name", "dc_node"]
        for prefix in ("dc", "byog"):
            columns += ["%s_injector" % prefix, "%s_p_mw" % prefix,
                        "%s_max_mw" % prefix,
                        "%s_limit_violation_mw" % prefix,
                        "%s_penalty_usd" % prefix]
    return columns


# ------------------------------------------------------------------------------
#   Dashboard
# ------------------------------------------------------------------------------
# lib/devnet_stress_lib.py cannot change, and its update_index_html() scrapes
# the dashboard markdown by LINE PREFIX, so this emits the same prefix-keyed
# format rather than calling its dashboard_text() (which needs a pypsa.Network
# and a devnet argparse namespace, neither of which exists here).
#
# Two mechanical facts about that scraper drive the layout below.
#
# 1. The scrape is `elif line.startswith("lmp_spread")`, inside a loop that
#    OVERWRITES m["lmp_spread"] on every match. Its own later branch for
#    "lmp_spread_max" is therefore dead code, and two lines both starting
#    "lmp_spread" would resolve to whichever came LAST -- the opposite of what
#    a reader expects. So exactly ONE line here starts with "lmp_spread", it is
#    emitted first, and it carries P95 - P05. The max-minus-min figure is still
#    emitted, on a line named "lmp_maxmin" and labelled lmp_spread_maxmin for
#    continuity with the devnet reference runs, where it cannot collide.
#
# 2. The same loop scrapes "objective", "max_loading_pu" and "near_bind_ct" by
#    prefix. No other line may start with any of those, which is why the
#    per-interval cost is called "interval_cost" and not "objective_interval"
#    here, and why the binding count line is "binding_ct".
#
# Every per-entity listing is capped at DASHBOARD_TOP_N with a footer naming
# the CSV that holds the rest.
# ------------------------------------------------------------------------------
def _fmt(value: Any, spec: str = ",.3f") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    return format(number, spec)


def _listing(lines: List[str], title: str, mapping: Dict[str, float],
             tag: str, artifact: str, width: int = 24) -> None:
    if not mapping:
        return
    lines.append(title)
    ranked = sorted(mapping.items(),
                    key=lambda kv: (-abs(kv[1]) if _finite(kv[1]) else 0.0,
                                    kv[0]))
    for name, value in ranked[:DASHBOARD_TOP_N]:
        lines.append("  %-*s: %10s" % (width, name[:width], _fmt(value, ",.1f")))
    remaining = len(ranked) - DASHBOARD_TOP_N
    if remaining > 0:
        lines.append("  ... %d more, see %s_%s.csv" % (remaining, tag, artifact))


def dashboard_text(run: MappedRun, tag: str, mode: Optional[str] = None,
                   label: Optional[str] = None) -> str:
    """
    The same prefix-keyed dashboard update_index_html() expects, for a PSO run.

    mode must carry its own "::" sub-segment, because the scraper reads the
    scenario column as parts[-1] of an ASR-DASH line split on "::" and only
    when there are at least FOUR parts. devnet satisfies that with
    "COMMIT::c3"; the default here is "MAP::<cycle>". label defaults to the tag
    and is what lands in the scenario column.
    """
    summary = run.summary
    dash = run.dashboard
    context = run.context
    label = label or tag
    if mode is None:
        mode = "MAP::%s" % summary["cycle"]

    lines: List[str] = []
    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    lines.append("ASR-DASH::%s::%s" % (mode, label))
    lines.append(SUBSECTION_SEPARATOR.rstrip("\n"))

    lines.append(
        "report           : cycle=%s  scenario=%s  interval=%s  datetime=%s"
        % (summary["cycle"], summary["scenario"], summary["interval"],
           summary["datetime"] or "n/a")
    )
    lines.append(
        "solver           : %s  (%d solves: %s)"
        % (summary["status"], dash.get("solves", 0),
           ", ".join("%s=%d" % (k, v)
                     for k, v in sorted(
                         (dash.get("status_counts") or {}).items())))
    )
    # "objective" is scraped by prefix. This is the only line that may start
    # with it, and it carries the reported cycle's MC_Hrzn.DeltaCost sum.
    lines.append("objective        : %s   (%s DeltaCost sum)"
                 % (_fmt(summary["objective"], ".3e"), summary["cycle"]))
    lines.append("total_load_mw     : %s"
                 % _fmt(summary["total_system_load_mw"], ",.1f"))
    lines.append("interval_cost    : %s"
                 % _fmt(_interval_cost(run), ",.1f"))

    _listing(lines, "generator_dispatch_mw:", summary["generator_dispatch_mw"],
             tag, "generator_dispatch_mw")
    _listing(lines, "bus_import_export_mw (+IMPORT / -EXPORT):",
             summary["bus_net_import_mw"], tag, "bus_net_import_mw")

    for node, value in (dash.get("dc_lmp") or {}).items():
        lines.append("dc_node_lmp      : %s @ %s" % (_fmt(value), node))

    # ONE line starting with "lmp_spread", emitted first, carrying P95 - P05.
    lines.append(
        "lmp_spread       : %s   (P95 - P05)  p05: %s  p50: %s  p95: %s"
        % (_fmt(dash.get("lmp_spread_p95_p05")),
           _fmt((dash.get("lmp_stats") or {}).get("p05")),
           _fmt((dash.get("lmp_stats") or {}).get("p50")),
           _fmt((dash.get("lmp_stats") or {}).get("p95")))
    )
    lines.append(
        "lmp_maxmin       : %s   lmp_spread_maxmin (max - min)  "
        "max_lmp: %s @ %s  min_lmp: %s @ %s"
        % (_fmt(dash.get("lmp_spread_maxmin")),
           _fmt(dash.get("max_lmp")), dash.get("max_lmp_node") or "n/a",
           _fmt(dash.get("min_lmp")), dash.get("min_lmp_node") or "n/a")
    )
    lines.append("nodes_reported   : %d" % dash.get("n_nodes", 0))

    lines.append("max_loading_pu   : %s @ %s"
                 % (_fmt(dash.get("max_loading_pu")),
                    dash.get("max_loading_path") or "n/a"))
    lines.append("near_bind_ct(>=%.2f): %d"
                 % (NEAR_BIND_THRESHOLD, dash.get("near_bind_ct", 0)))
    lines.append("binding_ct       : %d of %d monitored paths"
                 % (dash.get("n_binding", 0), dash.get("n_paths", 0)))
    _listing(lines, "top_lines:", summary["line_loading_pu"], tag,
             "line_loading_pu")

    lines.extend(_deliverability_lines(run))

    for area, total in sorted((dash.get("load_factor_raw_sum") or {}).items()):
        lines.append(
            "load_factor_sum  : area %s raw %s (renormalized to 1.0 before "
            "distributing area load)" % (area, _fmt(total, ".6f"))
        )

    lines.append(SECTION_SEPARATOR.rstrip("\n"))
    return "\n".join(lines) + "\n"


def _interval_cost(run: MappedRun) -> float:
    for row in run.chronology_rows:
        if row["int"] == run.summary["interval"]:
            return row["objective_interval"]
    return math.nan


def _deliverability_lines(run: MappedRun) -> List[str]:
    """The asymptote figures: who gave way first, the grid or the datacenter."""
    lines: List[str] = []
    system = [row["system_violation_mw"] for row in run.deliverability_rows
              if _finite(row.get("system_violation_mw", math.nan))]
    worst_system = max(system, key=abs) if system else math.nan
    hours_system = sum(1 for v in system if v != 0.0)
    lines.append(
        "sys_violation    : worst %s MW over %d of %d intervals"
        % (_fmt(worst_system, ",.3f"), hours_system,
           len(run.deliverability_rows) or 0)
    )
    context = run.context
    if context is None or not context.has_datacenter:
        lines.append(
            "dc_deliverability: no datacenter in the case manifest, so the "
            "DC columns are absent (base run)"
        )
        return lines
    for entry in run.dashboard.get("datacenters") or []:
        lines.append(
            "dc_deliverability: %s  P %s MW  LimitViolation %s MW  "
            "Penalty %s  violated in %s intervals (worst %s MW)"
            % (entry.get("dc_injector") or "n/a",
               _fmt(entry.get("dc_p_mw"), ",.3f"),
               _fmt(entry.get("dc_limit_violation_mw"), ",.3f"),
               _fmt(entry.get("dc_penalty_usd"), ",.3f"),
               entry.get("dc_violation_intervals", 0),
               _fmt(entry.get("dc_worst_violation_mw"), ",.3f"))
        )
        lines.append(
            "byog_dispatch    : %s  P %s MW  LimitViolation %s MW"
            % (entry.get("byog_injector") or "n/a",
               _fmt(entry.get("byog_p_mw"), ",.3f"),
               _fmt(entry.get("byog_limit_violation_mw"), ",.3f"))
        )
    return lines


# ------------------------------------------------------------------------------
#   Command line
# ------------------------------------------------------------------------------
# Nothing above this line runs at import time. This block exists so the module
# is usable from a shell without a front end, and is the only place that
# prints.
# ------------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ercot7k_results.py",
        description="Map a solved PSO run into this repo's artifact shapes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pin = sub.add_parser("pin", help="report the peak-congestion interval")
    pin.add_argument("results_dir")
    pin.add_argument("--cycle", default=DEFAULT_CYCLE)
    pin.add_argument("--scenario", default=None)
    pin.add_argument("--case-dir", default=None,
                     help="write study.json into this case directory")
    pin.add_argument("--force", action="store_true",
                     help="overwrite an existing study.json pin")

    mapper = sub.add_parser("map", help="write the artifacts")
    mapper.add_argument("results_dir")
    mapper.add_argument("outdir")
    mapper.add_argument("tag")
    mapper.add_argument("--interval", type=int, default=None,
                        help="required unless --case-dir carries a study.json")
    mapper.add_argument("--cycle", default=DEFAULT_CYCLE)
    mapper.add_argument("--scenario", default=None)
    mapper.add_argument("--case-dir", default=None)
    mapper.add_argument("--dashboard", default=None,
                        help="also write the dashboard markdown here")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "pin":
        scenario = args.scenario or scenario_for_cycle(args.results_dir,
                                                       args.cycle)
        interval = pin_interval(args.results_dir, args.cycle, scenario)
        loads = area_load_by_interval(args.results_dir, args.cycle, scenario)
        print("cycle    : %s" % args.cycle)
        print("scenario : %s" % scenario)
        print("interval : %d" % interval)
        print("load_mw  : %s" % _fmt(loads[interval], ",.3f"))
        if args.case_dir:
            key = ReportKey(cycle=args.cycle, scenario=scenario,
                            interval=interval)
            path = write_study(Path(args.case_dir), key,
                               results_dir=Path(args.results_dir),
                               force=args.force)
            print("study    : %s" % path)
        return 0

    interval = args.interval
    if interval is None:
        if not args.case_dir:
            print("AMW-ERR: --interval is required unless --case-dir carries "
                  "a study.json. The reported interval must be pinned by the "
                  "study, not recomputed per run.", file=sys.stderr)
            return 2
        interval = pinned_report_key(Path(args.case_dir)).interval

    run = map_results(args.results_dir, interval=interval, cycle=args.cycle,
                      scenario=args.scenario, case_dir=args.case_dir)
    written = write_artifacts(Path(args.outdir), args.tag, run)
    text = dashboard_text(run, args.tag)
    if args.dashboard:
        Path(args.dashboard).write_text(text, encoding="ascii")
    print(text, end="")
    for kind in sorted(written):
        print("wrote %-22s %s" % (kind, written[kind]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ------------------------------------------------------------------------------
# END OF ercot7k_results.py
# ------------------------------------------------------------------------------
