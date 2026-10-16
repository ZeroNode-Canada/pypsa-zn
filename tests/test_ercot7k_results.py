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

# test_ercot7k_results.py
#
# Purpose
#   Test ercot7k_results.py against the REAL validated PSO run of the shipped
#   ERCOT Texas7k case. No AIMMS seat is needed for any of this: the run is a
#   committed artifact, and reading it is the whole point of the module.
#
#   Concrete numbers are asserted, not shapes. A mapper that returns a
#   plausibly-shaped dict of wrong numbers is the failure mode here, because
#   nothing downstream can tell.
#
# What it does
#   - Asserts the real run's headline figures: 190 MC_Solution rows all
#     Optimal, the RT/DA/SC MC_Hrzn.DeltaCost sums, the pinned RT peak
#     interval, 6717 LMP rows after dropping Reference_*, <= 1171 paths.
#   - Asserts the PF_AraNde.LoadFactor renormalization, which the whole
#     bus_net_import artifact stands on, including the measured raw sum that
#     makes the renormalization necessary.
#   - Asserts the artifact byte format against a hand-built pd.Series and
#     against the committed devnet reference run.
#   - Maps a base run with no manifest and asserts the DC columns are absent.
#   - Builds a synthetic results directory carrying a deliverable-failure
#     datacenter, because the shipped run has no datacenter and therefore
#     cannot exercise the asymptote metric at all.
#   - Asserts determinism: mapping twice is byte-identical.
#
# Outputs
#   - pytest results only. Everything is written under tmp_path.
#
# Run: python -m pytest tests/test_ercot7k_results.py -q
# ------------------------------------------------------------------------------

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ercot7k_case as ec  # noqa: E402
import ercot7k_results as er  # noqa: E402

BASE_DIR = REPO_ROOT / "ercot7k"
MINI_DIR = REPO_ROOT / "tests" / "fixtures" / "mini7k"
REFERENCE_RUN = (REPO_ROOT / "devnet-reference-runs"
                 / "devnetDC-sld-27Aug2026" / "stress_out")

# The complete validated run of the 2018 Texas7k case that ercot7k/ shipped
# until the 2030 WA swap, read-only, and 442 MB, which is why it is not in the
# repo. Everything in this module is measured
# against it rather than against a brief.
#
# Set ERCOT7K_REAL_RESULTS to the results/ directory of your own full-cycle run
# of ercot7k/. Without it these tests SKIP, and a skip is not a pass: the
# module's whole job is checking the mapper against real numbers, so treat a
# skipped run as "not tested" rather than "fine". The default is a sibling
# checkout of the public dataset, which is where it lives on the machine this
# was developed on.
REAL_RESULTS = Path(
    os.environ.get("ERCOT7K_REAL_RESULTS")
    or REPO_ROOT.parent / "ercot-public-dataset" / "pso"
    / "texas7k_fullcycle" / "results"
)

# The case that PRODUCED that run, which is no longer ercot7k/. Since the swap
# to the 2030 WA case, ercot7k/ has different injectors, nodes and dates, and
# pairing it with a 2018 run fails on all three. Every constant below was
# measured on the 2018 run, so the case read beside it must be the 2018 case:
# by default the directory the results sit in. Its cost-curve tables (CCV_*)
# moved after this run was made; nothing here reads them.
REAL_CASE = Path(os.environ.get("ERCOT7K_REAL_CASE") or REAL_RESULTS.parent)

# Measured on the real run, not taken from a brief. Every one of these is a
# number the mapper would happily report wrong.
REAL_SOLVES = 190
REAL_DELTACOST = {"RT": 12008467.056, "DA": 20297189.227, "SC": 11727676.824}
REAL_PEAK_INTERVAL = 184
REAL_PEAK_LOAD_MW = 46794.465

# The peak-CONGESTION interval, which is what pin_interval() now returns, and
# the numbers that make it the pin. All measured on the run below.
#   RT's top binding count of 5 is shared by 101, 102 and 103, so the
#   lmp_spread tie-break decides, and 103 wins it on 7.4545 against 7.1648 and
#   4.0070. Interval 236 has the WIDEST spread of the cycle (12.67) on only 4
#   binding paths, so it is deliberately not the pin -- binding count leads.
REAL_PIN_INTERVAL = {"RT": 103, "DA": 102, "SC": 103}
REAL_PIN_N_BINDING = {"RT": 5, "DA": 6, "SC": 6}
REAL_RT_BINDING_TIE = [101, 102, 103]
REAL_RT_WIDEST_SPREAD_INTERVAL = 236

# Datacenter placement. HEWITT 3 is the import side of N210144_N210332_1, the
# branch that binds in 69 of the 168 RT intervals -- the most persistent of the
# only SEVEN branches that ever bind. BAY CITY 3 was the old template default:
# equally valid, equally clean, and electrically inert.
DEFAULT_DC_NODE = "N210144"
QUIET_CONTROL_NODE = "N110126"
REAL_NODE_COUNT = 6717
REAL_MAX_PATHS = 1171
REAL_REPORTED_INTERVALS = (73, 240)

# PF_AraNde.LoadFactor is documented as normalized to 1. In this run the column
# sums to 1.13204781, because the report quantizes it: values >= 0.001 print as
# "%.3f", so a node whose true share is 0.0015 prints as 0.002. The mapper
# renormalizes; this constant exists so that a change in the quantization is a
# test failure rather than a silent 13% shift in every distributed load.
REAL_LOAD_FACTOR_RAW_SUM = 1.13204781007

pytestmark = pytest.mark.skipif(
    not REAL_RESULTS.is_dir()
    or not (REAL_CASE / "texas7k_MDL_ID.csv").is_file(),
    reason=("no validated PSO run at %s, or no case beside it at %s -- set "
            "ERCOT7K_REAL_RESULTS and ERCOT7K_REAL_CASE. These tests are "
            "SKIPPED, not passed." % (REAL_RESULTS, REAL_CASE)),
)


# ------------------------------------------------------------------------------
#   Fixtures
# ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_key() -> er.ReportKey:
    return er.ReportKey(cycle="RT", scenario="ScnRT",
                        interval=REAL_PEAK_INTERVAL)


@pytest.fixture(scope="module")
def real_run(real_key: er.ReportKey) -> er.MappedRun:
    """One full map of the real run. Module-scoped: it reads 400 MB."""
    return er.map_results(REAL_RESULTS, interval=real_key.interval,
                          cycle=real_key.cycle, scenario=real_key.scenario,
                          case_dir=REAL_CASE)


def read_csv_rows(path: Path) -> list:
    with open(path, newline="") as handle:
        return list(csv.reader(handle))


# ------------------------------------------------------------------------------
#   1. Reader mechanics. Everything else stands on these.
# ------------------------------------------------------------------------------
def test_the_commented_first_header_cell_is_stripped_not_assumed():
    # PSO comment-prefixes the FIRST cell only, and the name behind the "//"
    # differs per table: PC_Nd is "//cyc", MC_Solution is "//slv", PF_AraNde is
    # "//ste". None of them is hardcoded anywhere in the module.
    assert er.result_columns(er.result_path(REAL_RESULTS, "PC_Nd"))[0] == "cyc"
    assert er.result_columns(
        er.result_path(REAL_RESULTS, "MC_Solution"))[0] == "slv"
    assert er.result_columns(
        er.result_path(REAL_RESULTS, "PF_AraNde"))[0] == "ste"
    # and the second cell keeps whatever it had, comment marker or not
    assert er.result_columns(er.result_path(REAL_RESULTS, "PC_Nd"))[1] == "scn"


