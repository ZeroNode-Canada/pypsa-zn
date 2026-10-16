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

# cut_mini7k.py
#
# Purpose
#   Cut the tests/fixtures/mini7k/ test case out of the real ercot7k/ case.
#   The fixture is checked in, but it is CUT rather than hand-typed so that
#   every header line, every column order and every field's text is provably
#   the real thing. A hand-written fixture would pass a test suite that a real
#   case fails, which is the one failure mode a fixture must not have.
#
# What it does
#   - Selects a small, self-consistent slice: a few nodes including both ends
#     of a Monitor=1 branch AND at least one node touched only by Monitor=0
#     branches (so V8 has something to find), the SlackBusName node, and the
#     injectors sited on those nodes.
#   - Shrinks the horizon from 265 time points to 12, keeping MDL_ID's
#     MinDate < StartDate < StopDate < MaxDate relationship and proportions.
#   - Filters CYC_* tables through keep_cycle_rows(), which ALWAYS preserves
#     rows keyed on cycle "0". Cycle "0" is the all-cycles wildcard, not a
#     cycle: filtering it away silently deletes data (in this case the whole
#     of CYC_INJ_CCV, all 357 rows of which are on cycle "0").
#   - Runs verify_case() on the result and refuses to emit a fixture that does
#     not pass its own checks clean.
#
# Outputs
#   - tests/fixtures/mini7k/ (a complete, verifiable PSO case directory)
#
# Run: python tests/cut_mini7k.py
# ------------------------------------------------------------------------------

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ercot7k_case as ec  # noqa: E402  (path juggling has to come first)

# Global defines
SECTION_SEPARATOR = "="*80 + "\n"  # for print separation
SUBSECTION_SEPARATOR = "-"*40 + "\n"  # for print separation

BASE_DIR = REPO_ROOT / "ercot7k"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "mini7k"

# 12 time points, so 11 intervals. The base runs 265 points over 264 hours with
# StartDate at +72 h (27.3 per cent in) and StopDate at +240 h (Max - 24 h,
# 90.9 per cent in). The same proportions on an 11-hour span put StartDate at
# +3 h and StopDate at +10 h, keeping MinDate < StartDate < StopDate < MaxDate
# and keeping a lead window before the horizon and a tail after it.
TIMEPOINTS = 12
START_OFFSET_HOURS = 3
STOP_OFFSET_HOURS = 10

# Cycle timings scale with the horizon so the fixture stays internally
# coherent: SC and DA run a 24 h step with 48 h of lead on the real case.
CYCLE_SCALE_FIELDS = {
    "CYC_ID": {"DeltaTime": {"24": "2"}, "LeadTime": {"48": "4"}},
    "CYC_SAI": {"PriorTime": {"24": "2"}},
}

# Periods per cycle in the cut case. The base carries SC 1..24, DA 1..33 and
# RT 1; four is enough to keep the table shaped like the real one.
PERIODS_KEPT = 4

WANTED_MONITORED_BRANCHES = 2
WANTED_UNMONITORED_BRANCHES = 3
WANTED_INJECTORS = 8

# SCN_INJ_MAX splits the injector set into two populations that the writer
# treats completely differently: the 167 renewables that already carry
# availability schedules (ScaleFactor only, never MaxMw) and everything else
# (append a MaxMw on the default scenario '0'). A fixture holding only one
# population cannot exercise the rule that separates them, so the cut takes a
# few of the scheduled injectors ON PURPOSE, in addition to the thermal units
# the node slice happens to pick up.
WANTED_SCHEDULED_INJECTORS = 2


# ------------------------------------------------------------------------------
# keep_cycle_rows()
#
# Filters a CYC_* table to a set of cycles, ALWAYS preserving rows keyed on
# cycle "0".
#
# "0" is the all-cycles wildcard, not a cycle name. Treating it as a cycle and
# filtering it out removes data that applied to every cycle, with no error and
# no missing-key complaint anywhere downstream: CYC_INJ_CCV in this case is
# entirely cycle "0", so a naive filter deletes every cost-curve mapping in
# the model and the units silently become free.
# ------------------------------------------------------------------------------
def keep_cycle_rows(records: Sequence[Dict[str, str]],
                    cycles: Set[str]) -> Callable[[Dict[str, str]], bool]:
    keep = set(cycles) | {"0", ""}

    def predicate(record: Dict[str, str]) -> bool:
        return record.get("Cycle", "") in keep

    return predicate


