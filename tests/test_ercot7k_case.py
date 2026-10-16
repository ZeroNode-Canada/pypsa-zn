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

# test_ercot7k_case.py
#
# Purpose
#   Test ercot7k_case.py. Every negative test below corresponds to one SILENT
#   failure: a case that PSO reads without complaint, solves to optimality and
#   reports normally, while modelling something other than what was asked for.
#   Each asserts a raise, because a warning nobody reads is the failure mode.
#
# What it does
#   - Round-trips all 24 files of the real ercot7k/ case and asserts the bytes
#     are identical. Everything else stands on this.
#   - Builds two-layer chains on the mini7k fixture, tampers a parent, and
#     asserts the hash chain catches it.
#   - Builds a real datacenter layer off ercot7k/ and runs the full V1-V13.
#   - Asserts verify_case() passes clean on ercot7k/ itself. If the base fails
#     its own checks, the checks are wrong.
#
# Outputs
#   - pytest results only. Every layer is written under tmp_path.
#
# Run: python -m pytest tests/test_ercot7k_case.py -q
# ------------------------------------------------------------------------------

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ercot7k_case as ec  # noqa: E402

BASE_DIR = REPO_ROOT / "ercot7k"
MINI_DIR = REPO_ROOT / "tests" / "fixtures" / "mini7k"

# Nodes in the mini7k fixture. MONITORED_NODE is an endpoint of a Monitor=1
# branch; UNMONITORED_NODE is touched only by Monitor=0 branches, which is what
# V8 is looking for.
MONITORED_NODE = "N111179"
UNMONITORED_NODE = "N110001"

MINI_TIMEPOINTS = 12


# ------------------------------------------------------------------------------
#   Fixtures
# ------------------------------------------------------------------------------
@pytest.fixture
def mini_base(tmp_path: Path) -> Path:
    """A writable copy of mini7k, so a test may tamper with its parent."""
    target = tmp_path / "mini7k"
    shutil.copytree(MINI_DIR, target)
    return target


def mini_spec(node: str = MONITORED_NODE, **overrides) -> ec.DatacenterSpec:
    values = dict(dc_name="DC1", node=node, p_set_mw=100.0,
                  byog_p_nom_mw=50.0, byog_max_mw=50.0, byog_mc=65.0)
    values.update(overrides)
    return ec.DatacenterSpec(**values)


# ------------------------------------------------------------------------------
#   1. Byte-fidelity I/O. Nothing else in this module means anything if these
#      fail, so they come first.
# ------------------------------------------------------------------------------
def test_round_trip_of_the_real_case_is_byte_identical():
    files = ec.case_csv_files(BASE_DIR)
    assert len(files) == 29, "the ercot7k case is 29 CSV files"
    for path in files:
        table = ec.read_table(path)
        assert table.to_bytes() == path.read_bytes(), path.name


def test_pso_run_artifacts_are_not_case_inputs(mini_base: Path):
    """
    Solving a case leaves files in its *input* directory. They must not be read
    back as tables: SCH_TMP1X is a filtered copy of SCH_TMP1 restricted to the
    solved window, so propagating it into a derived layer would ship a
    truncated schedule under a table name PSO never asked for.
    """
    before = ec.case_csv_files(mini_base)

    # Exactly what a real run leaves behind, names taken from PSO's own
    # construction: <root>.status and <root>_SCH_TMP<n>X.csv.
    (mini_base / "texas7k.status").write_bytes(b"runlog copy\n")
    (mini_base / "texas7k_SCH_TMP1X.csv").write_bytes(
        (mini_base / "texas7k_SCH_TMP1.csv").read_bytes()
    )

    assert ec.case_csv_files(mini_base) == before
    assert "SCH_TMP1X" not in ec.read_case(mini_base)
    assert not any(p.name.endswith(".status")
                   for p in ec.case_files(mini_base))

    # The guard is the trailing X, so the real input must still be a case file.
    assert "SCH_TMP1" in ec.read_case(mini_base)
    assert ec.is_run_artifact("texas7k_SCH_TMP1X.csv")
    assert ec.is_run_artifact("texas7k_SCH_TMPX.csv")   # the unnumbered form
    assert not ec.is_run_artifact("texas7k_SCH_TMP1.csv")
    assert not ec.is_run_artifact("texas7k_SCN_INJ_MAX.csv")  # ends in X.csv


def test_round_trip_through_the_filesystem_is_byte_identical(tmp_path: Path):
    for path in ec.case_csv_files(BASE_DIR):
        target = tmp_path / path.name
        ec.write_table(ec.read_table(path), target)
        assert target.read_bytes() == path.read_bytes(), path.name


def test_field_text_is_never_reserialized():
    """295.000 must not become 295.0, on any of 1063 rows."""
    table = ec.read_table(BASE_DIR / "texas7k_INJ_ID.csv")
    records = table.records()
    assert records[0]["MaxMw"] == "295.000"
    assert records[0]["MinMw"] == "0.000"
    assert records[0]["RaiseRR"] == "8.850"
    net = ec.read_table(BASE_DIR / "texas7k_INJ_NET.csv")
    assert net.records()[0]["LossFactor"] == "0.00000000"


def test_schema_is_introspected_from_the_file_not_hardcoded():
    table = ec.read_table(BASE_DIR / "texas7k_INJ_ID.csv")
    assert table.columns[0] == "Injector"
    assert table.columns.index("Area") == 2
    assert len(table.columns) == 15


def test_a_crlf_file_keeps_its_crlf(tmp_path: Path):
    """
    A CRLF file must round-trip as CRLF. The 2018 case shipped one (CYC_SAI);
    the 2030 WA case is all LF, so the file is built here rather than found.
    """
    path = tmp_path / "texas7k_CYC_SAI.csv"
    raw = (b"Cycle,PriorCycle,RunAnalysis\r\n"
           b"SC,,1\r\n"
           b"DA,SC,1\r\n")
    path.write_bytes(raw)
    assert ec.read_table(path).to_bytes() == raw
    target = tmp_path / "copy.csv"
    ec.write_table(ec.read_table(path), target)
    assert target.read_bytes() == raw


def test_reading_a_non_ascii_file_is_refused(tmp_path: Path):
    path = tmp_path / "texas7k_X.csv"
    # The two bytes are UTF-8 for e-acute, written as an escape so this file
    # itself stays plain ASCII.
    path.write_bytes(b"A,B\n1,\xc3\xa9\n")
    with pytest.raises(ec.ByteFidelityError):
        ec.read_table(path)


def test_reading_a_bom_is_refused(tmp_path: Path):
    path = tmp_path / "texas7k_X.csv"
    path.write_bytes(b"\xef\xbb\xbfA,B\n1,2\n")
    with pytest.raises(ec.ByteFidelityError):
        ec.read_table(path)


# ------------------------------------------------------------------------------
#   2. Manifest, hashing and the chain walk
# ------------------------------------------------------------------------------
def test_a_two_layer_chain_walks_back_to_the_base(mini_base: Path,
                                                  tmp_path: Path):
    layer1 = tmp_path / ec.layer_dir_name(mini_base, "dc1")
    ec.build_datacenter_layer(mini_base, layer1, mini_spec())
    layer2 = tmp_path / ec.layer_dir_name(layer1, "dc2")
    ec.build_datacenter_layer(layer2.parent / layer1.name, layer2,
                              mini_spec(dc_name="DC2"))

    chain = ec.walk_chain(layer2)
    assert [c.kind for c in chain] == ["base", "layer", "layer"]
    assert chain[0].path == mini_base.resolve()
    assert chain[-1].path == layer2.resolve()


def test_a_hand_edited_parent_layer_is_caught_by_its_own_hash(mini_base: Path,
                                                             tmp_path: Path):
    layer1 = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer1, mini_spec())
    ec.walk_chain(layer1)  # clean before the edit

    target = layer1 / "texas7k_INJ_ID.csv"
    target.write_bytes(target.read_bytes().replace(b"100.000", b"900.000"))

    with pytest.raises(ec.ChainIntegrityError):
        ec.walk_chain(layer1)
    with pytest.raises(ec.ChainIntegrityError):
        ec.build_datacenter_layer(layer1, tmp_path / "layer2",
                                  mini_spec(dc_name="DC2"))


def test_a_hand_edited_base_is_caught_by_the_childs_parent_hash(
        mini_base: Path, tmp_path: Path):
    layer1 = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer1, mini_spec())

    target = mini_base / "texas7k_INJ_ID.csv"
    target.write_bytes(target.read_bytes().replace(b"746.000", b"747.000"))

    with pytest.raises(ec.ChainIntegrityError):
        ec.walk_chain(layer1)


def test_the_manifest_records_what_the_layer_owns(mini_base: Path,
                                                  tmp_path: Path):
    layer = tmp_path / "layer1"
    manifest = ec.build_datacenter_layer(mini_base, layer, mini_spec())

    assert manifest["schema"] == ec.MANIFEST_SCHEMA
    assert manifest["parent"]["kind"] == "base"
    assert manifest["parent"]["path"] == str(mini_base.resolve())
    assert manifest["self_sha256"] == ec.case_digest(layer)

    owned = {(e["table"], tuple(e["key"])) for e in manifest["owned"]}
    assert ("INJ_ID", ("DC1_LOAD",)) in owned
    assert ("INJ_ID", ("DC1_BYOG",)) in owned
    assert ("INJ_NET", ("DC1_LOAD",)) in owned
    for scenario in ("ScnSC", "ScnDA", "ScnRT"):
        assert ("SCN_INJ_DSP", (scenario, "DC1_LOAD")) in owned

    assert manifest["owned_files"] == ["texas7k_SCN_INJ_DSP.csv"]
    assert manifest["capacity_ceilings"]["DC1_BYOG"] == 50.0
    assert {o["table"] for o in manifest["deliberate_omissions"]} == {
        "INJ_CMT", "CYC_INJ_CCV", "RSV_INJ", "STE_NDE"}
    # The manifest is read back from disk as ASCII JSON, not just returned.
    on_disk = ec.read_manifest(layer)
    assert on_disk["layer_id"] == manifest["layer_id"]
    assert json.dumps(on_disk).isascii()