def test_a_missing_result_table_names_the_file_and_the_likely_cause():
    with pytest.raises(er.Ercot7kResultsError) as excinfo:
        er.require_result(REAL_RESULTS, "NOT_A_TABLE")
    assert "results_NOT_A_TABLE.csv" in str(excinfo.value)


def test_a_blank_field_reads_as_nan_and_never_as_zero():
    # ED_Ara.Violation and ED_Inj.LimitViolation are documented SPARSE fields.
    # A blank is "not reported"; 0.0 would read as "no violation".
    assert math.isnan(er._num(""))
    assert math.isnan(er._num("   "))
    assert er._num("0.000") == 0.0


def test_an_unknown_column_names_the_header():
    path = er.result_path(REAL_RESULTS, "ED_Ara")
    with pytest.raises(er.Ercot7kResultsError) as excinfo:
        er.column_index(er.result_columns(path), "Nonexistent", path)
    assert "Nonexistent" in str(excinfo.value)
    assert "Load" in str(excinfo.value)


# ------------------------------------------------------------------------------
#   2. The real run's headline figures
# ------------------------------------------------------------------------------
def test_the_real_run_reports_190_solves_and_every_one_is_optimal():
    status = er.solution_status(REAL_RESULTS)
    assert status.solves == REAL_SOLVES
    assert status.counts == {"Optimal": REAL_SOLVES}
    assert status.status == "Optimal"


def test_the_objective_is_the_deltacost_sum_per_cycle():
    # MC_Solution.Objective is wrong at 7k: 190 rows, one per solve, and the
    # SC/DA horizons OVERLAP (DA's horizon is 48 h with DeltaTime 24), so
    # neither iloc[0] nor a sum is the run's cost. MC_Hrzn.DeltaCost is the
    # non-overlapping slice.
    got = er.objective_by_cycle(REAL_RESULTS)
    assert set(got) == set(REAL_DELTACOST)
    for cycle, expected in REAL_DELTACOST.items():
        assert got[cycle] == pytest.approx(expected, abs=0.01)


def test_deltacost_and_allcost_differ_for_da_which_is_why_deltacost_is_used():
    # The overlap is not hypothetical. AllCost for DA is 31,244,657.7 against
    # DeltaCost's 20,297,189.2: a 54% over-count if the wrong column is read.
    records = er.read_result_records(er.result_path(REAL_RESULTS, "MC_Hrzn"))
    all_cost = sum(float(r["AllCost"]) for r in records if r["cyc"] == "DA")
    assert all_cost == pytest.approx(31244657.732, abs=0.01)
    assert all_cost > REAL_DELTACOST["DA"] * 1.5
    # RT has DeltaTime 1 and no lookahead, so its two columns agree.
    rt_all = sum(float(r["AllCost"]) for r in records if r["cyc"] == "RT")
    assert rt_all == pytest.approx(REAL_DELTACOST["RT"], abs=0.01)


def test_the_pinned_interval_is_the_rt_peak_congestion_interval():
    assert er.scenario_for_cycle(REAL_RESULTS, "RT") == "ScnRT"
    interval = er.pin_interval(REAL_RESULTS, "RT")
    assert interval == REAL_PIN_INTERVAL["RT"]

    key = er.ReportKey("RT", "ScnRT", interval)
    paths = er.scan_paths(REAL_RESULTS, key)
    assert paths.n_binding[interval] == REAL_PIN_N_BINDING["RT"]
    assert paths.n_binding[interval] == max(paths.n_binding.values())


def test_the_pin_is_not_the_peak_load_interval_because_that_hour_is_idle():
    """
    The whole reason the rule changed. At the peak LOAD hour the shipped case
    is uncongested, so a metric pinned there starts at zero and a stress lever
    has to invent congestion before it reads anything.
    """
    loads = er.area_load_by_interval(REAL_RESULTS, "RT", "ScnRT")
    peak = min(i for i, v in loads.items() if v == max(loads.values()))
    assert peak == REAL_PEAK_INTERVAL
    assert loads[peak] == pytest.approx(REAL_PEAK_LOAD_MW, abs=0.001)

    pinned = er.pin_interval(REAL_RESULTS, "RT")
    assert pinned != peak

    paths = er.scan_paths(REAL_RESULTS, er.ReportKey("RT", "ScnRT", peak))
    assert paths.n_binding[peak] == 0
    assert paths.n_binding[pinned] > 0
    # ... and the pinned hour carries less load than the peak, by design.
    assert loads[pinned] < loads[peak]


def test_ed_inj_max_echoes_the_nameplate_of_an_uncapped_thermal_unit():
    """
    The premise of the k_gen derate witness, measured rather than assumed.
    ED_Inj.md says Max is "de-rated by ... dispatch limits (SCN_INJ_MAX)", so
    on an uncapped unit it must read the nameplate back -- which is what makes
    a capped one's reading an echo of the case file rather than a response.

    N210336_1 is TEMPLE 7 2, 312 MW, no SCN_INJ_MAX row, committed in all 168
    RT intervals of this run.
    """
    limits = er.injector_limit_by_interval(REAL_RESULTS, "RT", "ScnRT",
                                           "N210336_1")
    assert len(limits) == 168
    assert {round(v["max_mw"], 3) for v in limits.values()} == {312.0}
    at_pin = limits[REAL_PIN_INTERVAL["RT"]]
    assert at_pin["cap_mw"] == pytest.approx(312.0)
    assert at_pin["p_mw"] <= at_pin["max_mw"]
    assert at_pin["limit_violation_mw"] == pytest.approx(0.0)


def test_ed_inj_max_follows_the_schedule_of_a_renewable_and_reaches_zero():
    """
    The other population, and the reason its mode is proportional rather than
    absolute: what the results echo is the schedule, so the level is known only
    up to the factor. N220149_1 is King Mountain Wind Ranch 1: 278 MW of
    nameplate, 134 distinct Max values over the window, and 6 hours at zero.
    """
    limits = er.injector_limit_by_interval(REAL_RESULTS, "RT", "ScnRT",
                                           "N220149_1")
    assert len({round(v["max_mw"], 3) for v in limits.values()}) > 100
    assert all(v["cap_mw"] == pytest.approx(278.0) for v in limits.values())
    assert any(v["max_mw"] == 0.0 for v in limits.values())


def test_ed_inj_max_is_zero_for_a_unit_the_solve_did_not_commit():
    """
    Measured, and it is why read_witness() refuses to report a zero Max as a
    witness. N111180_1 is 746 MW of nameplate reading Max=0 in 125 of 168 RT
    intervals -- the pinned one included -- because ED_Inj.md sets Max to zero
    when a unit is "unavailable for commitment". Read as a number, a derate
    sweep on this unit would be constant at zero across every step and W2
    would report the sweep as never having happened.
    """
    limits = er.injector_limit_by_interval(REAL_RESULTS, "RT", "ScnRT",
                                           "N111180_1")
    assert limits[REAL_PIN_INTERVAL["RT"]]["max_mw"] == 0.0
    assert limits[REAL_PIN_INTERVAL["RT"]]["cap_mw"] == pytest.approx(746.0)
    assert sum(1 for v in limits.values() if v["max_mw"] == 0.0) > 100