# ------------------------------------------------------------------------------
# filter_table()
#
# Rebuilds a Table keeping only the data lines whose parsed record satisfies
# `predicate`, and keeping each kept line's ORIGINAL text byte for byte. Rows
# are never re-serialized here, so "746.000" cannot become "746.0" on the way
# into the fixture.
# ------------------------------------------------------------------------------
def filter_table(table: ec.Table,
                 predicate: Callable[[Dict[str, str]], bool]) -> None:
    columns = table.columns
    kept: List[str] = [table.raw_lines[0]]
    for raw in table.data_lines:
        record = dict(zip(columns, ec._parse_line(raw)))
        if predicate(record):
            kept.append(raw)
    table.raw_lines = kept


# ------------------------------------------------------------------------------
# edit_table()
#
# Rewrites every data line through `transform`, which is handed the record and
# returns the record to write. Used only for the few fields that have to move
# with the shrunken horizon.
# ------------------------------------------------------------------------------
def edit_table(table: ec.Table,
               transform: Callable[[Dict[str, str]], Dict[str, str]]) -> None:
    columns = table.columns
    rebuilt: List[str] = [table.raw_lines[0]]
    for raw in table.data_lines:
        record = dict(zip(columns, ec._parse_line(raw)))
        updated = transform(dict(record))
        if updated == record:
            rebuilt.append(raw)
        else:
            rebuilt.append(table.build_line(updated))
    table.raw_lines = rebuilt


# ------------------------------------------------------------------------------
# select_slice()
#
# Chooses the nodes and injectors the fixture keeps. Deterministic: everything
# is taken in the order it appears in the real files, so re-cutting produces
# the same fixture.
# ------------------------------------------------------------------------------
def select_slice(tables: Dict[str, ec.Table]) -> Dict[str, Set[str]]:
    branches = tables["BRN_ID"].records()
    net = tables["INJ_NET"].records()
    options = {r["OptionName"]: r["OptionValue"]
               for r in tables[ec.CONTROL_TABLE].records()}

    injector_nodes = {r["Injector"]: r["Node"] for r in net}
    hosted: Dict[str, List[str]] = {}
    for injector, node in injector_nodes.items():
        hosted.setdefault(node, []).append(injector)

    nodes: Set[str] = set()

    # Both ends of the first few monitored branches that host an injector, so
    # the fixture has a Monitor=1 branch AND something sitting on it.
    monitored_taken = 0
    for record in branches:
        if record["Monitor"] != "1":
            continue
        if record["FrEnode"] not in hosted and record["ToEnode"] not in hosted:
            continue
        nodes.update([record["FrEnode"], record["ToEnode"]])
        monitored_taken += 1
        if monitored_taken >= WANTED_MONITORED_BRANCHES:
            break

    # Both ends of a few Monitor=0 branches whose endpoints are not already in,
    # so the fixture also has nodes touched ONLY by unmonitored branches. That
    # is what makes V8 a check that can actually fire.
    unmonitored_taken = 0
    for record in branches:
        if record["Monitor"] != "0":
            continue
        pair = {record["FrEnode"], record["ToEnode"]}
        if pair & nodes:
            continue
        nodes.update(pair)
        unmonitored_taken += 1
        if unmonitored_taken >= WANTED_UNMONITORED_BRANCHES:
            break

    # The slack bus must exist in NDE_ID or the case does not describe itself.
    slack = options.get("SlackBusName")
    if slack:
        nodes.add(slack)

    injectors: Set[str] = set()
    for record in net:
        if record["Node"] in nodes:
            injectors.add(record["Injector"])
        if len(injectors) >= WANTED_INJECTORS:
            break

    if not injectors:
        raise SystemExit("cut_mini7k: the selected nodes host no injectors")

    # A few injectors that already carry SCN_INJ_MAX availability schedules,
    # with their nodes dragged in behind them. Taken in file order so the cut
    # stays deterministic.
    scheduled: List[str] = []
    for record in tables["SCN_INJ_MAX"].records():
        name = record["Injector"]
        if name in injectors or name in scheduled:
            continue
        if name not in injector_nodes:
            continue
        scheduled.append(name)
        if len(scheduled) >= WANTED_SCHEDULED_INJECTORS:
            break
    if len(scheduled) < WANTED_SCHEDULED_INJECTORS:
        raise SystemExit(
            "cut_mini7k: fewer than %d scheduled injectors found in "
            "SCN_INJ_MAX" % WANTED_SCHEDULED_INJECTORS)
    injectors.update(scheduled)
    nodes.update(injector_nodes[name] for name in scheduled)

    return {"nodes": nodes, "injectors": injectors}