def test_a_manifest_is_written_once_and_never_edited(mini_base: Path,
                                                     tmp_path: Path):
    layer = tmp_path / "layer1"
    manifest = ec.build_datacenter_layer(mini_base, layer, mini_spec())
    with pytest.raises(ec.Ercot7kCaseError):
        ec.write_manifest(layer, manifest)


# ------------------------------------------------------------------------------
#   3. AddInjector, AddSchedule and the numbered SCH_TMP sibling
# ------------------------------------------------------------------------------
def test_a_datacenter_layer_leaves_every_untouched_file_byte_identical(
        mini_base: Path, tmp_path: Path):
    layer = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer, mini_spec())

    changed = {"texas7k_INJ_ID.csv", "texas7k_INJ_NET.csv"}
    new = {"texas7k_SCN_INJ_DSP.csv"}
    for path in ec.case_files(mini_base):
        target = layer / path.name
        if path.name in changed:
            assert target.read_bytes().startswith(path.read_bytes()), path.name
        else:
            assert target.read_bytes() == path.read_bytes(), path.name
    assert {p.name for p in ec.case_files(layer)} == (
        {p.name for p in ec.case_files(mini_base)} | new)


def test_the_new_injector_rows_carry_a_blank_area(mini_base: Path,
                                                  tmp_path: Path):
    layer = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer, mini_spec())
    records = ec.read_table(layer / "texas7k_INJ_ID.csv").records()
    added = {r["Injector"]: r for r in records
             if r["Injector"].startswith("DC1_")}
    assert set(added) == {"DC1_LOAD", "DC1_BYOG"}
    for record in added.values():
        assert record["Area"] == "", "Area must be blank, never 0"
    assert added["DC1_LOAD"]["LoadFlag"] == "1"
    assert added["DC1_LOAD"]["MaxMw"] == "100.000"
    assert added["DC1_BYOG"]["LoadFlag"] == "0"
    assert added["DC1_BYOG"]["EnergyCost"] == "65.000"


def test_add_schedule_writes_a_new_numbered_sch_tmp_sibling(mini_base: Path,
                                                            tmp_path: Path):
    layer = tmp_path / "layer1"
    values = tuple(float(i) for i in range(MINI_TIMEPOINTS))
    deltas = [ec.AddSchedule("DC1_shape", values, repeat_time=MINI_TIMEPOINTS)]
    manifest = ec.write_layer(mini_base, layer, deltas, slug="sched")

    sibling = layer / "texas7k_SCH_TMP2.csv"
    assert sibling.is_file()
    assert manifest["owned_files"] == ["texas7k_SCH_TMP2.csv"]
    # SCH_TMP1 is copied byte-identical and never parsed for content.
    assert (layer / "texas7k_SCH_TMP1.csv").read_bytes() == (
        (mini_base / "texas7k_SCH_TMP1.csv").read_bytes())
    # The sibling's header IS the original's header.
    assert sibling.read_bytes().split(b"\n")[0] == (
        (mini_base / "texas7k_SCH_TMP1.csv").read_bytes().split(b"\n")[0])

    rows = ec.read_table(sibling).records()
    assert len(rows) == MINI_TIMEPOINTS
    assert rows[0]["Time"] == "2018.04.06 00:00"
    assert rows[-1]["Time"] == "2018.04.06 11:00"
    assert all(r["Enforce"] == "1" for r in rows)
    assert not ec.has_errors(ec.verify_case(layer))


def test_a_third_layer_takes_sch_tmp3(mini_base: Path, tmp_path: Path):
    values = tuple(1.0 for _ in range(MINI_TIMEPOINTS))
    layer1 = tmp_path / "l1"
    ec.write_layer(mini_base, layer1,
                   [ec.AddSchedule("S1", values, repeat_time=MINI_TIMEPOINTS)],
                   slug="s1")
    layer2 = tmp_path / "l2"
    ec.write_layer(layer1, layer2,
                   [ec.AddSchedule("S2", values, repeat_time=MINI_TIMEPOINTS)],
                   slug="s2")
    assert (layer2 / "texas7k_SCH_TMP3.csv").is_file()
    assert (layer2 / "texas7k_SCH_TMP2.csv").read_bytes() == (
        (layer1 / "texas7k_SCH_TMP2.csv").read_bytes())


# ------------------------------------------------------------------------------
#   4. ScenarioOverride on SCN_INJ_DSP
# ------------------------------------------------------------------------------
def test_scn_inj_dsp_gets_one_row_per_named_scenario(mini_base: Path,
                                                     tmp_path: Path):
    layer = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer, mini_spec())
    table = ec.read_table(layer / "texas7k_SCN_INJ_DSP.csv")
    assert table.columns == list(ec.NEW_TABLE_COLUMNS["SCN_INJ_DSP"])
    rows = table.records()
    assert [r["Scenario"] for r in rows] == ["ScnSC", "ScnDA", "ScnRT"]
    for record in rows:
        assert record["Injector"] == "DC1_LOAD"
        assert record["Dispatch"] == "100.000"
        # Enforce is narrow: it means "Dispatch = 0 should be enforced". A
        # non-zero dispatch is enforced regardless, so it stays blank.
        assert record["Enforce"] == ""


def test_a_zero_mw_datacenter_sets_enforce(mini_base: Path, tmp_path: Path):
    tables = ec.read_case(mini_base)
    deltas = ec.datacenter_deltas(mini_spec(p_set_mw=0.0, byog_p_nom_mw=0.0,
                                            byog_max_mw=0.0), tables)
    overrides = [d for d in deltas if isinstance(d, ec.ScenarioOverride)]
    assert overrides and all(d.field_map()["Enforce"] == "1" for d in overrides)


# ------------------------------------------------------------------------------
#   k_line -- the per-branch limit derate.
#
#   Every negative test here is a row PSO would accept and solve to optimality
#   while derating nothing.
# ------------------------------------------------------------------------------
MONITORED_BRANCH = "TX_N111179_N111180_1"   # 345 kV, Monitor=1, limit 969.800
UNMONITORED_BRANCH = "N110001_N110041_1"    # 138 kV, Monitor=0, limit 227.900


def k_line_row(target: str = MONITORED_BRANCH, value: str = "0.90") -> dict:
    return {"lever": "k_line", "target": target, "mode": "scale",
            "value": value}


def test_k_line_writes_an_absolute_mw_limit_not_a_scale_factor(
        mini_base: Path, tmp_path: Path):
    """
    The central trap. SCN_BRN_LMT.ScaleFactor scales Schedule and Sequence, not
    NormalLimit, so a k_line expressed as ScaleFactor on a branch with no
    schedule derates nothing at all.
    """
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row()])

    table = ec.read_table(layer / "texas7k_SCN_BRN_LMT.csv")
    assert table.columns == list(ec.NEW_TABLE_COLUMNS["SCN_BRN_LMT"])
    rows = table.records()
    assert len(rows) == 1
    record = rows[0]
    assert record["Branch"] == MONITORED_BRANCH
    # 969.800 * 0.90, as absolute MW.
    assert record["NormalLimit"] == "872.820"
    assert record["ScaleFactor"] == "", "ScaleFactor would scale a schedule"
    assert record["Schedule"] == "" and record["Sequence"] == ""


def test_k_line_writes_the_default_scenario_so_every_cycle_inherits(
        mini_base: Path, tmp_path: Path):
    """
    SCN_ARA_LOD.md's general scenario notes, which SCN_BRN_LMT.md defers to:
    scenario '0' is default data for all scenarios WITHOUT scenario-specific
    data. The base carries no SCN_BRN_LMT at all, so one '0' row covers SC, DA
    and RT -- unlike SCN_ARA_LOD, where a '0' row would leave ScnRT at 1.0.
    """
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row()])
    rows = ec.read_table(layer / "texas7k_SCN_BRN_LMT.csv").records()
    assert [r["Scenario"] for r in rows] == ["0"]


def test_k_line_refuses_an_unmonitored_branch(mini_base: Path):
    """
    BRN_ID.md: when Monitor is not flagged, flows are not calculated and the
    limit is not enforced. Derating one is provably inert, so this is an error
    and not a warning.
    """
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match="Monitor"):
        ec.stress_deltas([k_line_row(target=UNMONITORED_BRANCH)], tables)


def test_k_line_refuses_a_branch_that_does_not_exist(mini_base: Path):
    tables = ec.read_case(mini_base)
    # A node name rather than a Branch key is the plausible operator mistake.
    with pytest.raises(ec.Ercot7kCaseError, match="not in BRN_ID"):
        ec.stress_deltas([k_line_row(target="N111179")], tables)