def test_an_injector_absent_from_the_results_is_absent_from_the_mapping():
    assert er.injector_limit_by_interval(REAL_RESULTS, "RT", "ScnRT",
                                         "NOT_AN_INJECTOR") == {}


def test_the_binding_count_leads_and_the_spread_only_breaks_ties():
    """
    Binding count is the primary key, so the widest-spread interval of the
    cycle is NOT the pin: 236 spreads 12.67 on 4 paths and loses to 5 paths.
    The tie-break is still load-bearing -- RT's top count of 5 is a three-way
    tie -- so both halves of the rule are asserted here.
    """
    key = er.ReportKey("RT", "ScnRT", REAL_PIN_INTERVAL["RT"])
    paths = er.scan_paths(REAL_RESULTS, key)
    most = max(paths.n_binding.values())
    tied = sorted(i for i, n in paths.n_binding.items() if n == most)
    assert tied == REAL_RT_BINDING_TIE

    widest = REAL_RT_WIDEST_SPREAD_INTERVAL
    assert paths.n_binding[widest] < most
    assert er.pin_interval(REAL_RESULTS, "RT") != widest

    # The tie is broken on spread, not on the lowest interval.
    percentiles = er.scan_nodes(REAL_RESULTS, key).percentiles
    spreads = {i: percentiles[i]["spread_p95_p05"] for i in tied}
    assert max(spreads, key=lambda i: spreads[i]) == REAL_PIN_INTERVAL["RT"]
    assert REAL_PIN_INTERVAL["RT"] != min(tied)
    assert percentiles[widest]["spread_p95_p05"] > max(spreads.values())


def test_a_case_where_nothing_binds_refuses_to_pin(monkeypatch):
    """An uncongested case has no peak-congestion hour; it must say so."""
    empty = er.PathScan(n_binding={i: 0 for i in range(73, 241)})
    monkeypatch.setattr(er, "scan_paths", lambda *a, **k: empty)
    with pytest.raises(er.Ercot7kResultsError, match="no path binds"):
        er.pin_interval(REAL_RESULTS, "RT")


def test_the_reported_cycle_covers_168_contiguous_intervals():
    loads = er.area_load_by_interval(REAL_RESULTS, "RT", "ScnRT")
    low, high = REAL_REPORTED_INTERVALS
    assert sorted(loads) == list(range(low, high + 1))
    assert len(loads) == 168


def test_pinning_is_deterministic_across_repeated_calls():
    assert er.pin_interval(REAL_RESULTS, "RT") == er.pin_interval(
        REAL_RESULTS, "RT")


def test_each_cycle_pins_its_own_interval_and_scenario():
    for cycle, scenario in (("SC", "ScnSC"), ("DA", "ScnDA")):
        assert er.scenario_for_cycle(REAL_RESULTS, cycle) == scenario
        interval = er.pin_interval(REAL_RESULTS, cycle)
        assert REAL_REPORTED_INTERVALS[0] <= interval <= (
            REAL_REPORTED_INTERVALS[1])


# ------------------------------------------------------------------------------
#   3. The load distribution, which bus_net_import stands on entirely
# ------------------------------------------------------------------------------
def test_the_load_factor_column_does_not_sum_to_one_and_is_renormalized():
    # Documented as normalized to 1; MEASURED at 1.13204781 because the report
    # quantizes the column. Trust the file: assert what it says, and assert
    # that the mapper corrects it rather than distributing 13% too much load.
    distribution = er.load_distribution(REAL_RESULTS)
    assert distribution.areas() == ["0"]
    assert distribution.raw_sum("0") == pytest.approx(
        REAL_LOAD_FACTOR_RAW_SUM, abs=1e-8)
    assert distribution.raw_sum("0") > 1.13, (
        "if this column ever does sum to 1.0, the renormalization becomes a "
        "no-op and this test should be deleted, not loosened"
    )
    normalized = distribution.normalized("0")
    assert sum(normalized.values()) == pytest.approx(1.0, abs=1e-12)
    assert len(normalized) == 4548


def test_every_load_node_is_a_reported_node():
    # A load node absent from PC_Nd would be load the LMP artifact cannot
    # price, and bus_net_import would append a node that no other artifact has.
    distribution = er.load_distribution(REAL_RESULTS)
    reported = set(er.scan_nodes(
        REAL_RESULTS,
        er.ReportKey("RT", "ScnRT", REAL_PEAK_INTERVAL)).lmp)
    assert set(distribution.nodes()) <= reported


def test_a_load_distribution_that_sums_to_zero_is_refused_not_divided_by():
    distribution = er.LoadDistribution(raw={"0": {"N1": 0.0}})
    with pytest.raises(er.Ercot7kResultsError):
        distribution.normalized("0")


# ------------------------------------------------------------------------------
#   4. The streaming scans
# ------------------------------------------------------------------------------
def test_the_node_scan_drops_the_reference_nodes_and_keeps_6717(
        real_key: er.ReportKey):
    scan = er.scan_nodes(REAL_RESULTS, real_key)
    assert len(scan.lmp) == REAL_NODE_COUNT
    assert scan.reference_nodes == ["Reference_0", "Reference_N111333"]
    assert not any(node.startswith(er.REFERENCE_NODE_PREFIX)
                   for node in scan.lmp)
    # the chronology pass is the SAME pass, so every reported interval is there
    assert sorted(scan.percentiles) == list(
        range(REAL_REPORTED_INTERVALS[0], REAL_REPORTED_INTERVALS[1] + 1))


def test_the_path_scan_reports_at_most_1171_paths(real_key: er.ReportKey):
    scan = er.scan_paths(REAL_RESULTS, real_key)
    assert 0 < len(scan.loading) <= REAL_MAX_PATHS
    assert len(scan.loading) == REAL_MAX_PATHS


def test_the_injector_scan_matches_the_cases_injector_count(
        real_key: er.ReportKey):
    scan = er.scan_injectors(REAL_RESULTS, real_key)
    injectors = {r["Injector"]
                 for r in ec.read_table(
                     REAL_CASE / "texas7k_INJ_ID.csv").records()}
    assert set(scan.dispatch) == injectors
    assert len(scan.dispatch) == 634


def test_the_scans_refuse_an_interval_that_is_not_reported():
    key = er.ReportKey("RT", "ScnRT", 9999)
    with pytest.raises(er.Ercot7kResultsError):
        er.scan_nodes(REAL_RESULTS, key)
    with pytest.raises(er.Ercot7kResultsError):
        er.scan_injectors(REAL_RESULTS, key)


def test_zero_limit_paths_give_nan_loading_and_never_a_zero():
    # The shipped run has no Max == 0 path, so this is asserted on a synthetic
    # table. A 0.0 here would read as "empty line" instead of "no limit".
    key = er.ReportKey("RT", "ScnRT", 1)
    columns = er.result_columns(er.result_path(REAL_RESULTS, "PN_Pth"))
    row = {name: "0" for name in columns}
    row.update({"cyc": "RT", "scn": "ScnRT", "int": "1", "Mw": "500.000",
                "Min": "-100.000", "Max": "0.000", "Violation": "0.000",
                "Binding": "0", "Penalty": "0.000", "SP": "0.000",
                "SAC": "0"})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "results_PN_Pth.csv"
        path.write_text(
            "//" + ",".join(columns) + "\n"
            + ",".join(row[name] for name in columns) + "\n",
            encoding="ascii", newline="",
        )
        scan = er.scan_paths(Path(tmp), key)
    assert math.isnan(scan.loading["0"])
    assert scan.zero_limit_paths == ["0"]