# ------------------------------------------------------------------------------
# cut()
#
# Writes the fixture.
# ------------------------------------------------------------------------------
def cut(base_dir: Path = BASE_DIR, out_dir: Path = FIXTURE_DIR) -> Path:
    prefix = ec.case_prefix(base_dir)
    tables = ec.read_case(base_dir, prefix)

    chosen = select_slice(tables)
    nodes, injectors = chosen["nodes"], chosen["injectors"]

    # ----- horizon -----
    fmt = ec.aimms_date_format(tables)
    mdl = ec.model_id(tables)
    min_date = datetime.strptime(mdl["MinDate"], fmt)
    step = ec.interval_delta(mdl)
    kept_times = [(min_date + step * i).strftime(fmt) for i in range(TIMEPOINTS)]
    max_date = min_date + step * (TIMEPOINTS - 1)
    start_date = min_date + timedelta(hours=START_OFFSET_HOURS)
    stop_date = min_date + timedelta(hours=STOP_OFFSET_HOURS)
    kept_time_set = set(kept_times)

    edit_table(tables["MDL_ID"], lambda r: dict(
        r,
        MaxDate=max_date.strftime(fmt),
        StartDate=start_date.strftime(fmt),
        StopDate=stop_date.strftime(fmt),
    ))

    cycles = {r["Cycle"] for r in tables["CYC_ID"].records()}

    # ----- network -----
    filter_table(tables["NDE_ID"], lambda r: r["Enode"] in nodes)
    filter_table(tables["BRN_ID"],
                 lambda r: r["FrEnode"] in nodes and r["ToEnode"] in nodes)
    filter_table(tables["STE_NDE"], lambda r: r["Enode"] in nodes)

    # ----- injectors -----
    for name in ("INJ_ID", "INJ_NET", "INJ_CMT", "INJ_STG_CMT", "RSV_INJ"):
        filter_table(tables[name], lambda r: r["Injector"] in injectors)
    filter_table(tables["CYC_INJ_CCV"], lambda r: r["Injector"] in injectors)
    filter_table(tables["SCN_INJ_MAX"], lambda r: r["Injector"] in injectors)

    curves = {r["CostCurve"] for r in tables["CYC_INJ_CCV"].records()}
    filter_table(tables["CCV_ATT"], lambda r: r["CostCurve"] in curves)
    filter_table(tables["CCV_PNT"], lambda r: r["CostCurve"] in curves)

    # ----- cycles -----
    # Both CYC_* filters go through keep_cycle_rows() so that cycle "0" is
    # preserved by construction rather than by remembering to.
    filter_table(tables["CYC_INJ_CCV"], keep_cycle_rows(
        tables["CYC_INJ_CCV"].records(), cycles))
    filter_table(tables["CYC_PRD_ID"], keep_cycle_rows(
        tables["CYC_PRD_ID"].records(), cycles))
    filter_table(tables["CYC_PRD_ID"],
                 lambda r: int(r["Period"]) <= PERIODS_KEPT)
    for name, fields in CYCLE_SCALE_FIELDS.items():
        def scale(record: Dict[str, str], fields=fields) -> Dict[str, str]:
            for column, mapping in fields.items():
                if record.get(column) in mapping:
                    record[column] = mapping[record[column]]
            return record
        edit_table(tables[name], scale)

    # ----- schedules -----
    # SCN_ARA_LOD keeps BOTH rows: the default "0" row driving SC and DA, and
    # the ScnRT row driving the reported cycle. Dropping either would hide the
    # k_load failure mode V6 exists to catch.
    wanted_schedules: Set[str] = set()
    for name in ("SCN_ARA_LOD", "SCN_INJ_MAX"):
        for record in tables[name].records():
            if record.get("Schedule"):
                wanted_schedules.add(record["Schedule"])
    filter_table(tables["SCH_ATT"], lambda r: r["Schedule"] in wanted_schedules)
    filter_table(tables["SCH_TMP1"],
                 lambda r: r["Schedule"] in wanted_schedules
                 and r["Time"] in kept_time_set)
    edit_table(tables["SCH_ATT"],
               lambda r: dict(r, RepeatTime=str(TIMEPOINTS)))

    # ----- emit -----
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for name, table in tables.items():
        ec.write_table(table, out_dir / table.filename)

    findings = ec.verify_case(out_dir)
    if ec.has_errors(findings):
        print(ec.format_findings(findings))
        shutil.rmtree(out_dir)
        raise SystemExit(
            "cut_mini7k: the cut fixture does not pass verify_case, so it is "
            "not a valid case and has not been written"
        )
    return out_dir


def main() -> int:
    out_dir = cut()
    tables = ec.read_case(out_dir)
    print(SECTION_SEPARATOR)
    print("cut mini7k fixture -> %s" % out_dir)
    print(SUBSECTION_SEPARATOR)
    for name in sorted(tables):
        print("  %-14s %5d row(s)" % (name, len(tables[name].data_lines)))
    print(SUBSECTION_SEPARATOR)
    print(ec.format_findings(ec.verify_case(out_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