@pytest.mark.parametrize("value", ["0", "0.0", "-0.5"])
def test_k_line_refuses_a_zero_or_negative_factor(mini_base: Path, value: str):
    """
    BRN_ID.md: "If NormalLimit = 0, limits are ignored" -- a zero factor
    REMOVES the constraint rather than closing the line, and even enforced it
    means equal phase angles, not an outage. That is SCN_BRN_OPN's job.
    """
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match="must be positive"):
        ec.stress_deltas([k_line_row(value=value)], tables)


def test_k_line_requires_a_target_and_k_load_refuses_one(mini_base: Path):
    """The two levers have opposite target contracts; neither may default."""
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match="no target"):
        ec.stress_deltas([k_line_row(target="")], tables)
    with pytest.raises(ec.Ercot7kCaseError, match="blank target"):
        ec.stress_deltas(
            [{"lever": "k_load", "target": MONITORED_BRANCH,
              "mode": "scale", "value": "1.10"}], tables)


def test_k_line_can_uprate_as_well_as_derate(mini_base: Path,
                                             tmp_path: Path):
    """
    SCN_BRN_LMT.md: scenario limits override static ones, and static limits are
    "increased as needed to bound scenario limits", so a factor above 1 is
    meaningful rather than silently clamped.
    """
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row(value="1.25")])
    rows = ec.read_table(layer / "texas7k_SCN_BRN_LMT.csv").records()
    assert rows[0]["NormalLimit"] == "1212.250"   # 969.800 * 1.25


def test_v14_catches_a_shadowed_default_scenario_row(mini_base: Path,
                                                     tmp_path: Path):
    """
    A '0' row is inherited only while no scenario states its own value for the
    same branch. Hand-add a scenario row and the derate silently stops applying
    to that scenario, so V14 must refuse the case.
    """
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row()])
    assert not ec.has_errors(ec.verify_case(layer))

    target = layer / "texas7k_SCN_BRN_LMT.csv"
    target.write_bytes(
        target.read_bytes()
        + ("ScnRT,%s,969.800,,,,\n" % MONITORED_BRANCH).encode("ascii")
    )
    findings = ec.verify_case(layer)
    assert ec.has_errors(findings), ec.format_findings(findings)
    assert "shadowed" in ec.format_findings(findings)


def test_v14_catches_a_derate_of_an_unmonitored_branch(mini_base: Path,
                                                       tmp_path: Path):
    """The writer refuses this, so V14 is what catches a hand-edited case."""
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row()])
    target = layer / "texas7k_SCN_BRN_LMT.csv"
    target.write_bytes(
        target.read_bytes()
        + ("0,%s,200.000,,,,\n" % UNMONITORED_BRANCH).encode("ascii")
    )
    findings = ec.verify_case(layer)
    assert ec.has_errors(findings), ec.format_findings(findings)
    assert "Monitor=0" in ec.format_findings(findings)


def test_v14_catches_a_zero_limit_left_unenforced(mini_base: Path,
                                                  tmp_path: Path):
    layer = tmp_path / "kline"
    ec.build_stress_layer(mini_base, layer, [k_line_row()])
    target = layer / "texas7k_SCN_BRN_LMT.csv"
    target.write_bytes(
        target.read_bytes()
        + ("0,%s,0.000,,,,\n" % "TX_N111179_N111181_1").encode("ascii")
    )
    findings = ec.verify_case(layer)
    assert ec.has_errors(findings), ec.format_findings(findings)
    assert "limits are ignored" in ec.format_findings(findings)


# ------------------------------------------------------------------------------
#   k_gen -- the full generator outage.
# ------------------------------------------------------------------------------
GEN = "N111180_1"          # 746 MW, LoadFlag=0


def k_gen_row(target: str = GEN, value: str = "1") -> dict:
    return {"lever": "k_gen", "target": target, "mode": "outage",
            "value": value}


def test_a_datacenter_with_no_byog_omits_the_injector_entirely(
        mini_base: Path, tmp_path: Path):
    """
    The no-BYOG arm is the counterfactual, not a degenerate case: BYOG's value
    is price suppression at its own node, which is only visible against a run
    without it. It must be the ABSENCE of the unit -- a zero-MW generator is
    rejected by V7, and pricing BYOG out instead leaves 500 MW of dispatchable
    capacity that still answers a contingency.
    """
    layer = tmp_path / "nobyog"
    spec = ec.DatacenterSpec(dc_name="DC1", node=MONITORED_NODE,
                             p_set_mw=100.0, byog_p_nom_mw=0.0,
                             byog_max_mw=0.0, byog_mc=0.0)
    manifest = ec.build_datacenter_layer(mini_base, layer, spec)

    injectors = {r["Injector"] for r in
                 ec.read_table(layer / "texas7k_INJ_ID.csv").records()}
    assert "DC1_LOAD" in injectors
    assert "DC1_BYOG" not in injectors
    assert not ec.has_errors(ec.verify_case(layer))

    # The manifest must not send the mapper looking for an absent injector.
    entry = manifest["study"]["datacenters"][0]
    assert entry["byog_injector"] == ""
    assert entry["byog_max_mw"] == 0.0


def test_a_byog_capacity_without_a_ceiling_is_refused(mini_base: Path,
                                                      tmp_path: Path):
    """Zeroing only the ceiling is caught by the existing p_nom check."""
    spec = ec.DatacenterSpec(dc_name="DC1", node=MONITORED_NODE,
                             p_set_mw=100.0, byog_p_nom_mw=50.0,
                             byog_max_mw=0.0, byog_mc=65.0)
    with pytest.raises(ec.Ercot7kCaseError, match="above byog_max_mw"):
        ec.build_datacenter_layer(mini_base, tmp_path / "bad", spec)


def test_k_gen_writes_an_outage_bit_on_the_default_scenario(mini_base: Path,
                                                            tmp_path: Path):
    layer = tmp_path / "kgen"
    ec.build_stress_layer(mini_base, layer, [k_gen_row()])

    table = ec.read_table(layer / "texas7k_SCN_INJ_OUT.csv")
    assert table.columns == list(ec.NEW_TABLE_COLUMNS["SCN_INJ_OUT"])
    rows = table.records()
    assert len(rows) == 1
    assert rows[0]["Scenario"] == "0"
    assert rows[0]["Injector"] == GEN
    assert rows[0]["Outage"] == "1"
    # The generator itself is untouched: the outage is a scenario override, not
    # an edit to INJ_ID, so the parent's capacity still reads 746.
    inj = {r["Injector"]: r for r in
           ec.read_table(layer / "texas7k_INJ_ID.csv").records()}
    assert inj[GEN]["MaxMw"] == "746.000"


@pytest.mark.parametrize("value", ["0", "0.5", "2"])
def test_k_gen_takes_only_the_value_one(mini_base: Path, value: str):
    """
    Outage is a bit. A 0 is IGNORED rather than meaning 'available', so a row
    written from it states nothing while looking deliberate; a fraction is not
    a partial outage either.
    """
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match="takes value 1"):
        ec.stress_deltas([k_gen_row(value=value)], tables)


def test_k_gen_refuses_to_outage_a_load(mini_base: Path, tmp_path: Path):
    """
    Outaging a LoadFlag=1 injector deletes demand while reading, in every
    report, as a generation contingency -- the most plausible way to produce a
    confidently wrong reliability result.
    """
    dc = tmp_path / "dc"
    ec.build_datacenter_layer(mini_base, dc, mini_spec())
    tables = ec.read_case(dc)
    with pytest.raises(ec.Ercot7kCaseError, match="LoadFlag=1"):
        ec.stress_deltas([k_gen_row(target="DC1_LOAD")], tables)
    # BYOG is a generator, so outaging it IS meaningful.
    assert ec.stress_deltas([k_gen_row(target="DC1_BYOG")], tables)


def test_k_gen_refuses_an_unknown_injector(mini_base: Path):
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match="not in INJ_ID"):
        ec.stress_deltas([k_gen_row(target="N111180")], tables)


def test_v15_catches_an_outage_that_states_nothing(mini_base: Path,
                                                    tmp_path: Path):
    layer = tmp_path / "kgen"
    ec.build_stress_layer(mini_base, layer, [k_gen_row()])
    assert not ec.has_errors(ec.verify_case(layer))

    target = layer / "texas7k_SCN_INJ_OUT.csv"
    original = target.read_bytes()

    # Outage=0 with no Enforce: ignored, not "available".
    target.write_bytes(original + b"0,N111181_1,0,,,\n")
    findings = ec.verify_case(layer)
    assert ec.has_errors(findings)
    assert "ignored rather than meaning" in ec.format_findings(findings)

    # A scenario row shadowing the default one.
    target.write_bytes(original + ("ScnRT,%s,1,,,\n" % GEN).encode("ascii"))
    findings = ec.verify_case(layer)
    assert ec.has_errors(findings)
    assert "shadowed" in ec.format_findings(findings)


# ------------------------------------------------------------------------------
#   T4 lever 3 -- k_gen partial, in its two modes
#
# The two modes exist because SCN_INJ_MAX holds two disjoint populations and the
# same field means different things to each. Writing the wrong one is not an
# error in PSO: it is a row that reads as a derate and is discarded.
# ------------------------------------------------------------------------------
DERATE_GEN = "N111333_1"   # 275 MW nameplate, MinDispatch 25, no schedule
AVAIL_GEN = "N220149_1"    # 278 MW nameplate, _fcst and _act schedules