# ------------------------------------------------------------------------------
#   5. bus_net_import -- the artifact that does not exist in the results
# ------------------------------------------------------------------------------
def test_bus_net_import_conserves_the_areas_load(real_run: er.MappedRun):
    # sum(load - gen) over every node must be zero to within float noise: the
    # renormalized factors distribute exactly ED_Ara.Load, and ED_Inj.P sums to
    # the same number because the base case has no LoadFlag=1 injector.
    values = list(real_run.summary["bus_net_import_mw"].values())
    assert len(values) == REAL_NODE_COUNT
    assert sum(values) == pytest.approx(0.0, abs=1e-6)


def test_bus_net_import_is_positive_at_exactly_the_load_nodes(
        real_run: er.MappedRun):
    net = real_run.summary["bus_net_import_mw"]
    distribution = er.load_distribution(REAL_RESULTS)
    load_nodes = set(distribution.nodes())
    gen_nodes = set(er.injector_node_map(REAL_CASE).values())
    for node in load_nodes - gen_nodes:
        assert net[node] > 0.0, "%s carries load and no generation" % node
    for node in gen_nodes - load_nodes:
        assert net[node] <= 0.0, "%s carries generation and no load" % node


def test_bus_net_import_index_matches_the_lmp_index(real_run: er.MappedRun):
    assert list(real_run.summary["bus_net_import_mw"]) == list(
        real_run.summary["lmp"])


def test_bus_net_import_sign_follows_the_devnet_convention():
    # > 0 imports, < 0 exports; and a LoadFlag=1 injector's negative P ADDS to
    # its node's net import, which is why gen_at_node is a signed sum.
    net = er.bus_net_import(
        area_load={"0": 100.0},
        distribution=er.LoadDistribution(raw={"0": {"A": 0.5, "B": 0.5}}),
        dispatch={"GEN_A": 80.0, "DC_LOAD": -30.0},
        injector_node={"GEN_A": "A", "DC_LOAD": "B"},
        node_order=["A", "B"],
    )
    assert net["A"] == pytest.approx(50.0 - 80.0)
    assert net["B"] == pytest.approx(50.0 + 30.0)


def test_a_node_outside_the_reported_set_is_appended_not_dropped():
    net = er.bus_net_import(
        area_load={"0": 10.0},
        distribution=er.LoadDistribution(raw={"0": {"OFFGRID": 1.0}}),
        dispatch={},
        injector_node={},
        node_order=["A"],
    )
    assert list(net) == ["A", "OFFGRID"]
    assert net["OFFGRID"] == pytest.approx(10.0)


def test_bus_net_import_is_omitted_when_there_is_no_case_directory():
    # It needs INJ_NET to place injectors at nodes. Absent a case it is not
    # approximated; write_outputs already skips an empty mapping.
    run = er.map_results(REAL_RESULTS, interval=REAL_PEAK_INTERVAL,
                         cycle="RT", scenario="ScnRT", case_dir=None)
    assert run.summary["bus_net_import_mw"] == {}
    assert len(run.summary["lmp"]) == REAL_NODE_COUNT
    assert run.summary["datetime"] == ""
    assert run.summary["snapshot"] == "int %d" % REAL_PEAK_INTERVAL


# ------------------------------------------------------------------------------
#   6. The whole map of the real run
# ------------------------------------------------------------------------------
def test_the_mapped_summary_carries_the_collect_results_keys(
        real_run: er.MappedRun):
    # These are exactly lib/devnet_stress_lib.py collect_results' keys, plus
    # status and the reported triple. write_outputs consumes this dict.
    assert set(real_run.summary) == {
        "snapshot", "objective", "total_system_load_mw",
        "generator_dispatch_mw", "bus_net_import_mw", "dc_dispatch_mw",
        "lmp", "line_loading_pu",
        "status", "cycle", "scenario", "interval", "datetime",
    }


def test_the_mapped_summary_carries_the_real_numbers(real_run: er.MappedRun):
    summary = real_run.summary
    assert summary["objective"] == pytest.approx(
        REAL_DELTACOST["RT"], abs=0.01)
    assert summary["total_system_load_mw"] == pytest.approx(
        REAL_PEAK_LOAD_MW, abs=0.001)
    assert summary["status"] == "Optimal"
    assert summary["cycle"] == "RT"
    assert summary["scenario"] == "ScnRT"
    assert summary["interval"] == REAL_PEAK_INTERVAL
    assert len(summary["lmp"]) == REAL_NODE_COUNT
    assert len(summary["line_loading_pu"]) == REAL_MAX_PATHS
    assert len(summary["generator_dispatch_mw"]) == 634


def test_the_interval_datetime_counts_from_mindate_not_startdate(
        real_run: er.MappedRun):
    # MinDate 2018.04.06 00:00 is interval 1, StartDate 2018.04.09 00:00 is 72
    # hours later, and the first reported interval is 73. Interval 184 is
    # therefore 183 hours after MinDate.
    assert real_run.summary["datetime"] == "2018-04-13 15:00"
    clock = er.interval_clock(REAL_CASE)
    assert clock is not None
    assert clock.text(1) == "2018-04-06 00:00"
    assert clock.text(REAL_REPORTED_INTERVALS[0]) == "2018-04-09 00:00"


def test_the_default_datacenter_node_sits_behind_a_binding_constraint():
    """
    The template's node is a study decision, not just a validation one, so the
    reason it was chosen is asserted rather than left in a comment. A node that
    verifies clean but never binds gives a datacenter that is simply served:
    no congestion response, no asymptote, nothing for BYOG to displace. That
    was the old default, and it is the control case here.
    """
    brn = ec.read_table(REAL_CASE / "texas7k_BRN_ID.csv").records()
    nodes = {DEFAULT_DC_NODE, QUIET_CONTROL_NODE}
    touching = {n: [b for b in brn
                    if n in (b["FrEnode"], b["ToEnode"])] for n in nodes}

    # Both are 345 kV and monitored, which is why both verify clean and why a
    # clean verify proves nothing about placement.
    for node, branches in touching.items():
        assert branches, node
        assert all(b["Monitor"] == "1" for b in branches), node
        assert {b["Voltage"] for b in branches} == {"345.000"}, node

    # What separates them: only the study node terminates a branch that binds.
    binding = {r["pth"] for r in er.scan_paths(
        REAL_RESULTS, er.ReportKey("RT", "ScnRT", REAL_PIN_INTERVAL["RT"])
    ).binding}
    study = {b["Branch"] for b in touching[DEFAULT_DC_NODE]}
    quiet = {b["Branch"] for b in touching[QUIET_CONTROL_NODE]}
    assert study & binding, "the default DC node no longer binds anything"
    assert not (quiet & binding)

    # And it is the import-constrained side: dearer here than across the limit.
    lmp = er.scan_nodes(
        REAL_RESULTS, er.ReportKey("RT", "ScnRT", REAL_PIN_INTERVAL["RT"])).lmp
    across = [b for b in touching[DEFAULT_DC_NODE]
              if b["Branch"] in binding][0]
    far = (across["ToEnode"] if across["FrEnode"] == DEFAULT_DC_NODE
           else across["FrEnode"])
    assert lmp[DEFAULT_DC_NODE] > lmp[far]