def k_gen_derate_row(target: str = DERATE_GEN, value: str = "200") -> dict:
    return {"lever": "k_gen", "target": target, "mode": "derate",
            "value": value}


def k_gen_avail_row(target: str = AVAIL_GEN, value: str = "0.8") -> dict:
    return {"lever": "k_gen", "target": target, "mode": "avail",
            "value": value}


def test_k_gen_derate_writes_an_absolute_mw_on_the_default_scenario(
        mini_base: Path, tmp_path: Path):
    layer = tmp_path / "kgenderate"
    ec.build_stress_layer(mini_base, layer, [k_gen_derate_row()])

    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
    mine = [r for r in rows if r["Injector"] == DERATE_GEN]
    assert len(mine) == 1
    assert mine[0]["Scenario"] == "0"
    assert mine[0]["MaxMw"] == "200.000"
    assert mine[0]["ScaleFactor"] == "", (
        "ScaleFactor on a unit with no schedule scales nothing")
    # The nameplate is untouched: a derate is a scenario override, and INJ_ID
    # MaxMw is still the BigM the commitment constraints are built from.
    inj = {r["Injector"]: r for r in
           ec.read_table(layer / "texas7k_INJ_ID.csv").records()}
    assert inj[DERATE_GEN]["MaxMw"] == "275.000"
    assert not ec.has_errors(ec.verify_case(layer))


def test_k_gen_avail_scales_both_of_the_schedules_rows(mini_base: Path,
                                                        tmp_path: Path):
    """The '*' form, and it is the whole point of the mode: the base gives
    these units a '0' forecast row and a 'ScnRT' actual row, and a scenario
    with its own row ignores the default entirely. A factor written to '0'
    alone would scale SC and DA and leave RT -- the reported cycle -- at 1."""
    layer = tmp_path / "kgenavail"
    ec.build_stress_layer(mini_base, layer, [k_gen_avail_row()])

    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
    mine = [r for r in rows if r["Injector"] == AVAIL_GEN]
    assert {r["Scenario"] for r in mine} == {"0", "ScnRT"}
    assert all(r["ScaleFactor"] == "0.800" for r in mine)
    assert all(r["MaxMw"] == "" for r in mine), (
        "a static MaxMw here would be outranked by the schedule and ignored")
    assert [r["Schedule"] for r in mine] == ["%s_fcst" % AVAIL_GEN,
                                             "%s_act" % AVAIL_GEN]
    assert not ec.has_errors(ec.verify_case(layer))


def test_k_gen_derate_refuses_a_scheduled_injector_and_names_the_other_mode(
        mini_base: Path):
    """The trap the whole lever is shaped around: a static MaxMw beside a
    schedule that covers every interval is ignored for all of them, with no
    error and no warning."""
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError) as excinfo:
        ec.stress_deltas([k_gen_derate_row(target=AVAIL_GEN)], tables)
    message = str(excinfo.value)
    assert "avail" in message, "the refusal has to name the mode that works"
    assert "%s_fcst" % AVAIL_GEN in message


def test_k_gen_avail_refuses_an_unscheduled_injector_and_names_the_other_mode(
        mini_base: Path):
    """The mirror no-op: ScaleFactor is 'a factor used to scale Schedule and
    Sequence', and this injector carries neither."""
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError) as excinfo:
        ec.stress_deltas([k_gen_avail_row(target=DERATE_GEN)], tables)
    assert "derate" in str(excinfo.value)


@pytest.mark.parametrize("value,why", [
    ("0", "positive"),          # MaxMw=0 is ignored without Enforce=1
    ("-5", "positive"),
    ("900", "INJ_ID.MaxMw"),    # above the nameplate: a plateau, not a derate
    ("10", "MinDispatch"),      # below the commitment floor
])
def test_k_gen_derate_refuses_a_value_outside_the_units_own_window(
        mini_base: Path, value: str, why: str):
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match=why):
        ec.stress_deltas([k_gen_derate_row(value=value)], tables)


@pytest.mark.parametrize("value,why", [
    ("0", "positive"),          # a zero ScaleFactor reads as 1
    ("1.2", "above 1"),         # this lever restricts; it does not raise
])
def test_k_gen_avail_refuses_a_factor_that_is_not_a_derate(mini_base: Path,
                                                            value: str,
                                                            why: str):
    tables = ec.read_case(mini_base)
    with pytest.raises(ec.Ercot7kCaseError, match=why):
        ec.stress_deltas([k_gen_avail_row(value=value)], tables)


def test_neither_partial_mode_will_touch_a_load(mini_base: Path,
                                                 tmp_path: Path):
    """INJ_ID.md: for a LoadFlag injector MaxMw limits WITHDRAWAL, so capping
    it cuts demand while every report reads it as a generation derate."""
    dc = tmp_path / "dc"
    ec.build_datacenter_layer(mini_base, dc, mini_spec())
    tables = ec.read_case(dc)
    with pytest.raises(ec.Ercot7kCaseError, match="LoadFlag=1"):
        ec.stress_deltas([k_gen_derate_row(target="DC1_LOAD", value="50")],
                         tables)
    with pytest.raises(ec.Ercot7kCaseError, match="LoadFlag=1"):
        ec.stress_deltas([k_gen_avail_row(target="DC1_LOAD")], tables)
    # BYOG is a generator with no schedule, so a derate of it IS meaningful.
    assert ec.stress_deltas([k_gen_derate_row(target="DC1_BYOG", value="30")],
                            tables)


def test_the_two_partial_modes_are_registered_and_dispatch_separately():
    """A mode in the registry with no branch in stress_deltas() would be
    accepted by the front end and then refused by an internal error."""
    assert set(ec.STRESS_LEVERS["k_gen"]["modes"]) == {"outage", "derate",
                                                       "avail"}
    tables = ec.read_case(MINI_DIR)
    outage = ec.stress_deltas([k_gen_row()], tables)[0]
    derate = ec.stress_deltas([k_gen_derate_row()], tables)[0]
    avail = ec.stress_deltas([k_gen_avail_row()], tables)[0]
    assert outage.table == "SCN_INJ_OUT"
    assert derate.table == "SCN_INJ_MAX" and derate.scenario == "0"
    assert avail.table == "SCN_INJ_MAX" and avail.scenario == "*"


# ------------------------------------------------------------------------------
#   V16 -- the SCN_INJ_MAX rows that are present and mean nothing
# ------------------------------------------------------------------------------
def _v16_message(case_dir: Path) -> str:
    return ec.format_findings(ec.verify_case(case_dir))


def test_v16_is_quiet_on_the_untouched_case():
    """The shipped base is nothing but scheduled injectors with blank MaxMw
    and blank ScaleFactor. A check that fires there would be noise on every
    run and would be learned to ignore."""
    findings = [f for f in ec.verify_case(MINI_DIR) if f.check == "V16"]
    assert findings and not any(f.level == ec.LEVEL_ERROR for f in findings)


@pytest.mark.parametrize("row,expected", [
    # A static MaxMw beside a schedule that outranks it.
    ("0,N220151_1,100.000,,,N220151_1_fcst,", "outranks"),
    # A ScaleFactor with nothing to scale.
    ("0,N111180_1,,,0.800,,", "neither Schedule nor Sequence"),
    # MaxMw=0 without Enforce: ignored, not "off".
    ("0,N111180_1,0.000,,,,", "Enforce=1"),
    # A zero ScaleFactor reads as 1.
    ("0,N220151_1,,,0.000,N220151_1_fcst,", "read as 1"),
])
def test_v16_catches_a_restriction_that_states_nothing(mini_base: Path,
                                                        tmp_path: Path,
                                                        row: str,
                                                        expected: str):
    layer = tmp_path / "kgenderate"
    ec.build_stress_layer(mini_base, layer, [k_gen_derate_row()])
    assert not ec.has_errors(ec.verify_case(layer))

    target = layer / "texas7k_SCN_INJ_MAX.csv"
    target.write_bytes(target.read_bytes() + (row + "\n").encode("ascii"))
    # Filtered to V16, not merely searched for in the whole report: appending a
    # line to a layer file also breaks the V9 hash chain, so a test that asked
    # only "did anything error" would pass with V16 doing nothing at all.
    findings = [f for f in ec.verify_case(layer) if f.check == "V16"]
    assert any(f.level == ec.LEVEL_ERROR for f in findings)
    assert expected in ec.format_findings(findings)


def test_v16_catches_a_default_value_that_does_not_reach_the_reported_cycle(
        mini_base: Path, tmp_path: Path):
    """The k_load trap in this table's terms. A scenario carrying its own row
    ignores the '0' row entirely, so a value written only to '0' applies to
    every cycle EXCEPT that one -- and here that one is ScnRT, which is what
    every report is read from."""
    layer = tmp_path / "kgenavail"
    ec.build_stress_layer(mini_base, layer, [k_gen_avail_row()])
    assert not ec.has_errors(ec.verify_case(layer))

    target = layer / "texas7k_SCN_INJ_MAX.csv"
    rows = target.read_text(encoding="ascii").splitlines()
    # Strip the factor from the ScnRT row only, which is exactly what a
    # scenario-by-scenario writer would have produced.
    rewritten = [line.replace("0.800", "") if line.startswith("ScnRT,%s,"
                                                              % AVAIL_GEN)
                 else line for line in rows]
    target.write_text("\n".join(rewritten) + "\n", encoding="ascii",
                      newline="")
    findings = [f for f in ec.verify_case(layer) if f.check == "V16"]
    assert any(f.level == ec.LEVEL_ERROR for f in findings)
    message = ec.format_findings(findings)
    assert "shadowed" in message and "ScnRT" in message