def test_dispatch_sums_to_the_area_load_because_the_base_has_no_load_injector(
        real_run: er.MappedRun):
    # INJ_ID.LoadFlag is 0 on all 634 base injectors, so ED_Inj.P sums to
    # ED_Ara.Load exactly. This is the sign check the LoadFlag adjustment
    # demands, done once against a number that is known independently.
    total = sum(real_run.summary["generator_dispatch_mw"].values())
    assert total == pytest.approx(REAL_PEAK_LOAD_MW, abs=0.01)
    load_flags = {r["LoadFlag"] for r in ec.read_table(
        REAL_CASE / "texas7k_INJ_ID.csv").records()}
    assert load_flags == {"0"}


def test_a_base_run_has_no_datacenter_and_reports_nan_dc_dispatch(
        real_run: er.MappedRun):
    assert real_run.context is not None
    assert real_run.context.datacenters == []
    assert math.isnan(real_run.summary["dc_dispatch_mw"])


def test_the_map_refuses_an_interval_the_run_does_not_report():
    with pytest.raises(er.Ercot7kResultsError) as excinfo:
        er.map_results(REAL_RESULTS, interval=1, cycle="RT",
                       scenario="ScnRT", case_dir=None)
    assert "73..240" in str(excinfo.value)


# ------------------------------------------------------------------------------
#   7. Chronology and binding
# ------------------------------------------------------------------------------
def test_the_chronology_has_one_row_per_interval_with_the_declared_columns(
        real_run: er.MappedRun):
    rows = real_run.chronology_rows
    assert len(rows) == 168
    assert tuple(rows[0]) == er.CHRONOLOGY_COLUMNS
    assert [r["int"] for r in rows] == list(
        range(REAL_REPORTED_INTERVALS[0], REAL_REPORTED_INTERVALS[1] + 1))


def test_the_chronology_percentiles_are_ordered_and_the_spread_is_p95_minus_p05(
        real_run: er.MappedRun):
    for row in real_run.chronology_rows:
        assert row["lmp_min"] <= row["lmp_p05"] <= row["lmp_p50"]
        assert row["lmp_p50"] <= row["lmp_p95"] <= row["lmp_max"]
        assert row["lmp_spread_p95_p05"] == pytest.approx(
            row["lmp_p95"] - row["lmp_p05"], abs=1e-9)


def test_the_chronology_carries_every_rt_horizon_cost(real_run: er.MappedRun):
    # RT has DeltaTime 1 and 168 horizons, so no interval is blank, and the
    # per-interval costs sum to the cycle objective.
    costs = [r["objective_interval"] for r in real_run.chronology_rows]
    assert all(math.isfinite(c) for c in costs)
    assert sum(costs) == pytest.approx(REAL_DELTACOST["RT"], abs=0.01)


def test_the_chronology_congestion_columns_agree_with_the_pinned_row(
        real_run: er.MappedRun):
    pinned = [r for r in real_run.chronology_rows
              if r["int"] == REAL_PEAK_INTERVAL][0]
    assert pinned["load_mw"] == pytest.approx(REAL_PEAK_LOAD_MW, abs=0.001)
    dash = real_run.dashboard
    assert pinned["lmp_spread_p95_p05"] == pytest.approx(
        dash["lmp_spread_p95_p05"], abs=1e-9)
    assert pinned["n_binding"] == dash["n_binding"]


def test_the_real_run_does_congest_even_though_the_pinned_hour_does_not(
        real_run: er.MappedRun):
    # MEASURED: 94 of the 168 RT intervals carry binding paths, but interval
    # 184 -- the peak LOAD hour -- is not one of them. So on the shipped base
    # case the lmp_spread metric reads 0.000 at the pinned interval. That is
    # the data, not a mapper bug, and the chronology is what makes it visible.
    congested = [r for r in real_run.chronology_rows if r["n_binding"] > 0]
    assert len(congested) == 94
    assert real_run.dashboard["n_binding"] == 0
    assert real_run.dashboard["lmp_spread_p95_p05"] == pytest.approx(0.0)
    assert max(r["lmp_spread_p95_p05"]
               for r in real_run.chronology_rows) > 12.0


def test_binding_rows_are_only_the_binding_ones(real_run: er.MappedRun):
    for row in real_run.binding_rows:
        assert row["loading_pu"] >= 0.0
    # interval 184 binds nothing, so assert on an interval that does
    key = er.ReportKey("RT", "ScnRT", 236)
    scan = er.scan_paths(REAL_RESULTS, key)
    assert scan.n_binding[236] == len(scan.binding) > 0
    for row in scan.binding:
        assert tuple(row) == er.BINDING_COLUMNS
        assert math.isfinite(row["SP"])


# ------------------------------------------------------------------------------
#   8. Artifact byte format
# ------------------------------------------------------------------------------
# update_index_html() and the plot scripts consume artifacts written by
# pd.Series.to_csv. These assert the format against a hand-built Series AND
# against the committed devnet reference run, which is the format of record.
# ------------------------------------------------------------------------------
def test_a_series_artifact_matches_a_hand_built_pandas_series(tmp_path: Path):
    mapping = {"WECC_NW": 58.333333333333336, "PJM_NE": 60.0}
    ours = tmp_path / "ours.csv"
    theirs = tmp_path / "theirs.csv"
    er.write_series_csv(ours, mapping, "lmp")
    pd.Series(mapping, name="lmp").to_csv(theirs)
    assert ours.read_bytes() == theirs.read_bytes()
    assert ours.read_bytes().startswith(b",lmp")


def test_the_series_header_and_float_repr_match_the_reference_run(
        tmp_path: Path):
    reference = REFERENCE_RUN / "c10_baseline_lmp.csv"
    if not reference.is_file():
        pytest.skip("the committed devnet reference run is not present")
        return
    rows = read_csv_rows(reference)
    mapping = {name: float(value) for name, value in rows[1:]}
    ours = tmp_path / "ours.csv"
    er.write_series_csv(ours, mapping, rows[0][1])
    assert ours.read_bytes() == reference.read_bytes()


def test_nan_is_written_blank_and_not_as_the_text_nan(tmp_path: Path):
    path = tmp_path / "loading.csv"
    er.write_series_csv(path, {"L1": math.nan, "L2": 0.5}, "loading_pu")
    assert path.read_bytes().replace(b"\r\n", b"\n") == (
        b",loading_pu\nL1,\nL2,0.5\n"
    )


def test_the_objective_artifact_has_the_reference_runs_unnamed_header(
        tmp_path: Path, real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "t", real_run)
    text = written["objective"].read_bytes().replace(b"\r\n", b"\n")
    assert text.startswith(b",0\nobjective,")
    assert b"total_system_load_mw,46794.465\n" in text


def test_every_declared_artifact_is_written(tmp_path: Path,
                                            real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "base_rt", real_run)
    assert set(written) == {
        "json", "lmp", "line_loading_pu", "generator_dispatch_mw",
        "bus_net_import_mw", "objective", "binding", "deliverability",
        "chronology",
    }
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([
        "base_rt.json", "base_rt_binding.csv", "base_rt_bus_net_import_mw.csv",
        "base_rt_chronology.csv", "base_rt_deliverability.csv",
        "base_rt_generator_dispatch_mw.csv", "base_rt_line_loading_pu.csv",
        "base_rt_lmp.csv", "base_rt_objective.csv",
    ])


def test_the_lmp_artifact_has_6717_rows_after_dropping_the_reference_nodes(
        tmp_path: Path, real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "t", real_run)
    rows = read_csv_rows(written["lmp"])
    assert rows[0] == ["", "lmp"]
    assert len(rows) - 1 == REAL_NODE_COUNT
    assert not any(r[0].startswith("Reference_") for r in rows[1:])


def test_the_line_loading_artifact_has_at_most_1171_rows(
        tmp_path: Path, real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "t", real_run)
    rows = read_csv_rows(written["line_loading_pu"])
    assert rows[0] == ["", "loading_pu"]
    assert 0 < len(rows) - 1 <= REAL_MAX_PATHS


def test_the_json_artifact_round_trips(tmp_path: Path,
                                      real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "t", real_run)
    loaded = json.loads(written["json"].read_text(encoding="ascii"))
    assert loaded["interval"] == REAL_PEAK_INTERVAL
    assert loaded["status"] == "Optimal"
    assert len(loaded["lmp"]) == REAL_NODE_COUNT


def test_mapping_twice_is_byte_identical(tmp_path: Path):
    # Determinism is not decoration: a sweep compares artifacts across runs,
    # and an unstable dict order would show up as a diff in every one of them.
    first = tmp_path / "a"
    second = tmp_path / "b"
    for outdir in (first, second):
        run = er.map_results(REAL_RESULTS, interval=REAL_PEAK_INTERVAL,
                             cycle="RT", scenario="ScnRT", case_dir=REAL_CASE)
        er.write_artifacts(outdir, "t", run)
        (outdir / "dash.md").write_text(er.dashboard_text(run, "t"),
                                        encoding="ascii")
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


# ------------------------------------------------------------------------------
#   9. Deliverability -- the asymptote metric
# ------------------------------------------------------------------------------
def test_a_base_run_maps_with_the_dc_columns_absent(tmp_path: Path,
                                                    real_run: er.MappedRun):
    written = er.write_artifacts(tmp_path, "t", real_run)
    rows = read_csv_rows(written["deliverability"])
    assert rows[0] == ["int", "datetime", "system_violation_mw",
                       "system_penalty_usd"]
    assert len(rows) - 1 == 168
    assert not any("dc_" in name for name in rows[0])


def test_the_base_run_reports_no_system_violation(real_run: er.MappedRun):
    for row in real_run.deliverability_rows:
        assert row["system_violation_mw"] == pytest.approx(0.0)
        assert row["system_penalty_usd"] == pytest.approx(0.0)


def _write_synthetic_results(results_dir: Path, dc_injector: str,
                             byog_injector: str) -> None:
    """
    A two-interval, two-node run carrying an UNDELIVERABLE datacenter.

    The shipped run has no datacenter, so it cannot exercise the asymptote
    metric at all. This fixture is the only place a non-zero
    ED_Inj.LimitViolation exists, which is the entire signal the study is
    built to read.
    """
    results_dir.mkdir(parents=True, exist_ok=True)

    def write(table: str, header: str, lines: list) -> None:
        (results_dir / ("results_%s.csv" % table)).write_text(
            "\n".join(["//" + header] + lines) + "\n",
            encoding="ascii", newline="",
        )

    write("MC_Solution", "slv,cyc,hrzn,Status,Objective",
          ["1,RT,hrzn_1,Optimal,1000.000",
           "2,RT,hrzn_2,Optimal,2000.000"])
    write("MC_Hrzn", "cyc,scn,hrzn,FirstInterval,DeltaCost",
          ["RT,ScnRT,hrzn_1,1,1000.000",
           "RT,ScnRT,hrzn_2,2,2000.000"])
    write("ED_Ara", "cyc,scn,ara,int,Load,Violation,Penalty",
          ["RT,ScnRT,0,1,100.000,0.000,0.000",
           "RT,ScnRT,0,2,200.000,5.000,500.000"])
    write("PF_AraNde", "ste,ara,nde,GenFactor,LoadFactor,ResidualLF",
          ["0,0,NA,0.600,0.600,0.000",
           "0,0,NB,0.600,0.600,0.000"])
    write("PC_Nd", "cyc,scn,nd,int,LMP",
          ["RT,ScnRT,NA,1,20.000", "RT,ScnRT,NA,2,30.000",
           "RT,ScnRT,NB,1,25.000", "RT,ScnRT,NB,2,90.000",
           "RT,ScnRT,Reference_0,1,20.000",
           "RT,ScnRT,Reference_0,2,20.000"])
    write("PN_Pth",
          "cyc,scn,pth,int,Mw,Min,Max,Violation,Binding,Penalty,SP,SAC",
          ["RT,ScnRT,P1,1,50.000,-100.000,100.000,0.000,0,0.000,0.000,0",
           "RT,ScnRT,P1,2,100.000,-100.000,100.000,3.000,1,300.000,17.500,1"])
    header = ("cyc,scn,inj,int,P,Max,Min,LimitViolation,RampViolation,"
              "Penalty")
    write("ED_Inj", header, [
        "RT,ScnRT,GEN_A,1,100.000,500.000,0.000,0.000,0.000,0.000",
        "RT,ScnRT,GEN_A,2,180.000,500.000,0.000,0.000,0.000,0.000",
        "RT,ScnRT,%s,1,-40.000,-40.000,-40.000,0.000,0.000,0.000" % dc_injector,
        "RT,ScnRT,%s,2,-25.000,-40.000,-40.000,-15.000,0.000,7500.000"
        % dc_injector,
        "RT,ScnRT,%s,1,0.000,10.000,0.000,0.000,0.000,0.000" % byog_injector,
        "RT,ScnRT,%s,2,10.000,10.000,0.000,0.000,0.000,0.000" % byog_injector,
    ])


@pytest.fixture
def dc_case(tmp_path: Path) -> Path:
    """A real datacenter layer, so the manifest is a real manifest."""
    base = tmp_path / "mini7k"
    shutil.copytree(MINI_DIR, base)
    out = tmp_path / "mini7k__dc1"
    ec.build_datacenter_layer(
        base, out,
        ec.DatacenterSpec(dc_name="DC1", node="N111179", p_set_mw=40.0,
                          byog_p_nom_mw=10.0, byog_max_mw=10.0,
                          byog_mc=65.0),
    )
    return out


def test_the_dc_injectors_come_from_the_manifest_not_a_prefix_match(
        dc_case: Path):
    datacenters = er.datacenters_from_manifest(dc_case)
    assert len(datacenters) == 1
    assert datacenters[0]["load_injector"] == "DC1_LOAD"
    assert datacenters[0]["byog_injector"] == "DC1_BYOG"
    assert datacenters[0]["node"] == "N111179"


def test_no_manifest_means_no_datacenter_and_not_an_error(tmp_path: Path):
    assert er.datacenters_from_manifest(None) == []
    assert er.datacenters_from_manifest(BASE_DIR) == []
    assert er.datacenters_from_manifest(tmp_path) == []