def test_a_stress_layer_keeps_its_parents_datacenter_in_the_manifest(
        mini_base: Path, tmp_path: Path):
    """
    Stacking is the study shape: a stress layer is built ON a datacenter layer.
    The injectors are copied like every other row, so the CASE is right and PSO
    solves it with the datacenter present -- but the manifest used to restart
    from an empty study, so the child declared no datacenter and map_results()
    reported the whole deliverability block, the asymptote included, as n/a.
    A correct case with the measurement silently missing.
    """
    dc = tmp_path / "dc"
    ec.build_datacenter_layer(mini_base, dc, mini_spec())
    stressed = tmp_path / "dc_kload"
    ec.build_stress_layer(dc, stressed, [stress_row(value="1.10")])

    parent = ec.read_manifest(dc)["study"]
    child = ec.read_manifest(stressed)["study"]

    # The datacenter survives into the child, unchanged...
    assert [d["dc_name"] for d in child["datacenters"]] == ["DC1"]
    assert child["datacenters"] == parent["datacenters"]
    # ...alongside the stress the child itself applied.
    assert [s["lever"] for s in child["stress"]] == ["k_load"]

    # And the case really does still carry the injectors, which is what makes
    # the manifest's silence a reporting bug rather than a missing datacenter.
    injectors = {r["Injector"] for r in
                 ec.read_table(stressed / "texas7k_INJ_ID.csv").records()}
    assert {"DC1_LOAD", "DC1_BYOG"} <= injectors


def test_a_datacenter_layer_keeps_its_parents_stress_in_the_manifest(
        mini_base: Path, tmp_path: Path):
    """The same inheritance in the other order, which is equally buildable."""
    stressed = tmp_path / "kload"
    ec.build_stress_layer(mini_base, stressed, [stress_row(value="1.10")])
    dc = tmp_path / "kload_dc"
    ec.build_datacenter_layer(stressed, dc, mini_spec())

    study = ec.read_manifest(dc)["study"]
    assert [s["lever"] for s in study["stress"]] == ["k_load"]
    assert [d["dc_name"] for d in study["datacenters"]] == ["DC1"]


def test_three_layers_accumulate_rather_than_overwrite(mini_base: Path,
                                                       tmp_path: Path):
    """A chain keeps every contribution, so the manifest reads as the case is."""
    dc = tmp_path / "dc"
    ec.build_datacenter_layer(mini_base, dc, mini_spec())
    one = tmp_path / "one"
    ec.build_stress_layer(dc, one, [stress_row(value="1.10")])
    two = tmp_path / "two"
    ec.build_stress_layer(one, two, [k_line_row()])

    study = ec.read_manifest(two)["study"]
    assert [d["dc_name"] for d in study["datacenters"]] == ["DC1"]
    assert [s["lever"] for s in study["stress"]] == ["k_load", "k_line"]
    assert len(ec.walk_chain(two)) == 4


def test_scenario_override_on_an_unregistered_table_names_the_registry(
        mini_base: Path, tmp_path: Path):
    """Out of scope, absent rather than stubbed: the error names the way in."""
    for table_name in ("SCN_INJ_CST", "SCN_INJ_ADD"):
        delta = ec.ScenarioOverride.of(table_name, "ScnRT", "X",
                                       {"ScaleFactor": "1.200"})
        with pytest.raises(NotImplementedError, match="SCN_TABLES"):
            ec.write_layer(mini_base, tmp_path / table_name, [delta])


def test_field_edit_is_absent_and_names_its_extension_point(mini_base: Path,
                                                            tmp_path: Path):
    delta = ec.FieldEdit("BRN_ID", ("N110001_N110041_1",), "Monitor", "0", "1")
    with pytest.raises(NotImplementedError, match="apply_deltas"):
        ec.write_layer(mini_base, tmp_path / "fe", [delta])


# ------------------------------------------------------------------------------
#   5. verify_case on the real base and on a real derived layer
# ------------------------------------------------------------------------------
def test_verify_case_passes_clean_on_the_base_itself():
    """If the base fails its own checks, the checks are wrong."""
    findings = ec.verify_case(BASE_DIR)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert not [f for f in findings if f.level == ec.LEVEL_WARNING]


def test_verify_case_passes_clean_on_the_fixture():
    findings = ec.verify_case(MINI_DIR)
    assert not ec.has_errors(findings), ec.format_findings(findings)


@pytest.mark.parametrize("node,why", [
    # The study node: HEWITT 3, import side of the branch that bound in 69 of
    # the 168 RT intervals of the 2018 case, so load here deepened a live
    # constraint. Not yet re-measured on the 2030 WA case.
    ("N210144", "congested pocket"),
    # BAY CITY 3, the old template default: a real 345 kV node on monitored
    # branches that never binds. Kept as a control -- a layer there must still
    # verify clean, so a clean verify is not evidence the node does anything.
    ("N110126", "quiet node"),
])
def test_a_real_datacenter_layer_off_ercot7k_verifies_clean(
        node: str, why: str, tmp_path: Path):
    spec = ec.DatacenterSpec(dc_name="DC1", node=node, p_set_mw=1000.0,
                             byog_p_nom_mw=500.0, byog_max_mw=500.0,
                             byog_mc=65.0)
    layer = tmp_path / ec.layer_dir_name(BASE_DIR, "dc1")
    manifest = ec.build_datacenter_layer(BASE_DIR, layer, spec)

    findings = ec.verify_case(layer)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    checks = {f.check for f in findings if f.level == ec.LEVEL_OK}
    for required in ("V1", "V2", "V3", "V4", "V5", "V7", "V8", "V9", "V10",
                     "V11", "V12", "V13"):
        assert required in checks, "%s did not execute: %s" % (
            required, ec.format_findings(findings))

    injectors = ec.read_table(layer / "texas7k_INJ_ID.csv").records()
    assert len(injectors) == 1065
    assert manifest["study"]["datacenters"][0]["pin_mechanism"] == (
        "scn_inj_dsp_fixed")
    expected = manifest["study"]["datacenters"][0]["expected_dc_mw_by_interval"]
    assert len(expected) == 385
    assert expected["2026.06.12 00:00"] == 1000.0
    assert expected["2026.06.28 00:00"] == 1000.0


def test_the_datacenter_load_spans_the_whole_of_min_to_max_date():
    """MinDate..MaxDate, not StartDate..StopDate: SC carries 48 h of lead."""
    tables = ec.read_case(BASE_DIR)
    points = ec.model_timepoints(tables)
    mdl = ec.model_id(tables)
    assert points[0] == mdl["MinDate"]
    assert points[-1] == mdl["MaxDate"]
    assert len(points) == 385
    assert mdl["StartDate"] != mdl["MinDate"]
    assert mdl["StopDate"] != mdl["MaxDate"]


# ------------------------------------------------------------------------------
#   6. Negative tests. One per silent failure.
# ------------------------------------------------------------------------------
def test_area_zero_on_an_added_injector_is_refused(mini_base: Path,
                                                   tmp_path: Path,
                                                   monkeypatch):
    """Area=0 is a dummy injector: the case runs clean and does nothing."""
    original = ec.injector_id_values

    def with_area_zero(delta):
        values = original(delta)
        values["Area"] = "0"
        return values

    monkeypatch.setattr(ec, "injector_id_values", with_area_zero)
    layer = tmp_path / "layer1"
    with pytest.raises(ec.VerificationError, match="V2"):
        ec.build_datacenter_layer(mini_base, layer, mini_spec())
    assert not layer.exists(), "a rejected layer must not be emitted"


def test_a_duplicate_injector_name_is_refused(mini_base: Path, tmp_path: Path):
    """Duplicate primary keys coalesce non-blank fields, silently merging."""
    deltas = [
        ec.AddInjector("N111180_1", MONITORED_NODE, True, 100.0),
    ]
    with pytest.raises(ec.OwnershipError, match="COALESCE"):
        ec.write_layer(mini_base, tmp_path / "dup", deltas)


def test_a_layer_two_add_over_a_layer_one_key_is_refused(mini_base: Path,
                                                         tmp_path: Path):
    layer1 = tmp_path / "l1"
    ec.build_datacenter_layer(mini_base, layer1, mini_spec())
    with pytest.raises(ec.OwnershipError):
        ec.build_datacenter_layer(layer1, tmp_path / "l2", mini_spec())


def test_a_schedule_short_of_max_date_is_refused(mini_base: Path,
                                                 tmp_path: Path):
    """Values past the last time point read as ZERO, not hold-last."""
    short = tuple(1.0 for _ in range(MINI_TIMEPOINTS - 1))
    deltas = [ec.AddSchedule("DC1_shape", short,
                             repeat_time=MINI_TIMEPOINTS - 1)]
    with pytest.raises(ec.Ercot7kCaseError, match="MaxDate"):
        ec.write_layer(mini_base, tmp_path / "short", deltas)


def test_a_missing_scenario_row_is_refused(mini_base: Path, tmp_path: Path):
    """A missing scenario row is a silently switched-off datacenter."""
    deltas = [
        ec.AddInjector("DC1_LOAD", MONITORED_NODE, True, 100.0),
        ec.ScenarioOverride.of("SCN_INJ_DSP", "ScnSC", "DC1_LOAD",
                               {"Dispatch": "100.000"}),
        ec.ScenarioOverride.of("SCN_INJ_DSP", "ScnRT", "DC1_LOAD",
                               {"Dispatch": "100.000"}),
    ]
    with pytest.raises(ec.VerificationError, match="ScnDA"):
        ec.write_layer(mini_base, tmp_path / "missing", deltas)