def test_an_undeliverable_datacenter_reports_its_own_limit_violation(
        tmp_path: Path, dc_case: Path):
    results = tmp_path / "results"
    _write_synthetic_results(results, "DC1_LOAD", "DC1_BYOG")
    run = er.map_results(results, interval=2, cycle="RT", scenario="ScnRT",
                         case_dir=dc_case)

    rows = run.deliverability_rows
    assert len(rows) == 2
    second = rows[1]
    # The DC half: attributed to the DC's OWN injector, not to the system.
    assert second["dc_injector"] == "DC1_LOAD"
    assert second["dc_limit_violation_mw"] == pytest.approx(-15.0)
    assert second["dc_penalty_usd"] == pytest.approx(7500.0)
    assert second["dc_p_mw"] == pytest.approx(-25.0)
    # The system half, side by side, so a run can say which gave way first.
    assert second["system_violation_mw"] == pytest.approx(5.0)
    assert second["system_penalty_usd"] == pytest.approx(500.0)
    # and the BYOG generator is measured too
    assert second["byog_p_mw"] == pytest.approx(10.0)
    assert second["byog_limit_violation_mw"] == pytest.approx(0.0)
    # interval 1 was delivered in full
    assert rows[0]["dc_limit_violation_mw"] == pytest.approx(0.0)
    assert rows[0]["dc_p_mw"] == pytest.approx(-40.0)


def test_the_dc_columns_appear_in_the_written_deliverability_file(
        tmp_path: Path, dc_case: Path):
    results = tmp_path / "results"
    _write_synthetic_results(results, "DC1_LOAD", "DC1_BYOG")
    run = er.map_results(results, interval=2, cycle="RT", scenario="ScnRT",
                         case_dir=dc_case)
    written = er.write_artifacts(tmp_path / "out", "dc1", run)
    rows = read_csv_rows(written["deliverability"])
    assert rows[0] == [
        "int", "datetime", "system_violation_mw", "system_penalty_usd",
        "dc_name", "dc_node",
        "dc_injector", "dc_p_mw", "dc_max_mw", "dc_limit_violation_mw",
        "dc_penalty_usd",
        "byog_injector", "byog_p_mw", "byog_max_mw",
        "byog_limit_violation_mw", "byog_penalty_usd",
    ]
    assert len(rows) - 1 == 2


def test_the_chronology_carries_the_dc_limit_violation_when_there_is_one(
        tmp_path: Path, dc_case: Path):
    results = tmp_path / "results"
    _write_synthetic_results(results, "DC1_LOAD", "DC1_BYOG")
    run = er.map_results(results, interval=2, cycle="RT", scenario="ScnRT",
                         case_dir=dc_case)
    violations = [r["dc_limit_violation_mw"] for r in run.chronology_rows]
    assert violations == [pytest.approx(0.0), pytest.approx(-15.0)]


def test_the_synthetic_run_exercises_the_dc_dispatch_and_lmp_at_the_dc_node(
        tmp_path: Path, dc_case: Path):
    results = tmp_path / "results"
    _write_synthetic_results(results, "DC1_LOAD", "DC1_BYOG")
    run = er.map_results(results, interval=2, cycle="RT", scenario="ScnRT",
                         case_dir=dc_case)
    assert run.summary["dc_dispatch_mw"] == pytest.approx(10.0)
    assert run.summary["objective"] == pytest.approx(3000.0)
    assert run.summary["total_system_load_mw"] == pytest.approx(200.0)
    # a synthetic LoadFactor column that sums to 1.2 is still renormalized
    distribution = er.load_distribution(results)
    assert distribution.raw_sum("0") == pytest.approx(1.2)
    # The DC node carries no synthetic load share, so its net import is the
    # datacenter's un-offset draw: 0 - (BYOG 10 + DC -25) = +15 MW. Note that
    # this synthetic run is DELIBERATELY inconsistent with the mini7k case it
    # is mapped against -- GEN_A is not in mini7k's INJ_NET -- so the
    # conservation identity is asserted on the real run instead, where the
    # results and the case are the same case.
    net = run.summary["bus_net_import_mw"]
    assert net["N111179"] == pytest.approx(15.0)


# ------------------------------------------------------------------------------
#   10. The pin, persisted
# ------------------------------------------------------------------------------
def test_the_pin_round_trips_through_study_json(tmp_path: Path):
    case = tmp_path / "case"
    case.mkdir()
    key = er.ReportKey("RT", "ScnRT", REAL_PEAK_INTERVAL)
    er.write_study(case, key, results_dir=REAL_RESULTS)
    assert er.has_study(case)
    assert er.pinned_report_key(case) == key


def test_re_pinning_is_refused_unless_asked_twice(tmp_path: Path):
    case = tmp_path / "case"
    case.mkdir()
    key = er.ReportKey("RT", "ScnRT", 184)
    er.write_study(case, key)
    with pytest.raises(er.Ercot7kResultsError) as excinfo:
        er.write_study(case, er.ReportKey("RT", "ScnRT", 91))
    assert "184" in str(excinfo.value)
    er.write_study(case, er.ReportKey("RT", "ScnRT", 91), force=True)
    assert er.pinned_report_key(case).interval == 91


def test_a_study_with_the_wrong_schema_is_refused(tmp_path: Path):
    case = tmp_path / "case"
    case.mkdir()
    er.study_path(case).write_bytes(b'{"schema": "something-else"}\n')
    with pytest.raises(er.Ercot7kResultsError):
        er.read_study(case)


def test_a_missing_study_is_named_not_guessed_around(tmp_path: Path):
    with pytest.raises(er.Ercot7kResultsError) as excinfo:
        er.read_study(tmp_path)
    assert er.STUDY_NAME in str(excinfo.value)


# ------------------------------------------------------------------------------
#   11. Dashboard
# ------------------------------------------------------------------------------
# update_index_html() cannot change and scrapes by LINE PREFIX. These tests
# assert against a copy of that scraper's loop, because getting it wrong is
# silent: index.html would just show the wrong number.
# ------------------------------------------------------------------------------
def scrape_like_update_index_html(text: str) -> dict:
    """
    A verbatim copy of the metric loop inside
    lib/devnet_stress_lib.py::update_index_html::_read_commit_metrics.
    That file may not be modified, so its behaviour is mirrored here.
    """
    metrics = {"scenario": "", "objective": "", "lmp_spread": "",
               "max_loading_pu": "", "near_bind_ct": "",
               "k_first_near_bind": "", "lmp_spread_max": ""}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ASR-DASH::"):
            parts = line.split("::")
            if len(parts) >= 4:
                metrics["scenario"] = parts[-1].strip()
        elif line.startswith("objective"):
            if ":" in line:
                metrics["objective"] = line.split(":", 1)[1].strip()
        elif line.startswith("lmp_spread"):
            if ":" in line:
                metrics["lmp_spread"] = line.split(":", 1)[1].strip().split()[0]
        elif line.startswith("max_loading_pu"):
            if ":" in line:
                metrics["max_loading_pu"] = (
                    line.split(":", 1)[1].strip().split()[0])
        elif line.startswith("near_bind_ct"):
            if ":" in line:
                metrics["near_bind_ct"] = line.split(":", 1)[1].strip()
        elif line.startswith("first_near_bind_k"):
            if ":" in line:
                metrics["k_first_near_bind"] = line.split(":", 1)[1].strip()
        elif line.startswith("lmp_spread_max"):
            if ":" in line:
                metrics["lmp_spread_max"] = line.split(":", 1)[1].strip()
    return metrics


def test_exactly_one_dashboard_line_starts_with_lmp_spread_and_it_is_first(
        real_run: er.MappedRun):
    lines = [line.strip() for line in
             er.dashboard_text(real_run, "t").splitlines()]
    spread = [i for i, line in enumerate(lines)
              if line.startswith("lmp_spread")]
    assert len(spread) == 1, (
        "the scraper overwrites m['lmp_spread'] on every prefix match, so a "
        "second lmp_spread* line would decide the value by position"
    )
    maxmin = [i for i, line in enumerate(lines)
              if line.startswith("lmp_maxmin")]
    assert len(maxmin) == 1
    assert spread[0] < maxmin[0]