def test_a_positive_min_mw_is_refused(mini_base: Path, tmp_path: Path):
    deltas = [ec.AddInjector("DC1_LOAD", MONITORED_NODE, True, 100.0,
                             min_mw=5.0)]
    with pytest.raises(ec.VerificationError, match="V7"):
        ec.write_layer(mini_base, tmp_path / "minmw", deltas)


def test_byog_p_nom_above_byog_max_mw_is_refused(mini_base: Path,
                                                 tmp_path: Path):
    """SCN_INJ_MAX can only restrict INJ_ID.MaxMw, so the run would be capped."""
    spec = mini_spec(byog_p_nom_mw=75.0, byog_max_mw=50.0)
    with pytest.raises(ec.Ercot7kCaseError, match="study ceiling"):
        ec.build_datacenter_layer(mini_base, tmp_path / "byog", spec)


def test_an_unknown_node_is_refused(mini_base: Path, tmp_path: Path):
    """An unmapped node falls back to area load distribution, silently."""
    spec = mini_spec(node="N999999")
    with pytest.raises(ec.Ercot7kCaseError, match="NDE_ID"):
        ec.build_datacenter_layer(mini_base, tmp_path / "node", spec)


def test_a_datacenter_at_an_unmonitored_node_warns_and_can_be_made_fatal(
        mini_base: Path, tmp_path: Path):
    """Only 1171 of 9140 branches are monitored; the rest report nothing."""
    layer = tmp_path / "warn"
    ec.build_datacenter_layer(mini_base, layer, mini_spec(node=UNMONITORED_NODE))
    findings = ec.verify_case(layer)
    warnings = [f for f in findings if f.check == "V8"]
    assert warnings and warnings[0].level == ec.LEVEL_WARNING

    with pytest.raises(ec.VerificationError, match="V8"):
        ec.build_datacenter_layer(mini_base, tmp_path / "strict",
                                  mini_spec(node=UNMONITORED_NODE),
                                  strict_monitored=True)


def test_a_tampered_derived_case_fails_the_v9_line_diff(mini_base: Path,
                                                        tmp_path: Path):
    layer = tmp_path / "layer1"
    ec.build_datacenter_layer(mini_base, layer, mini_spec())
    target = layer / "texas7k_NDE_ID.csv"
    target.write_bytes(target.read_bytes().replace(b"N110001", b"N110002", 1))
    findings = ec.verify_case(layer)
    v9 = [f for f in findings if f.check == "V9" and f.level == ec.LEVEL_ERROR]
    assert v9, ec.format_findings(findings)


def test_a_field_containing_a_comma_is_refused(mini_base: Path,
                                               tmp_path: Path):
    deltas = [ec.AddInjector("DC1_LOAD", MONITORED_NODE, True, 100.0,
                             name="Big, Datacenter")]
    with pytest.raises(ec.ByteFidelityError):
        ec.write_layer(mini_base, tmp_path / "comma", deltas)


def test_a_rejected_layer_leaves_nothing_behind(mini_base: Path,
                                                tmp_path: Path):
    out = tmp_path / "gone"
    with pytest.raises(ec.Ercot7kCaseError):
        ec.write_layer(mini_base, out,
                       [ec.AddInjector("N111180_1", MONITORED_NODE, True, 1.0)])
    assert not out.exists()


# ------------------------------------------------------------------------------
#   7. ScenarioOverride on SCN_ARA_LOD -- the k_load lever
#
#   SCN_ARA_LOD is a whole-file rewrite touching EVERY row, not an append.
#   VERIFIED, SCN_ARA_LOD.md: a ScaleFactor "assigned to the default scenario
#   '0' is applied only to schedules and sequences also associated with the
#   default scenario. Non-default scenarios that do not have a ScaleFactor will
#   be assigned a value of 1." The fixture holds both base rows -- '0' ->
#   Load_fcst driving SC and DA, and ScnRT -> Load_act driving the REPORTED
#   cycle -- so a factor on one row only would leave the reported cycle at 1.0.
# ------------------------------------------------------------------------------
def k_load(factor: str, area: str = "0") -> ec.ScenarioOverride:
    return ec.ScenarioOverride.of("SCN_ARA_LOD", "*", area,
                                  {"ScaleFactor": factor})


def test_k_load_reaches_every_scn_ara_lod_row(mini_base: Path, tmp_path: Path):
    layer = tmp_path / "kload"
    ec.write_layer(mini_base, layer, [k_load("1.200")], slug="k")
    rows = ec.read_table(layer / "texas7k_SCN_ARA_LOD.csv").records()
    assert [r["Scenario"] for r in rows] == ["0", "ScnRT"]
    assert all(r["ScaleFactor"] == "1.200" for r in rows), (
        "a factor that misses ScnRT leaves the reported cycle unscaled")
    # The lever must not disturb the schedule mapping it scales.
    assert [r["Schedule"] for r in rows] == ["Load_fcst", "Load_act"]
    assert not ec.has_errors(ec.verify_case(layer))


def test_k_load_on_a_literal_scenario_is_refused(mini_base: Path,
                                                 tmp_path: Path):
    delta = ec.ScenarioOverride.of("SCN_ARA_LOD", "0", "0",
                                   {"ScaleFactor": "1.200"})
    with pytest.raises(ec.Ercot7kCaseError, match="reported cycle"):
        ec.write_layer(mini_base, tmp_path / "literal", [delta])


def test_a_zero_k_load_is_refused(mini_base: Path, tmp_path: Path):
    """VERIFIED: a ScaleFactor of 0 is silently read as 1, not as zero load."""
    with pytest.raises(ec.Ercot7kCaseError, match="ScaleFactor = 1"):
        ec.write_layer(mini_base, tmp_path / "zero", [k_load("0.000")])
    with pytest.raises(ec.Ercot7kCaseError, match="ScaleFactor = 1"):
        ec.write_layer(mini_base, tmp_path / "blank", [k_load("")])


def test_a_k_load_layer_changes_only_the_declared_lines(mini_base: Path,
                                                        tmp_path: Path):
    """The rewrite is held to the same byte standard as an append."""
    layer = tmp_path / "kload"
    manifest = ec.write_layer(mini_base, layer, [k_load("1.200")], slug="k")

    assert set(manifest["changed_files"]) == {"texas7k_SCN_ARA_LOD.csv"}
    entry = manifest["changed_files"]["texas7k_SCN_ARA_LOD.csv"]
    assert entry["added"] == []
    assert len(entry["edits"]) == 2
    assert manifest["owned_files"] == []

    for path in ec.case_files(mini_base):
        target = layer / path.name
        if path.name == "texas7k_SCN_ARA_LOD.csv":
            parent = path.read_bytes().decode("ascii").splitlines()
            child = target.read_bytes().decode("ascii").splitlines()
            assert len(parent) == len(child)
            differing = [i for i, (a, b) in enumerate(zip(parent, child))
                         if a != b]
            assert differing == [1, 2], "only the two data rows may differ"
        else:
            assert target.read_bytes() == path.read_bytes(), path.name


def test_a_tampered_k_load_rewrite_fails_the_v9_line_diff(mini_base: Path,
                                                          tmp_path: Path):
    layer = tmp_path / "kload"
    ec.write_layer(mini_base, layer, [k_load("1.200")], slug="k")
    target = layer / "texas7k_SCN_ARA_LOD.csv"
    target.write_bytes(target.read_bytes().replace(b"1.200", b"1.900"))
    findings = ec.verify_case(layer)
    v9 = [f for f in findings if f.check == "V9" and f.level == ec.LEVEL_ERROR]
    assert v9, ec.format_findings(findings)


def test_a_parent_edited_under_a_k_load_layer_fails_the_v9_replay(
        mini_base: Path, tmp_path: Path):
    """Every declared edit names the exact parent line it replaced."""
    layer = tmp_path / "kload"
    ec.write_layer(mini_base, layer, [k_load("1.200")], slug="k")
    parent = mini_base / "texas7k_SCN_ARA_LOD.csv"
    parent.write_bytes(parent.read_bytes().replace(b"Load_act", b"Load_fcst"))
    findings = ec.verify_case(layer)
    v9 = [f for f in findings
          if f.check == "V9" and f.level == ec.LEVEL_ERROR
          and "do not match the parent" in f.message]
    assert v9, ec.format_findings(findings)


def test_a_k_load_that_misses_a_row_is_caught_by_v6(mini_base: Path,
                                                    tmp_path: Path):
    """The silent failure itself: ScnRT, the reported cycle, left at 1.0."""
    layer = tmp_path / "kload"
    ec.write_layer(mini_base, layer, [k_load("1.200")], slug="k")
    target = layer / "texas7k_SCN_ARA_LOD.csv"
    target.write_bytes(
        target.read_bytes().replace(b"ScnRT,0,,,1.200,", b"ScnRT,0,,,,"))
    findings = ec.verify_case(layer)
    v6 = [f for f in findings if f.check == "V6" and f.level == ec.LEVEL_ERROR]
    assert v6, ec.format_findings(findings)