def test_the_scraped_lmp_spread_is_p95_minus_p05(real_run: er.MappedRun):
    scraped = scrape_like_update_index_html(er.dashboard_text(real_run, "t"))
    expected = real_run.dashboard["lmp_spread_p95_p05"]
    assert float(scraped["lmp_spread"]) == pytest.approx(expected, abs=0.001)


def test_the_maxmin_spread_is_still_emitted_and_labelled(
        real_run: er.MappedRun):
    text = er.dashboard_text(real_run, "t")
    line = [row for row in text.splitlines()
            if row.startswith("lmp_maxmin")][0]
    assert "lmp_spread_maxmin" in line
    assert "max_lmp" in line


def test_the_asr_dash_line_carries_the_four_segments_the_scraper_needs(
        real_run: er.MappedRun):
    # The scraper reads the scenario column as parts[-1] and only when
    # len(parts) >= 4. "ASR-DASH::MAP::t" is three parts and would scrape as an
    # empty scenario, so the default mode carries its own sub-segment.
    line = [row for row in er.dashboard_text(real_run, "t").splitlines()
            if row.startswith("ASR-DASH::")][0]
    assert line == "ASR-DASH::MAP::RT::t"
    assert len(line.split("::")) == 4
    explicit = er.dashboard_text(real_run, "t", mode="COMMIT::c3")
    assert "ASR-DASH::COMMIT::c3::t" in explicit


def test_the_scraper_finds_the_objective_and_the_loading_and_the_bind_count(
        real_run: er.MappedRun):
    scraped = scrape_like_update_index_html(er.dashboard_text(real_run, "t"))
    assert scraped["scenario"] == "t"
    assert scraped["objective"].startswith("1.201e+07")
    assert float(scraped["max_loading_pu"]) == pytest.approx(
        real_run.dashboard["max_loading_pu"], abs=0.001)
    assert int(scraped["near_bind_ct"]) == real_run.dashboard["near_bind_ct"]


def test_no_other_dashboard_line_collides_with_a_scraped_prefix(
        real_run: er.MappedRun):
    lines = [line.strip() for line in
             er.dashboard_text(real_run, "t").splitlines()]
    for prefix in ("objective", "max_loading_pu", "near_bind_ct",
                   "first_near_bind_k"):
        assert sum(1 for line in lines if line.startswith(prefix)) <= 1, prefix


def test_every_listing_is_capped_at_ten_with_a_footer_naming_the_csv(
        real_run: er.MappedRun):
    text = er.dashboard_text(real_run, "t")
    lines = text.splitlines()
    assert len(lines) < 80, (
        "uncapped, a 6717-bus dashboard is a 7000-line <pre> block"
    )
    for artifact, remaining in (("t_generator_dispatch_mw.csv", 634 - 10),
                                ("t_bus_net_import_mw.csv",
                                 REAL_NODE_COUNT - 10),
                                ("t_line_loading_pu.csv",
                                 REAL_MAX_PATHS - 10)):
        assert "... %d more, see %s" % (remaining, artifact) in text
    for block in ("generator_dispatch_mw:",
                  "bus_import_export_mw (+IMPORT / -EXPORT):",
                  "top_lines:"):
        start = lines.index(block)
        listed = [row for row in lines[start + 1:start + 11]
                  if row.startswith("  ") and "more, see" not in row]
        assert len(listed) == er.DASHBOARD_TOP_N


def test_the_dashboard_reports_the_pinned_triple_and_the_datetime(
        real_run: er.MappedRun):
    text = er.dashboard_text(real_run, "t")
    assert ("report           : cycle=RT  scenario=ScnRT  interval=184  "
            "datetime=2018-04-13 15:00") in text
    assert "solver           : Optimal  (190 solves: Optimal=190)" in text
    assert "nodes_reported   : 6717" in text


def test_the_dashboard_says_a_base_run_has_no_datacenter(
        real_run: er.MappedRun):
    text = er.dashboard_text(real_run, "t")
    assert "no datacenter in the case manifest" in text
    assert "sys_violation    :" in text


def test_the_dashboard_reports_the_dc_node_lmp_and_deliverability(
        tmp_path: Path, dc_case: Path):
    results = tmp_path / "results"
    _write_synthetic_results(results, "DC1_LOAD", "DC1_BYOG")
    run = er.map_results(results, interval=2, cycle="RT", scenario="ScnRT",
                         case_dir=dc_case)
    text = er.dashboard_text(run, "dc1")
    assert "dc_node_lmp      :" in text
    assert "N111179" in text
    assert "dc_deliverability: DC1_LOAD" in text
    assert "LimitViolation -15.000 MW" in text
    assert "byog_dispatch    : DC1_BYOG" in text
    assert "no datacenter" not in text


def test_the_dashboard_surfaces_the_load_factor_quantization(
        real_run: er.MappedRun):
    # The renormalization must stay VISIBLE. A silently absorbed 13% is the
    # thing this line exists to prevent.
    text = er.dashboard_text(real_run, "t")
    assert "load_factor_sum  : area 0 raw 1.132048" in text
    assert "renormalized to 1.0" in text


def test_the_dashboard_is_plain_ascii(real_run: er.MappedRun):
    text = er.dashboard_text(real_run, "t")
    assert text.isascii()
    text.encode("ascii")


# ------------------------------------------------------------------------------
#   12. The module is importable-only, and the CLI still works
# ------------------------------------------------------------------------------
def test_the_module_source_is_plain_ascii():
    assert (REPO_ROOT / "ercot7k_results.py").read_bytes().decode("ascii")


def test_importing_the_module_prints_nothing_and_creates_nothing(capsys):
    import importlib
    importlib.reload(er)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_the_cli_pins_into_the_cases_study_json_and_maps_from_it(
        tmp_path: Path, capsys):
    # study.json lives next to the case, which is what makes the pin travel
    # with the case rather than with whoever typed the command.
    # Inputs only: the case directory also holds the run's results/ (400 MB),
    # and a study.json already in it would refuse the pin under test.
    case = tmp_path / "ercot7k"
    case.mkdir()
    for path in ec.case_files(REAL_CASE):
        if path.name != er.study_path(REAL_CASE).name:
            shutil.copy2(path, case / path.name)

    assert er.main(["pin", str(REAL_RESULTS), "--case-dir", str(case)]) == 0
    out = capsys.readouterr().out
    assert "interval : %d" % REAL_PIN_INTERVAL["RT"] in out
    assert er.pinned_report_key(case).interval == REAL_PIN_INTERVAL["RT"]

    # The rule that produced the pin travels with it, so a study read years
    # later says which interval it means and why that one.
    assert "binding" in er.read_study(case)["pin_rule"]

    outdir = tmp_path / "out"
    assert er.main(["map", str(REAL_RESULTS), str(outdir), "t",
                    "--case-dir", str(case)]) == 0
    rows = read_csv_rows(outdir / "t_lmp.csv")
    assert len(rows) - 1 == REAL_NODE_COUNT
    assert "interval=%d" % REAL_PIN_INTERVAL["RT"] in capsys.readouterr().out


def test_the_cli_refuses_to_guess_the_interval(tmp_path: Path, capsys):
    assert er.main(["map", str(REAL_RESULTS), str(tmp_path / "o"), "t"]) == 2
    assert "must be pinned by the study" in capsys.readouterr().err