# ------------------------------------------------------------------------------
#   8. ScenarioOverride on SCN_INJ_MAX -- two disjoint populations
#
#   SCHEDULED_INJECTORS already carry a '0' -> <unit>_fcst row and a ScnRT ->
#   <unit>_act row, so they may set ScaleFactor only. PLAIN_INJECTORS carry no
#   SCN_INJ_MAX row at all, so they take an appended MaxMw on scenario '0'.
# ------------------------------------------------------------------------------
SCHEDULED_INJECTORS = ("N220149_1", "N220151_1")
PLAIN_INJECTORS = ("N111180_1", "N111181_1", "N111333_1")


def test_the_fixture_holds_both_scn_inj_max_populations():
    """A fixture with one population cannot exercise the rule that splits them."""
    rows = ec.read_table(MINI_DIR / "texas7k_SCN_INJ_MAX.csv").records()
    scheduled = {r["Injector"] for r in rows}
    assert scheduled == set(SCHEDULED_INJECTORS)
    for injector in SCHEDULED_INJECTORS:
        mine = [r for r in rows if r["Injector"] == injector]
        assert {r["Scenario"] for r in mine} == {"0", "ScnRT"}
        assert all(r["Schedule"] for r in mine)
        assert all(r["MaxMw"] == "" for r in mine)
    all_injectors = {r["Injector"] for r in
                     ec.read_table(MINI_DIR / "texas7k_INJ_ID.csv").records()}
    assert set(PLAIN_INJECTORS) <= all_injectors - scheduled
    assert len(all_injectors - scheduled) >= 2


def test_max_mw_on_a_scheduled_injector_is_refused(mini_base: Path,
                                                   tmp_path: Path):
    """Sequence > Schedule > static value, and the schedules cover every hour."""
    injector = SCHEDULED_INJECTORS[0]
    delta = ec.ScenarioOverride.of("SCN_INJ_MAX", "*", injector,
                                   {"MaxMw": "100.000"})
    with pytest.raises(ec.Ercot7kCaseError) as excinfo:
        ec.write_layer(mini_base, tmp_path / "maxmw", [delta])
    message = str(excinfo.value)
    assert injector in message, "the error must name the injector"
    assert "%s_fcst" % injector in message
    assert "%s_act" % injector in message
    assert "priority" in message


def test_scale_factor_on_a_scheduled_injector_edits_both_rows(mini_base: Path,
                                                              tmp_path: Path):
    injector = SCHEDULED_INJECTORS[0]
    other = SCHEDULED_INJECTORS[1]
    layer = tmp_path / "scale"
    manifest = ec.write_layer(
        mini_base, layer,
        [ec.ScenarioOverride.of("SCN_INJ_MAX", "*", injector,
                                {"ScaleFactor": "0.800"})],
        slug="scale")

    parent_rows = ec.read_table(mini_base / "texas7k_SCN_INJ_MAX.csv").records()
    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()

    # Existing row ORDER is preserved. A reordering would show in V9 as every
    # row changed and drown the two that were meant to.
    assert [(r["Scenario"], r["Injector"]) for r in rows] == (
        [(r["Scenario"], r["Injector"]) for r in parent_rows])

    mine = [r for r in rows if r["Injector"] == injector]
    assert len(mine) == 2
    assert all(r["ScaleFactor"] == "0.800" for r in mine)
    # Schedule is what ScaleFactor scales; it must be untouched.
    assert [r["Schedule"] for r in mine] == ["%s_fcst" % injector,
                                             "%s_act" % injector]
    assert all(r["MaxMw"] == "" for r in mine)
    assert all(r["ScaleFactor"] == "" for r in rows if r["Injector"] == other)

    owned = {(e["table"], tuple(e["key"])) for e in manifest["owned"]}
    assert ("SCN_INJ_MAX", ("0", injector)) in owned
    assert ("SCN_INJ_MAX", ("ScnRT", injector)) in owned
    assert not ec.has_errors(ec.verify_case(layer))


def test_max_mw_on_an_unscheduled_injector_appends_one_default_row(
        mini_base: Path, tmp_path: Path):
    """One '0' row covers every scenario: none of them names this injector."""
    injector = PLAIN_INJECTORS[0]
    layer = tmp_path / "append"
    ec.write_layer(mini_base, layer,
                   [ec.ScenarioOverride.of("SCN_INJ_MAX", "0", injector,
                                           {"MaxMw": "300.000"})],
                   slug="append")

    parent_rows = ec.read_table(mini_base / "texas7k_SCN_INJ_MAX.csv").records()
    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
    assert len(rows) == len(parent_rows) + 1
    # Appended at the END, with every inherited row still in its own place.
    assert rows[:-1] == parent_rows
    assert rows[-1]["Scenario"] == "0"
    assert rows[-1]["Injector"] == injector
    assert rows[-1]["MaxMw"] == "300.000"
    assert rows[-1]["Schedule"] == ""
    assert not ec.has_errors(ec.verify_case(layer))


def test_the_all_rows_form_on_an_unscheduled_injector_is_refused(
        mini_base: Path, tmp_path: Path):
    delta = ec.ScenarioOverride.of("SCN_INJ_MAX", "*", PLAIN_INJECTORS[0],
                                   {"MaxMw": "300.000"})
    with pytest.raises(ec.Ercot7kCaseError, match="nothing for the"):
        ec.write_layer(mini_base, tmp_path / "star", [delta])


def test_a_named_scenario_on_an_unscheduled_injector_is_refused(
        mini_base: Path, tmp_path: Path):
    """A single named scenario would leave the other two uncapped."""
    delta = ec.ScenarioOverride.of("SCN_INJ_MAX", "ScnRT", PLAIN_INJECTORS[0],
                                   {"MaxMw": "300.000"})
    with pytest.raises(ec.Ercot7kCaseError, match="uncapped"):
        ec.write_layer(mini_base, tmp_path / "named", [delta])


def test_max_mw_above_the_inj_id_ceiling_is_refused(mini_base: Path,
                                                    tmp_path: Path):
    """SCN_INJ_MAX can only restrict; above the ceiling the run is capped."""
    delta = ec.ScenarioOverride.of("SCN_INJ_MAX", "0", PLAIN_INJECTORS[0],
                                   {"MaxMw": "9000.000"})
    with pytest.raises(ec.Ercot7kCaseError, match="silently capped"):
        ec.write_layer(mini_base, tmp_path / "ceiling", [delta])


def test_max_mw_below_min_dispatch_is_refused(mini_base: Path, tmp_path: Path):
    """VERIFIED: the limit cannot be more restrictive than INJ_CMT.MinDispatch."""
    delta = ec.ScenarioOverride.of("SCN_INJ_MAX", "0", PLAIN_INJECTORS[0],
                                   {"MaxMw": "10.000"})
    with pytest.raises(ec.Ercot7kCaseError, match="MinDispatch"):
        ec.write_layer(mini_base, tmp_path / "mindisp", [delta])


def test_a_byog_below_its_ceiling_gets_a_scn_inj_max_row(mini_base: Path,
                                                         tmp_path: Path):
    """byog_max_mw is the study ceiling; byog_p_nom is the capacity this run."""
    layer = tmp_path / "byog"
    manifest = ec.build_datacenter_layer(
        mini_base, layer, mini_spec(byog_p_nom_mw=25.0, byog_max_mw=50.0))

    injectors = {r["Injector"]: r for r in
                 ec.read_table(layer / "texas7k_INJ_ID.csv").records()}
    assert injectors["DC1_BYOG"]["MaxMw"] == "50.000"
    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
    added = [r for r in rows if r["Injector"] == "DC1_BYOG"]
    assert len(added) == 1
    assert added[0]["Scenario"] == "0"
    assert added[0]["MaxMw"] == "25.000"
    assert manifest["capacity_ceilings"]["DC1_BYOG"] == 50.0
    findings = ec.verify_case(layer)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert "V11" in {f.check for f in findings if f.level == ec.LEVEL_OK}


def test_an_equal_byog_writes_no_scn_inj_max_row(mini_base: Path,
                                                 tmp_path: Path):
    """A row restating INJ_ID.MaxMw is a line of diff carrying no information."""
    layer = tmp_path / "byog"
    ec.build_datacenter_layer(mini_base, layer, mini_spec())
    assert (layer / "texas7k_SCN_INJ_MAX.csv").read_bytes() == (
        (mini_base / "texas7k_SCN_INJ_MAX.csv").read_bytes())


def test_a_hand_raised_scn_inj_max_is_caught_by_v11(mini_base: Path,
                                                    tmp_path: Path):
    layer = tmp_path / "byog"
    ec.build_datacenter_layer(
        mini_base, layer, mini_spec(byog_p_nom_mw=25.0, byog_max_mw=50.0))
    target = layer / "texas7k_SCN_INJ_MAX.csv"
    target.write_bytes(target.read_bytes().replace(b"25.000", b"99.000"))
    findings = ec.verify_case(layer)
    v11 = [f for f in findings
           if f.check == "V11" and f.level == ec.LEVEL_ERROR]
    assert v11, ec.format_findings(findings)


# ------------------------------------------------------------------------------
#   9. stress_deltas() -- the lever expander
#
#   An unrecognised lever or mode is a HARD ERROR naming what is implemented. A
#   skipped row is the exact failure this component exists to prevent: the sweep
#   runs, the numbers move a little for unrelated reasons, and the lever the
#   study rests on was never applied.
# ------------------------------------------------------------------------------
def stress_row(**overrides) -> dict:
    row = {"lever": "k_load", "target": "", "mode": "scale", "value": "1.20"}
    row.update(overrides)
    return row


def test_k_load_expands_to_one_all_rows_override():
    tables = ec.read_case(MINI_DIR)
    deltas = ec.stress_deltas([stress_row()], tables)
    assert len(deltas) == 1
    delta = deltas[0]
    assert isinstance(delta, ec.ScenarioOverride)
    assert delta.table == "SCN_ARA_LOD"
    assert delta.scenario == "*"
    assert delta.field_map() == {"ScaleFactor": "1.200"}


def test_an_unknown_lever_is_refused_and_names_the_implemented_set():
    # mc_bus is the next lever in the recommended order and is NOT built yet.
    # If it ever is, this test must move to another unimplemented name rather
    # than be deleted -- it is the guard on the unknown-lever path itself.
    unknown = "mc_bus"
    assert unknown not in ec.STRESS_LEVERS, (
        "%s is implemented now; point this test at an unbuilt lever" % unknown)

    tables = ec.read_case(MINI_DIR)
    with pytest.raises(ec.Ercot7kCaseError) as excinfo:
        ec.stress_deltas([stress_row(lever=unknown, value="0.90")], tables)
    message = str(excinfo.value)
    assert unknown in message
    for lever in ec.STRESS_LEVERS:
        assert lever in message, "the error must name what IS implemented"
    assert "STRESS_LEVERS" in message


def test_an_unknown_mode_is_refused():
    tables = ec.read_case(MINI_DIR)
    with pytest.raises(ec.Ercot7kCaseError, match="mode"):
        ec.stress_deltas([stress_row(mode="add")], tables)


def test_a_targeted_k_load_is_refused():
    """Per-bus and per-area k_load are out of scope, not silently system-wide."""
    tables = ec.read_case(MINI_DIR)
    with pytest.raises(ec.Ercot7kCaseError, match="blank target"):
        ec.stress_deltas([stress_row(target="N111179")], tables)


def test_a_blank_lever_row_is_refused_rather_than_skipped():
    tables = ec.read_case(MINI_DIR)
    with pytest.raises(ec.Ercot7kCaseError, match="row to skip"):
        ec.stress_deltas([stress_row(lever="")], tables)


def test_a_non_numeric_or_zero_k_load_is_refused():
    tables = ec.read_case(MINI_DIR)
    with pytest.raises(ec.Ercot7kCaseError, match="not a number"):
        ec.stress_deltas([stress_row(value="a lot")], tables)
    with pytest.raises(ec.Ercot7kCaseError, match="untouched"):
        ec.stress_deltas([stress_row(value="0")], tables)


def test_a_stress_layer_that_expands_to_nothing_is_refused(mini_base: Path,
                                                           tmp_path: Path):
    with pytest.raises(ec.Ercot7kCaseError, match="byte-identical copy"):
        ec.build_stress_layer(mini_base, tmp_path / "empty", [])


# ------------------------------------------------------------------------------
#   10. A two-layer chain end to end: datacenter, then k_load on top
# ------------------------------------------------------------------------------
def test_a_datacenter_then_a_k_load_layer_verify_clean(mini_base: Path,
                                                       tmp_path: Path):
    dc_layer = tmp_path / ec.layer_dir_name(mini_base, "dc1")
    ec.build_datacenter_layer(mini_base, dc_layer,
                              mini_spec(byog_p_nom_mw=25.0, byog_max_mw=50.0))
    findings = ec.verify_case(dc_layer)
    assert not ec.has_errors(findings), ec.format_findings(findings)

    stress_layer = tmp_path / ec.layer_dir_name(dc_layer, "k_load1p20")
    manifest = ec.build_stress_layer(dc_layer, stress_layer,
                                     [stress_row()], slug="k_load1p20")
    findings = ec.verify_case(stress_layer)
    assert not ec.has_errors(findings), ec.format_findings(findings)

    chain = ec.walk_chain(stress_layer)
    assert [c.kind for c in chain] == ["base", "layer", "layer"]
    # The stress layer inherits the datacenter's ceiling and the datacenter rows.
    assert ec.chain_capacity_ceilings(chain)["DC1_BYOG"] == 50.0
    assert manifest["study"]["stress"][0]["lever"] == "k_load"

    rows = ec.read_table(stress_layer / "texas7k_SCN_ARA_LOD.csv").records()
    assert all(r["ScaleFactor"] == "1.200" for r in rows)
    dsp = ec.read_table(stress_layer / "texas7k_SCN_INJ_DSP.csv").records()
    assert len(dsp) == 3, "the datacenter pin survives the layer above it"
    inj_max = ec.read_table(stress_layer / "texas7k_SCN_INJ_MAX.csv").records()
    assert [r for r in inj_max if r["Injector"] == "DC1_BYOG"]


def test_two_k_load_layers_each_declare_the_value_they_replace(
        mini_base: Path, tmp_path: Path):
    """Adds are exclusive; edits are allowed but must declare their prior value."""
    first = tmp_path / "k1"
    ec.write_layer(mini_base, first, [k_load("1.200")], slug="k1")
    second = tmp_path / "k2"
    manifest = ec.write_layer(first, second, [k_load("1.400")], slug="k2")

    prior = [e["prior_values"] for e in manifest["owned"]
             if e["table"] == "SCN_ARA_LOD"]
    assert prior == [{"ScaleFactor": "1.200"}, {"ScaleFactor": "1.200"}]
    rows = ec.read_table(second / "texas7k_SCN_ARA_LOD.csv").records()
    assert all(r["ScaleFactor"] == "1.400" for r in rows), (
        "the second factor replaces the first; it does not compound")
    assert not ec.has_errors(ec.verify_case(second))


# ------------------------------------------------------------------------------
#   11. ercot7k_build.py -- the operator front end
#
#   It cannot be imported: like every other root script it executes at module
#   level -- banner, log file, Tee over sys.stdout, prompts. So it is exercised
#   by subprocess with stdin supplied, never by import.
# ------------------------------------------------------------------------------
BUILD_SCRIPT = REPO_ROOT / "ercot7k_build.py"


def run_build(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), *args],
        input=stdin, capture_output=True, text=True, cwd=str(REPO_ROOT),
        timeout=300,
    )


def test_the_front_end_runs_and_prints_its_usage():
    result = run_build("--help")
    assert result.returncode == 0, result.stderr
    assert "--init" in result.stdout
    assert "--show-config" in result.stdout


def test_the_front_end_executes_at_module_level_so_it_is_never_imported():
    """The banner is printed before any argument is looked at."""
    result = run_build("--help")
    assert "ERCOT Texas7k Derived Case Builder" in result.stdout


def test_the_front_end_refuses_an_unknown_argument():
    result = run_build("--sweep")
    assert result.returncode == 2
    assert "AMW-ERR" in result.stdout


def test_the_front_end_never_dumps_a_traceback_on_a_closed_stdin():
    """Launched from the menu it is interactive; a closed stdin is not a crash.

    Which AMW-ERR comes back depends on whether the operator has generated
    ercot7k_config/ yet -- those CSVs are gitignored, so a fresh checkout stops
    at the missing folder and a working copy stops at the first prompt. Either
    way it must be a stated reason and an exit code, not a traceback.
    """
    result = run_build(stdin="")
    assert result.returncode == 2
    assert "AMW-ERR" in result.stdout
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_previous_values_rows_are_ignored(tmp_path: Path):
    """An operator keeps old parameter sets in the same file, below the marker."""
    config = tmp_path / "cfg"
    config.mkdir()
    (config / "ercot7k_dc.csv").write_text(
        "dc_name,node,p_set_mw,byog_p_nom_mw,byog_max_mw,byog_mc,load_shape\n"
        "DC1,N110126,1000,500,500,65,flat\n"
        "# Previous Values,,,,,,\n"
        "DCOLD,N110127,4000,4000,4000,99,flat\n",
        encoding="ascii")
    (config / "ercot7k_stress.csv").write_text(
        "lever,target,mode,value\n"
        "k_load,,scale,1.20\n"
        "# Previous Values,,,\n"
        "k_line,,scale,0.90\n",
        encoding="ascii")

    result = run_build("--show-config", str(config))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ercot7k_dc.csv:: 1 active row(s)" in result.stdout
    assert "ercot7k_stress.csv:: 1 active row(s)" in result.stdout
    assert "DC1" in result.stdout
    assert "DCOLD" not in result.stdout, "rows below the marker are not active"
    assert "k_line" not in result.stdout, "rows below the marker are not active"


def test_the_front_end_reports_a_missing_config_folder(tmp_path: Path):
    result = run_build("--show-config", str(tmp_path / "absent"))
    assert result.returncode == 2
    assert "AMW-ERR" in result.stdout


# ------------------------------------------------------------------------------
#   12. Style: plain ASCII everywhere
#
#   The base case is plain ASCII throughout and _serialize_fields() refuses
#   anything else, so a stray unicode dash in a printed message is a crash
#   waiting for a cp1252 console rather than a cosmetic issue.
# ------------------------------------------------------------------------------
def test_the_new_modules_are_plain_ascii():
    for name in ("ercot7k_case.py", "ercot7k_build.py",
                 "tests/test_ercot7k_case.py", "tests/cut_mini7k.py"):
        data = (REPO_ROOT / name).read_bytes()
        try:
            data.decode("ascii")
        except UnicodeDecodeError as exc:
            pytest.fail("%s is not plain ASCII: %s" % (name, exc))
