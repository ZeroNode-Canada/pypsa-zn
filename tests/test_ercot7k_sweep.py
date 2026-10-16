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

# test_ercot7k_sweep.py
#
# Purpose
#   Test ercot7k_sweep.py without an AIMMS seat. The seat is single and a real
#   step is six minutes, so a suite that needed one would never be run -- and an
#   untested sweep driver is precisely how devnet's two defects survived in
#   lib/devnet_stress_lib.py long enough to be reported twice.
#
#   The two inherited defects are tested as defects, not as absences:
#     - the descending endpoint (devnet's own presets, asserted point by point)
#     - a lever that never reaches the solver, simulated by a fake PSO that
#       ignores the case it is handed, asserted to produce a W2 ERROR
#
# What it does
#   - Asserts the step arithmetic, including every refusal.
#   - Reads both witnesses out of synthetic results directories, and asserts an
#     unreported path is NOT MEASURED rather than a limit of zero.
#   - Drives the whole loop against a REAL case layer built by ercot7k_case.py
#     with a fake solver that honours the layer it is given, so the witness
#     chain runs end to end: config row -> delta -> case file -> results ->
#     witness -> verdict.
#   - Drives the same loop with a fake solver that ignores the layer, and
#     asserts the driver calls it a failed sweep.
#
# Outputs
#   - pytest results only. Everything is written under tmp_path.
#
# Run: python -m pytest tests/test_ercot7k_sweep.py -q
# ------------------------------------------------------------------------------

from __future__ import annotations

import dataclasses
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ercot7k_case as ec  # noqa: E402
import ercot7k_results as er  # noqa: E402
import ercot7k_sweep as es  # noqa: E402

MINI_DIR = REPO_ROOT / "tests" / "fixtures" / "mini7k"

# The synthetic run reports two intervals; the pin is the second, which is the
# one carrying congestion in the fixture below.
#
# Built by a FACTORY rather than held as a module-level instance, and that is
# not a style preference. test_ercot7k_results.py calls importlib.reload(er) to
# assert the module is import-silent; a reload rebuilds ReportKey in place, so
# any instance constructed before it belongs to a class that no longer exists.
# A dataclass __eq__ compares classes first, so the comparison then fails
# between two objects with IDENTICAL reprs -- which reads as a real defect and
# is not one, and only shows up when both files run in the same session.
PIN_CYCLE = "RT"
PIN_SCENARIO = "ScnRT"
PIN_INTERVAL = 2


def pin() -> er.ReportKey:
    return er.ReportKey(cycle=PIN_CYCLE, scenario=PIN_SCENARIO,
                        interval=PIN_INTERVAL)

# mini7k's branches, from tests/fixtures/mini7k/texas7k_BRN_ID.csv. The k_line
# lever refuses an unmonitored branch, so the target has to be a real monitored
# one and not a plausible name.
BASE_LOAD_MW = 200.0

# mini7k's two SCN_INJ_MAX populations, which is what k_gen's two partial modes
# split on: DERATE_GEN carries no row (275 MW nameplate, MinDispatch 25) and
# takes an absolute MaxMw; AVAIL_GEN carries a '0' forecast row and a 'ScnRT'
# actual row and takes a ScaleFactor.
DERATE_GEN = "N111333_1"
AVAIL_GEN = "N220149_1"


# ------------------------------------------------------------------------------
#   1. sweep_steps -- inherited defect 2, the dropped endpoint
# ------------------------------------------------------------------------------
def test_a_descending_sweep_keeps_its_endpoint():
    """devnet's own default preset. np.arange(1.0, 0.2 + 1e-9, -0.1) gives 8
    steps ending at 0.3 and never solves the 0.2 case -- the most interesting
    point of the sweep and the reason it was run."""
    steps = es.sweep_steps(1.0, 0.2, -0.1)
    assert len(steps) == 9
    assert steps[0] == 1.0
    assert steps[-1] == 0.2, "the endpoint is the point devnet drops"
    assert steps == [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]


@pytest.mark.parametrize("kmin,kmax,kstep,expected_last,expected_n", [
    (1.0, 0.2, -0.1, 0.2, 9),    # devnet_stress.py default preset
    (1.0, 0.5, -0.1, 0.5, 6),    # second preset
    (1.0, 0.2, -0.05, 0.2, 17),  # third preset
    (0.2, 1.0, 0.1, 1.0, 9),     # the ascending one, which devnet gets right
])
def test_every_devnet_preset_reaches_its_endpoint(kmin, kmax, kstep,
                                                  expected_last, expected_n):
    steps = es.sweep_steps(kmin, kmax, kstep)
    assert len(steps) == expected_n
    assert steps[-1] == expected_last


def test_the_values_carry_no_float_accumulation_noise():
    """0.7000000000000001 in a directory name and in a config field is how a
    resume fails to recognise the step it already solved."""
    steps = es.sweep_steps(1.0, 0.2, -0.1)
    assert all(step == round(step, 4) for step in steps)
    assert es.value_text(steps[3]) == "0.7"
    assert es.value_slug(steps[3]) == "0p7"


def test_a_zero_step_is_refused():
    with pytest.raises(es.Ercot7kSweepError, match="no sweep exists"):
        es.sweep_steps(1.0, 0.5, 0.0)


def test_a_step_running_away_from_kmax_is_refused():
    """The direction that hides the arange bug is refused, not corrected."""
    with pytest.raises(es.Ercot7kSweepError, match="runs away from kmax"):
        es.sweep_steps(1.0, 0.2, 0.1)


def test_a_range_that_is_not_a_whole_number_of_steps_is_refused():
    """np.arange truncates this silently; truncation IS the endpoint bug."""
    with pytest.raises(es.Ercot7kSweepError,
                       match="not a whole number of steps"):
        es.sweep_steps(1.0, 0.25, -0.1)


def test_the_refusal_suggests_a_range_that_is_actually_accepted():
    """The advice used to be a rounded kstep, which no longer divided the span
    -- so following it reproduced the identical message. A refusal that loops
    is worse than no advice."""
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.sweep_steps(1.0, 0.25, -0.1)
    message = str(excinfo.value)
    # Only the SUGGESTIONS, which are the ones followed by a step count -- the
    # message also restates the kmax that was refused.
    suggested = re.findall(r"kmax=([0-9.]+) \(\d+ steps\)", message)
    assert len(suggested) == 2, message
    for kmax in suggested:
        # Every suggestion must be accepted by the same function, unchanged.
        steps = es.sweep_steps(1.0, float(kmax), -0.1)
        assert steps[-1] == float(kmax)


def test_a_single_point_is_refused_because_the_witness_cannot_vary():
    with pytest.raises(es.Ercot7kSweepError, match="at least"):
        es.sweep_steps(1.0, 1.0, -0.1)


@pytest.mark.parametrize("value,decimals,expected", [
    (100.0, 0, "100"),
    (200.0, 0, "200"),
    (1.0, 0, "1"),
    (10.0, 1, "10"),
    (0.9, 4, "0.9"),
    (1.0, 4, "1"),
])
def test_value_text_never_eats_a_significant_zero(value, decimals, expected):
    """Unguarded, "%.0f" % 100.0 is "100" and rstrip("0") gives "1". That
    string is what builds the layer, so the sweep would build, solve and
    verify a factor of 1 while every label said 100 -- and the witness would
    agree, because the case file would say 1 too. Latent for the two shipped
    levers; live the moment an integer-MW lever lands."""
    assert es.value_text(value, decimals) == expected


def test_a_negative_value_slug_is_directory_safe():
    assert es.value_slug(-0.5) == "m0p5"
    assert es.step_slug("k_load", 1.2) == "k_load1p2"
    assert es.step_slug("k_load", 1.2, prefix="a-") == "a-k_load1p2"
    # A small negative at coarse precision must not become a distinct-looking
    # step that means the same as zero.
    assert es.value_text(-0.4, 0) == "0"


@pytest.mark.parametrize("bad", ["a/b", "a\\b", "..", ".", " lead", "trail ",
                                 "c:name", "a*b", "a?b", "a|b", 'a"b', "a<b",
                                 "a\tb", "a\nb", "x..", "foo."])
def test_a_sweep_id_that_is_not_a_plain_name_is_refused(mini_base, bad):
    """It becomes a directory under the sweeps root. A name the validator
    accepts and the filesystem then refuses is worse than one never checked:
    the plan prints in full and mkdir raises after the operator has been told
    it is fine. '.' is the nastiest -- it collapses the sweep directory onto
    the sweeps root, scattering sweep.json and the step records."""
    with pytest.raises(es.Ercot7kSweepError, match="directory name"):
        es.plan_sweep(parent=mini_base, lever="k_load", target="",
                      mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                      sweep_id=bad)


@pytest.mark.parametrize("ok", ["a..b", "..y", "k_line-run.2", "sweep-1"])
def test_a_plain_name_containing_dots_is_accepted(mini_base, ok):
    """os.pardir was tested as a SUBSTRING, so legal names were refused.

    Note "x.." is NOT in this list and is refused by the trailing-dot rule
    instead: Windows strips a trailing dot, so it would silently share a
    directory with "x". The two rules looked like they disagreed; the
    trailing-dot one is right.
    """
    plan = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                         mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                         sweep_id=ok)
    assert plan.sweep_id == ok


def test_a_directory_the_filesystem_refuses_is_a_refusal_not_a_traceback(
        mini_base, tmp_path, monkeypatch, capsys):
    """Whatever the validator has not thought of, the filesystem has an
    opinion about, and it must not arrive as a stack trace after the plan has
    printed."""
    def boom(*args, **kwargs):
        raise OSError(123, "The filename, directory name, or volume label "
                           "syntax is incorrect")

    monkeypatch.setattr(es.Path, "mkdir", boom)
    code = es.main(["run", "--parent", str(mini_base), "--lever", "k_load",
                    "--kmin", "1.0", "--kmax", "1.2", "--kstep", "0.1",
                    "--sweeps-root", str(tmp_path / "sweeps"),
                    "--derived-root", str(tmp_path / "derived"),
                    "--runs-root", str(tmp_path / "runs"),
                    "--sweep-id", "fs", "--skip-disk-check"])
    assert code == 2, "a directory that cannot be made is a refusal to start"
    assert "AMW-ERR" in capsys.readouterr().err


def test_run_directories_also_sort_numerically_past_ninety_nine():
    plan = _plan()
    names = [plan.run_name(i, 1.0) for i in (9, 10, 99, 100)]
    assert names == sorted(names)


# ------------------------------------------------------------------------------
#   2. Which levers can be swept
# ------------------------------------------------------------------------------
def test_k_gen_outage_is_refused_with_the_reason_rather_than_ignored():
    """Outage is a BIT: the mode takes 1 and nothing else, so its value axis
    has one admissible point. Refusing it names what would be sweepable."""
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.witness_for("k_gen", "outage")
    message = str(excinfo.value)
    assert "cannot be swept" in message
    assert "k_line/scale" in message and "k_gen/derate" in message


def test_the_witness_is_chosen_by_mode_and_not_by_lever_alone():
    """k_gen writes SCN_INJ_OUT in one mode and SCN_INJ_MAX in the others. A
    witness keyed by lever would read an injector limit for a sweep that wrote
    an outage bit, and agree with itself about a case it never described."""
    assert es.witness_for("k_gen", "derate").column == "ED_Inj.Max"
    assert es.witness_for("k_gen", "avail").column == "ED_Inj.Max"
    assert es.witness_for("k_line", "scale").column == "PN_Pth.Max"
    assert ("k_gen", "outage") not in es.WITNESSES


def test_the_two_partial_modes_differ_in_kind_and_say_why():
    """'derate' writes an absolute MW the results echo in MW, so it can be
    compared against the case file. 'avail' writes a factor on a schedule, so
    the level is only known up to that factor and the check is relative."""
    assert es.witness_for("k_gen", "derate").kind == "absolute"
    assert es.witness_for("k_gen", "avail").kind == "proportional"


def test_an_unimplemented_lever_is_refused_naming_both_lists():
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.witness_for("mc_bus", "scale")
    assert "not implemented at all" in str(excinfo.value)


def test_an_unimplemented_mode_is_refused_before_the_witness_is_chosen():
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.witness_for("k_line", "derate")
    assert "does not implement mode" in str(excinfo.value)


def test_every_sweepable_pair_is_also_a_real_lever_and_mode():
    """A witness for a lever or mode ercot7k_case.py does not implement would
    be a sweep that cannot build its first layer."""
    for lever, mode in es.SWEEPABLE:
        assert lever in ec.STRESS_LEVERS
        assert mode in ec.STRESS_LEVERS[lever]["modes"]


# ------------------------------------------------------------------------------
#   3. The step row -- inherited defect 1, the unapplied sweep variable
# ------------------------------------------------------------------------------
def test_the_step_value_reaches_the_config_row():
    """devnet's loop variable labels the output row and is never applied. Here
    it goes into the one field a layer can be built from."""
    rows = es.build_step_rows("k_line", "BR1", "scale", 0.9)
    assert rows == [{"lever": "k_line", "target": "BR1", "mode": "scale",
                     "value": "0.9"}]


def test_the_step_value_survives_into_the_built_case_file(mini_base, tmp_path):
    """End of the chain that defect 1 breaks: config row -> delta -> case."""
    branch = _monitored_branch(mini_base)
    layer = tmp_path / "layer"
    ec.build_stress_layer(mini_base, layer,
                          es.build_step_rows("k_line", branch, "scale", 0.9),
                          slug="k_line0p9")
    written = es.written_witness("k_line", "scale", branch, layer)
    base_limit = _branch_limit(mini_base, branch)
    assert written == pytest.approx(base_limit * 0.9)


# ------------------------------------------------------------------------------
#   Fixtures
# ------------------------------------------------------------------------------
@pytest.fixture
def mini_base(tmp_path: Path) -> Path:
    """A writable copy of the mini7k case, pinned before anything is built.

    The pin is written FIRST on purpose: study.json is part of the case digest,
    so adding one to a case that already has children makes walk_chain() reject
    the children as hand-edited.
    """
    base = tmp_path / "mini7k"
    shutil.copytree(MINI_DIR, base)
    er.write_study(base, pin())
    return base


def _monitored_branch(case_dir: Path) -> str:
    prefix = ec.case_prefix(case_dir)
    table = ec.read_table(case_dir / ("%s_BRN_ID.csv" % prefix))
    for record in table.records():
        if (record.get("Monitor") or "").strip() in ("1", "1.0"):
            return record["Branch"]
    raise AssertionError("the mini7k fixture has no Monitor=1 branch")


def _branch_limit(case_dir: Path, branch: str) -> float:
    prefix = ec.case_prefix(case_dir)
    table = ec.read_table(case_dir / ("%s_BRN_ID.csv" % prefix))
    for record in table.records():
        if record["Branch"] == branch:
            return float(record["NormalLimit"])
    raise AssertionError("branch %s is not in BRN_ID" % branch)


def _area_scale(layer: Path) -> float:
    prefix = ec.case_prefix(layer)
    table = ec.read_table(layer / ("%s_SCN_ARA_LOD.csv" % prefix))
    values = {(r.get("ScaleFactor") or "").strip() for r in table.records()}
    assert len(values) == 1, "V6 should have refused an uneven ScaleFactor"
    return float(values.pop())


def write_fake_results(results_dir: Path, load_mw: float,
                       path_name: str = "P1",
                       limit_mw: float = 100.0,
                       report_path: bool = True,
                       max_enforced: int = 1,
                       min_enforced: int = 0,
                       with_enforced_column: bool = True,
                       gen_name: str = "GEN_A",
                       gen_max_mw: float = 500.0,
                       gen_cap_mw: float = 500.0,
                       gen_p_mw: float = 180.0,
                       gen_limit_violation_mw: float = 0.0,
                       report_gen: bool = True) -> None:
    """
    A two-interval run in the shape ercot7k_results.py reads.

    Modelled on the synthetic directory in test_ercot7k_results.py. The three
    numbers this driver reads back are parameters: area load (the k_load
    witness), the path limit (the k_line witness) and the injector dispatch
    limit (the k_gen one).
    """
    results_dir.mkdir(parents=True, exist_ok=True)

    def write(table: str, header: str, lines: list) -> None:
        (results_dir / ("results_%s.csv" % table)).write_text(
            "\n".join(["//" + header] + lines) + "\n",
            encoding="ascii", newline="",
        )

    write("MC_Solution", "slv,cyc,hrzn,Status,Objective",
          ["1,RT,hrzn_1,Optimal,1000.000", "2,RT,hrzn_2,Optimal,2000.000"])
    write("MC_Hrzn", "cyc,scn,hrzn,FirstInterval,DeltaCost",
          ["RT,ScnRT,hrzn_1,1,1000.000", "RT,ScnRT,hrzn_2,2,2000.000"])
    write("ED_Ara", "cyc,scn,ara,int,Load,Violation,Penalty",
          ["RT,ScnRT,0,1,%.3f,0.000,0.000" % (load_mw / 2.0),
           "RT,ScnRT,0,2,%.3f,0.000,0.000" % load_mw])
    write("PF_AraNde", "ste,ara,nde,GenFactor,LoadFactor,ResidualLF",
          ["0,0,NA,0.500,0.500,0.000", "0,0,NB,0.500,0.500,0.000"])
    write("PC_Nd", "cyc,scn,nd,int,LMP",
          ["RT,ScnRT,NA,1,20.000", "RT,ScnRT,NA,2,30.000",
           "RT,ScnRT,NB,1,25.000", "RT,ScnRT,NB,2,90.000",
           "RT,ScnRT,Reference_0,1,20.000", "RT,ScnRT,Reference_0,2,20.000"])
    # Column order follows the real results header, which carries MaxEnforced
    # between Violation and Binding. with_enforced_column drops it, to stand
    # for an older results set that cannot answer the enforcement question.
    if with_enforced_column:
        pth_header = ("cyc,scn,pth,int,Mw,Min,Max,Violation,MinEnforced,"
                      "MaxEnforced,Binding,Penalty,SP,SAC")
        enf = "%d,%d," % (min_enforced, max_enforced)
    else:
        pth_header = "cyc,scn,pth,int,Mw,Min,Max,Violation,Binding,Penalty,SP,SAC"
        enf = ""
    if report_path:
        pth_rows = [
            "RT,ScnRT,%s,1,50.000,-%.3f,%.3f,0.000,%s0,0.000,0.000,0"
            % (path_name, limit_mw, limit_mw, enf),
            "RT,ScnRT,%s,2,%.3f,-%.3f,%.3f,0.000,%s1,0.000,17.500,1"
            % (path_name, limit_mw, limit_mw, limit_mw, enf),
        ]
    else:
        # A run that reports SOME other path but not the one being swept: the
        # reporting-scope case from section 5f of the task notes.
        pth_rows = [
            "RT,ScnRT,OTHER,1,50.000,-100.000,100.000,0.000,%s0,0.000,0.000,0"
            % enf,
            "RT,ScnRT,OTHER,2,60.000,-100.000,100.000,0.000,%s0,0.000,0.000,0"
            % enf,
        ]
    write("PN_Pth", pth_header, pth_rows)
    # Cap sits beside Max as it does in the real header. It is what separates a
    # unit capped by the lever from one the solve left uncommitted, which
    # reports Max=0 under a full Cap.
    inj_rows = ["RT,ScnRT,GEN_OTHER,1,100.000,500.000,500.000,0.000,0.000,"
                "0.000,0.000",
                "RT,ScnRT,GEN_OTHER,2,180.000,500.000,500.000,0.000,0.000,"
                "0.000,0.000"]
    if report_gen:
        inj_rows += [
            "RT,ScnRT,%s,1,%.3f,%.3f,%.3f,0.000,0.000,0.000,0.000"
            % (gen_name, min(gen_p_mw, gen_max_mw), gen_max_mw, gen_cap_mw),
            "RT,ScnRT,%s,2,%.3f,%.3f,%.3f,0.000,%.3f,0.000,0.000"
            % (gen_name, gen_p_mw, gen_max_mw, gen_cap_mw,
               gen_limit_violation_mw),
        ]
    write("ED_Inj",
          "cyc,scn,inj,int,P,Max,Cap,Min,LimitViolation,RampViolation,Penalty",
          inj_rows)


# ------------------------------------------------------------------------------
#   4. Reading the witness back
# ------------------------------------------------------------------------------
def test_the_k_load_witness_is_the_area_load_at_the_pinned_interval(tmp_path):
    results = tmp_path / "results"
    write_fake_results(results, load_mw=220.0)
    witness, enforced = es.read_witness("k_load", "scale", "", results, pin())
    assert witness == pytest.approx(220.0)
    assert math.isnan(enforced), "enforcement is not a question for area load"


def test_the_k_line_witness_is_the_path_limit_at_the_pinned_interval(tmp_path):
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, path_name="BR1", limit_mw=90.0)
    witness, enforced = es.read_witness("k_line", "scale", "BR1", results,
                                        pin())
    assert witness == pytest.approx(90.0)
    assert enforced == 1.0


def test_an_unreported_path_is_not_measured_and_never_a_limit_of_zero(tmp_path):
    """0.0 would read as 'limits are ignored', which is a documented PSO
    meaning and the opposite of 'we did not see it'."""
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, path_name="BR1",
                       report_path=False)
    witness, enforced = es.read_witness("k_line", "scale", "BR1", results,
                                        pin())
    assert math.isnan(witness)
    assert math.isnan(enforced)


def test_a_limit_enforced_on_its_MIN_side_counts_as_enforced(tmp_path):
    """NormalLimit is bi-directional, so which side is enforced follows the
    direction of flow. MEASURED on the committed reference run: the study's
    own corridor N210144_N210332_1 is MinEnforced in 168 of 168 RT intervals
    and MaxEnforced in none, because flow runs Riesel to Hewitt against the
    negative limit. A check reading only MaxEnforced would have called the
    case's most persistent constraint unenforced and failed the one sweep
    already validated by hand."""
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, path_name="BR1", limit_mw=90.0,
                       min_enforced=1, max_enforced=0)
    witness, enforced = es.read_witness("k_line", "scale", "BR1", results,
                                        pin())
    assert witness == pytest.approx(90.0)
    assert enforced == 1.0


def test_a_limit_reported_but_not_enforced_is_read_as_not_enforced(tmp_path):
    """PN_Pth.md: Max is the limit, MaxEnforced says whether it was in the
    solution. The committed reference run is mostly rows of exactly this
    shape -- the limit echoed back from the file, having played no part in
    dispatch."""
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, path_name="BR1", limit_mw=90.0,
                       min_enforced=0, max_enforced=0)
    witness, enforced = es.read_witness("k_line", "scale", "BR1", results,
                                        pin())
    assert witness == pytest.approx(90.0), "the limit is still reported"
    assert enforced == 0.0, "but it was not in the LP on either side"


def test_results_without_a_maxenforced_column_report_unknown_not_false(
        tmp_path):
    """'this results set cannot answer' and 'the limit was not enforced' are
    different findings; manufacturing the second from the first is the whole
    silent-failure class."""
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, path_name="BR1", limit_mw=90.0,
                       with_enforced_column=False)
    witness, enforced = es.read_witness("k_line", "scale", "BR1", results,
                                        pin())
    assert witness == pytest.approx(90.0)
    assert math.isnan(enforced)


# ------------------------------------------------------------------------------
#   4b. The third witness -- k_gen against SCN_INJ_MAX (T4 lever 3)
# ------------------------------------------------------------------------------
def test_the_k_gen_derate_witness_is_the_injector_limit_at_the_pin(tmp_path):
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, gen_name="G1",
                       gen_max_mw=200.0, gen_cap_mw=312.0, gen_p_mw=150.0)
    witness, respected = es.read_witness("k_gen", "derate", "G1", results,
                                         pin())
    assert witness == pytest.approx(200.0)
    assert respected == 1.0, "dispatch stayed under the cap"


def test_an_injector_absent_from_the_results_is_not_measured(tmp_path):
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, report_gen=False)
    witness, respected = es.read_witness("k_gen", "derate", "G1", results,
                                         pin())
    assert math.isnan(witness)
    assert math.isnan(respected)


def test_a_zero_dispatch_limit_is_not_measured_and_never_a_cap_of_zero(
        tmp_path):
    """
    MEASURED on the validated run: N111180_1 carries 746 MW of nameplate and
    reports Max=0 in 125 of 168 RT intervals, the pinned one included, because
    ED_Inj.md sets Max to zero when a unit is "unavailable for commitment".
    No admissible step can ask for a cap of zero -- a zero MaxMw without
    Enforce is ignored, and both partial modes refuse the value -- so a zero
    here is an unavailable unit.

    Read as a number it is the worst possible reading: constant at zero across
    every step of a sweep, which W2 reports as the lever never having been
    applied at all.
    """
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, gen_name="G1",
                       gen_max_mw=0.0, gen_cap_mw=746.0, gen_p_mw=0.0)
    witness, respected = es.read_witness("k_gen", "derate", "G1", results,
                                         pin())
    assert math.isnan(witness)
    assert math.isnan(respected)


@pytest.mark.parametrize("p_mw,violation,why", [
    (260.0, 0.0, "dispatch above the cap"),
    (150.0, 60.0, "a reported LimitViolation"),
])
def test_a_cap_the_solution_overshot_is_reported_as_not_respected(
        tmp_path, p_mw: float, violation: float, why: str):
    """
    W6's question in this table's terms. PSO's injector dispatch limits are
    SOFT slacks, so a cap that reached the report without constraining the
    solve shows up as dispatch above it rather than as an infeasibility -- and
    the limit would otherwise be echoed back from the case file, agreeing with
    W3 to the digit while having been bought out.
    """
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0, gen_name="G1",
                       gen_max_mw=200.0, gen_cap_mw=312.0, gen_p_mw=p_mw,
                       gen_limit_violation_mw=violation)
    witness, respected = es.read_witness("k_gen", "derate", "G1", results,
                                         pin())
    assert witness == pytest.approx(200.0), "the cap is still reported"
    assert respected == 0.0, why


def test_the_derate_witness_is_read_back_from_the_layer_not_recomputed(
        mini_base, tmp_path):
    """The absolute check compares two independent artifacts: the MW the case
    file states and the MW the results report. Recomputing the first from the
    step value would test this module's arithmetic against itself."""
    layer = tmp_path / "layer"
    ec.build_stress_layer(
        mini_base, layer,
        es.build_step_rows("k_gen", DERATE_GEN, "derate", 200.0),
        slug="k_gen200")
    written = es.written_witness("k_gen", "derate", DERATE_GEN, layer)
    assert written == pytest.approx(200.0)

    rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
    assert [r for r in rows
            if r["Injector"] == DERATE_GEN and r["MaxMw"] == "200.000"]


def test_the_avail_mode_has_no_written_witness_because_it_writes_a_factor(
        mini_base, tmp_path):
    """A ScaleFactor is not in the witness's units: the results echo
    factor x schedule, and the schedule is not in the case file the sweep
    wrote. That is exactly what 'proportional' means, and claiming an absolute
    comparison here would compare MW against a multiplier."""
    layer = tmp_path / "layer"
    ec.build_stress_layer(
        mini_base, layer,
        es.build_step_rows("k_gen", AVAIL_GEN, "avail", 0.8),
        slug="k_gen0p8")
    assert math.isnan(es.written_witness("k_gen", "avail", AVAIL_GEN, layer))


# ------------------------------------------------------------------------------
#   4c. Refusing a sweep the case cannot express, at PLAN time
# ------------------------------------------------------------------------------
def test_a_derate_of_a_scheduled_injector_is_refused_before_any_solve(
        mini_base):
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.plan_sweep(mini_base, "k_gen", AVAIL_GEN, "derate",
                      kmin=200.0, kmax=100.0, kstep=-50.0)
    message = str(excinfo.value)
    assert "avail" in message and "_fcst" in message


def test_an_avail_sweep_of_an_unscheduled_injector_is_refused(mini_base):
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.plan_sweep(mini_base, "k_gen", DERATE_GEN, "avail",
                      kmin=1.0, kmax=0.8, kstep=-0.1)
    assert "derate" in str(excinfo.value)


def test_steps_above_the_nameplate_are_refused_as_a_plateau_not_a_sweep(
        mini_base):
    """SCN_INJ_MAX can only restrict, so every step above INJ_ID.MaxMw reports
    the same dispatch limit. In a response curve that reads as a lever that
    saturated rather than as a case that refused the input."""
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.plan_sweep(mini_base, "k_gen", DERATE_GEN, "derate",
                      kmin=400.0, kmax=200.0, kstep=-50.0)
    message = str(excinfo.value)
    assert "275" in message and "SAME dispatch limit" in message


def test_steps_below_the_commitment_floor_are_refused(mini_base):
    """VERIFIED, SCN_INJ_MAX.md: the limit cannot be more restrictive than
    INJ_CMT.MinDispatch."""
    with pytest.raises(es.Ercot7kSweepError, match="MinDispatch"):
        es.plan_sweep(mini_base, "k_gen", DERATE_GEN, "derate",
                      kmin=100.0, kmax=10.0, kstep=-30.0)


def test_an_avail_step_above_one_is_refused(mini_base):
    with pytest.raises(es.Ercot7kSweepError, match="above 1"):
        es.plan_sweep(mini_base, "k_gen", AVAIL_GEN, "avail",
                      kmin=1.2, kmax=0.8, kstep=-0.2)


def test_a_valid_derate_sweep_plans_and_carries_its_witness(mini_base):
    plan = es.plan_sweep(mini_base, "k_gen", DERATE_GEN, "derate",
                         kmin=275.0, kmax=175.0, kstep=-50.0)
    assert plan.values == [275.0, 225.0, 175.0]
    assert plan.witness.column == "ED_Inj.Max"
    assert plan.as_dict()["witness"]["kind"] == "absolute"
    assert plan.as_dict()["witness"]["enforcement"] == "respected"


# ------------------------------------------------------------------------------
#   5. The verdict
# ------------------------------------------------------------------------------
def _plan(lever="k_load", target="", values=(1.0, 1.1, 1.2),
          mode="scale") -> es.SweepPlan:
    return es.SweepPlan(
        sweep_id="t", parent=Path("parent"), lever=lever, target=target,
        mode=mode, values=list(values), key=pin(), pinned_by=Path("parent"),
    )


def _outcome(index, value, witness, written=math.nan, status="Optimal",
             enforced=math.nan, lever="k_load"):
    # The slug must be the one the plan would produce, or W7 correctly reports
    # the record as belonging to a different sweep -- which is exactly what it
    # is for. Pass lever="k_line" alongside a k_line plan.
    return es.StepOutcome(index=index, value=value,
                          slug=es.step_slug(lever, value), returncode=0,
                          witness=witness, witness_written=written,
                          witness_enforced=enforced, status=status)


def _kline_outcomes(rows):
    """[(index, value, witness, written, enforced), ...] -> outcomes."""
    return [_outcome(i, v, w, written=wr, enforced=en, lever="k_line")
            for i, v, w, wr, en in rows]


def _levels(findings, check):
    return [f.level for f in findings if f.check == check]


def test_a_constant_witness_is_reported_as_a_sweep_that_did_not_happen():
    """THE test. This is devnet's defect 1 exactly: three steps, three labels,
    one case. Every response column would be self-consistent and wrong."""
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 200.0),
                _outcome(3, 1.2, 200.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W2") == [ec.LEVEL_ERROR]
    assert ec.has_errors(findings)
    message = next(f.message for f in findings if f.check == "W2")
    assert "did not happen" in message


def test_a_witness_that_tracks_the_lever_passes_every_check():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert _levels(findings, "W3") == [ec.LEVEL_OK]
    assert _levels(findings, "W4") == [ec.LEVEL_OK]


def test_a_witness_that_moves_by_the_wrong_amount_fails_the_ratio_check():
    """Moving is not enough: a lever that applied on some steps and not others
    passes W2 and has to be caught here."""
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 200.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W2") == [ec.LEVEL_OK], "it did vary"
    assert _levels(findings, "W3") == [ec.LEVEL_ERROR]


def test_an_absolute_witness_is_checked_against_what_the_layer_wrote():
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, 1.0),
                                (2, 0.9, 100.0, 90.0, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W3") == [ec.LEVEL_ERROR]
    message = next(f.message for f in findings if f.check == "W3")
    assert "case wrote 90.000, results report 100.000" in message


def test_some_steps_unmeasured_warns_and_says_they_are_unverified():
    """W1 used to ERROR here while its own message said the absence "is NOT by
    itself evidence of a broken sweep" -- a check contradicting its own text,
    and one that would hard-fail the very shape of sweep worth running (a
    corridor slack at the top of the range, binding at the bottom)."""
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, math.nan, 100.0, math.nan),
                                (2, 0.9, 90.0, 90.0, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W1") == [ec.LEVEL_WARNING]
    message = next(f.message for f in findings if f.check == "W1")
    assert "UNVERIFIED" in message
    assert "reporting scope" in message
    assert not ec.has_errors(findings)


def test_no_step_measured_at_all_is_still_an_error():
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, math.nan, 100.0, math.nan),
                                (2, 0.9, math.nan, 90.0, math.nan)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W1") == [ec.LEVEL_ERROR]
    assert ec.has_errors(findings)


def test_a_non_monotone_witness_warns_without_failing_the_sweep():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 190.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W4") == [ec.LEVEL_WARNING]


def test_a_record_the_plan_never_asked_for_is_caught_on_an_absolute_lever():
    """W3 compares two fields of the SAME record, so on an absolute lever a
    record carrying a value nobody requested agrees with itself and passes.
    W7 is the only check that asks whether the records are the plan's."""
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, 1.0),
                                (2, 0.5, 50.0, 50.0, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W3") == [ec.LEVEL_OK], "it agrees with itself"
    assert _levels(findings, "W7") == [ec.LEVEL_ERROR]
    assert ec.has_errors(findings)


def test_an_extra_step_record_is_not_silently_absorbed():
    plan = _plan(values=(1.0, 1.1))
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W7") == [ec.LEVEL_ERROR]
    assert "3 step records" in next(f.message for f in findings
                                    if f.check == "W7")


def test_a_sweep_that_stopped_early_is_a_prefix_not_a_mismatch():
    """A correct prefix is not a correspondence failure -- W0 already reports
    the hole accurately, and W7 saying "nothing below this is about the sweep
    that was asked for" would be the driver claiming more than it knows."""
    plan = _plan(values=(1.0, 1.1, 1.2))
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W7") == [ec.LEVEL_OK]
    assert "stopped early" in next(f.message for f in findings
                                   if f.check == "W7")
    assert _levels(findings, "W0") == [ec.LEVEL_ERROR], "W0 carries the hole"


def test_no_completed_steps_skips_every_witness_check_not_just_w1():
    """The two SKIP blocks must stay in step: this one is the path nothing
    pinned, so it was free to drift from its twin."""
    plan = _plan(values=(1.0, 1.1))
    failed = es.StepOutcome(index=1, value=1.0, slug=es.step_slug("k_load",
                                                                  1.0),
                            returncode=1, error="exit 1")
    findings = es.check_sweep(plan, [failed])
    for check in ("W1", "W2", "W3", "W4", "W6"):
        assert _levels(findings, check) == [ec.LEVEL_SKIP], check
    assert es.verdict_exit_code(findings) == 1


def test_records_matching_the_plan_pass_w7():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W7") == [ec.LEVEL_OK]


def test_a_partial_sweep_is_an_error_because_the_curve_has_holes():
    plan = _plan()
    failed = es.StepOutcome(index=3, value=1.2, slug="k1p2", returncode=1,
                            error="exit 1")
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0), failed]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W0") == [ec.LEVEL_ERROR]


def test_fewer_than_two_steps_skips_the_witness_check_and_says_so():
    """A SKIP that reads as a pass is how a missing check hides."""
    plan = _plan(values=(1.0, 1.1))
    outcomes = [_outcome(1, 1.0, 200.0)]
    findings = es.check_sweep(plan, outcomes)
    skip = next(f for f in findings if f.check == "W1")
    assert skip.level == ec.LEVEL_SKIP
    assert "not a pass" in skip.message


def test_a_limit_never_enforced_at_any_step_fails_even_though_w3_passes():
    """W3 asks whether the results echo the case; W6 asks whether that value
    was ever in the LP. With ReportAllSolvedPaths a k_line sweep can echo its
    own CSV perfectly at every step while the derate changed nothing."""
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9, 0.8))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, 0.0),
                                (2, 0.9, 90.0, 90.0, 0.0),
                                (3, 0.8, 80.0, 80.0, 0.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W3") == [ec.LEVEL_OK], "it echoes perfectly"
    assert _levels(findings, "W2") == [ec.LEVEL_OK], "and it does vary"
    assert _levels(findings, "W6") == [ec.LEVEL_ERROR], "but it never bound"
    assert ec.has_errors(findings)


def test_a_limit_enforced_on_some_steps_warns_rather_than_failing():
    """A corridor slack at k=1.0 and binding at k=0.8 is a GOOD sweep --
    failing its first step would punish the experiment worth running."""
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9, 0.8))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, 0.0),
                                (2, 0.9, 90.0, 90.0, 1.0),
                                (3, 0.8, 80.0, 80.0, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W6") == [ec.LEVEL_WARNING]
    assert not ec.has_errors(findings)


def test_enforcement_unknown_warns_and_does_not_claim_the_lever_reached_the_lp():
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, math.nan),
                                (2, 0.9, 90.0, 90.0, math.nan)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W6") == [ec.LEVEL_WARNING]
    assert "MaxEnforced" in next(f.message for f in findings if f.check == "W6")


def test_enforcement_is_not_a_question_for_a_proportional_lever():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W6") == [ec.LEVEL_SKIP]
    assert not ec.has_errors(findings)


def _kgen_outcomes(rows, mode="derate"):
    """[(index, value, witness, written, respected), ...] -> outcomes."""
    return [_outcome(i, v, w, written=wr, enforced=en, lever="k_gen")
            for i, v, w, wr, en in rows]


def test_a_derate_sweep_checks_the_cap_against_the_mw_the_layer_wrote():
    """The absolute form: the case file's MW against the result file's MW, two
    independent artifacts, with no reference step."""
    plan = _plan(lever="k_gen", target="G1", mode="derate",
                 values=(275.0, 225.0, 175.0))
    outcomes = _kgen_outcomes([(1, 275.0, 275.0, 275.0, 1.0),
                               (2, 225.0, 225.0, 225.0, 1.0),
                               (3, 175.0, 175.0, 175.0, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert _levels(findings, "W3") == [ec.LEVEL_OK]
    assert _levels(findings, "W6") == [ec.LEVEL_OK]


def test_a_derate_the_solution_overshot_fails_w6_even_though_w3_passes():
    """The k_gen twin of the k_line enforcement case. The cap is echoed back
    from the case file at every step -- W3 is perfectly green -- while the
    solve dispatched through it and paid the slack instead."""
    plan = _plan(lever="k_gen", target="G1", mode="derate",
                 values=(275.0, 225.0, 175.0))
    outcomes = _kgen_outcomes([(1, 275.0, 275.0, 275.0, 1.0),
                               (2, 225.0, 225.0, 225.0, 0.0),
                               (3, 175.0, 175.0, 175.0, 0.0)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W3") == [ec.LEVEL_OK], "it echoes perfectly"
    assert _levels(findings, "W6") == [ec.LEVEL_ERROR]
    assert ec.has_errors(findings)


def test_an_avail_sweep_is_checked_as_a_ratio_and_still_asks_about_dispatch():
    """'avail' scales a schedule, so the level is known only up to the factor
    and W3 is relative -- but W6 is NOT skipped the way it is for k_load: a
    scaled schedule can be overshot exactly as a cap can."""
    plan = _plan(lever="k_gen", target="G1", mode="avail",
                 values=(1.0, 0.9, 0.8))
    outcomes = _kgen_outcomes([(1, 1.0, 100.0, math.nan, 1.0),
                               (2, 0.9, 90.0, math.nan, 1.0),
                               (3, 0.8, 80.0, math.nan, 1.0)])
    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert _levels(findings, "W3") == [ec.LEVEL_OK]
    assert _levels(findings, "W6") == [ec.LEVEL_OK]


def test_a_derate_witness_missing_at_the_pin_names_the_uncommitted_unit():
    """The W1 message has to send the operator to the right place: ED_Inj
    reports every injector, so an absent witness here is not the PN_Pth
    reporting-scope problem -- it is a unit that was off at the pinned hour."""
    plan = _plan(lever="k_gen", target="G1", mode="derate",
                 values=(275.0, 225.0))
    outcomes = _kgen_outcomes([(1, 275.0, math.nan, 275.0, math.nan),
                               (2, 225.0, math.nan, 225.0, math.nan)])
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W1") == [ec.LEVEL_ERROR]
    message = next(f.message for f in findings if f.check == "W1")
    assert "committed" in message and "G1" in message


def test_a_non_optimal_step_warns_rather_than_failing():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0, status="Infeasible")]
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W5") == [ec.LEVEL_WARNING]


# ------------------------------------------------------------------------------
#   6. The loop, end to end, against a real case layer
# ------------------------------------------------------------------------------
def _honest_solver(runs_root: Path):
    """
    A fake PSO that HONOURS the case it is handed: it reads the layer's own
    SCN_ARA_LOD.ScaleFactor and scales the reported load by it.

    That is what makes this an end-to-end test rather than a circular one. The
    chain under test is config row -> stress_deltas -> case file -> results ->
    witness -> verdict, and only the solve itself is faked.
    """
    def run_fn(case_csv, run_name, root):
        layer = Path(case_csv).parent
        results = Path(runs_root) / run_name / "results"
        write_fake_results(results, load_mw=BASE_LOAD_MW * _area_scale(layer))
        return 0, results, 0.5
    return run_fn


def _deaf_solver(runs_root: Path):
    """A fake PSO with devnet's defect: it ignores the case entirely."""
    def run_fn(case_csv, run_name, root):
        results = Path(runs_root) / run_name / "results"
        write_fake_results(results, load_mw=BASE_LOAD_MW)
        return 0, results, 0.5
    return run_fn


def _honest_derate_solver(runs_root: Path):
    """
    The same idea for k_gen: a fake PSO that reads the layer's own
    SCN_INJ_MAX.MaxMw and reports it back as ED_Inj.Max, dispatching under it.

    This is the chain the two scripts share, so it is the one place a step
    value that reached the config row but not the case file would show.
    """
    def run_fn(case_csv, run_name, root):
        layer = Path(case_csv).parent
        rows = ec.read_table(layer / "texas7k_SCN_INJ_MAX.csv").records()
        cap = next(float(r["MaxMw"]) for r in rows
                   if r["Injector"] == DERATE_GEN and r["MaxMw"])
        results = Path(runs_root) / run_name / "results"
        write_fake_results(results, load_mw=BASE_LOAD_MW,
                           gen_name=DERATE_GEN, gen_max_mw=cap,
                           gen_cap_mw=275.0, gen_p_mw=cap / 2.0)
        return 0, results, 0.5
    return run_fn


def _sweep_plan_for(mini_base: Path) -> es.SweepPlan:
    return es.plan_sweep(parent=mini_base, lever="k_load", target="",
                         mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                         sweep_id="unit")


def test_the_whole_loop_carries_a_derate_from_the_config_row_to_the_verdict(
        mini_base, tmp_path):
    """T4 lever 3 end to end: config row -> stress_deltas -> SCN_INJ_MAX ->
    results -> witness -> verdict, with only the solve faked."""
    runs = tmp_path / "runs"
    plan = es.plan_sweep(parent=mini_base, lever="k_gen", target=DERATE_GEN,
                         mode="derate", kmin=275.0, kmax=175.0, kstep=-50.0,
                         sweep_id="kgen")
    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_honest_derate_solver(runs))

    assert all(o.ok() for o in outcomes), [o.error for o in outcomes]
    assert [round(o.witness, 3) for o in outcomes] == [275.0, 225.0, 175.0]
    # The layer is read for the expected value, not recomputed from the step.
    assert [round(o.witness_written, 3) for o in outcomes] == [275.0, 225.0,
                                                               175.0]
    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), ec.format_findings(findings)
    assert _levels(findings, "W3") == [ec.LEVEL_OK]
    assert _levels(findings, "W6") == [ec.LEVEL_OK]


def test_the_loop_catches_a_solver_that_ignores_a_derate(mini_base, tmp_path):
    """devnet's defect 1 on the new lever: the steps are labelled and the case
    is not applied. The witness is constant, and W2 says so."""
    runs = tmp_path / "runs"
    plan = es.plan_sweep(parent=mini_base, lever="k_gen", target=DERATE_GEN,
                         mode="derate", kmin=275.0, kmax=175.0, kstep=-50.0,
                         sweep_id="kgendeaf")

    def deaf(case_csv, run_name, root):
        results = Path(runs) / run_name / "results"
        write_fake_results(results, load_mw=BASE_LOAD_MW, gen_name=DERATE_GEN,
                           gen_max_mw=275.0, gen_cap_mw=275.0, gen_p_mw=100.0)
        return 0, results, 0.5

    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=deaf)
    assert all(o.ok() for o in outcomes), "every step 'succeeded'"
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W2") == [ec.LEVEL_ERROR]
    assert ec.has_errors(findings)


def test_the_whole_loop_builds_solves_maps_and_passes(mini_base, tmp_path):
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_honest_solver(runs))

    assert [o.index for o in outcomes] == [1, 2, 3]
    assert all(o.ok() for o in outcomes), [o.error for o in outcomes]
    # 200, 220, 240 -- the load the layers actually asked for.
    assert [round(o.witness, 3) for o in outcomes] == [200.0, 220.0, 240.0]

    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), ec.format_findings(findings)


def test_the_loop_catches_a_solver_that_ignores_the_case(mini_base, tmp_path):
    """The failure devnet's summary CSV cannot show, shown."""
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_deaf_solver(runs))

    assert all(o.ok() for o in outcomes), "every step 'succeeded'"
    findings = es.check_sweep(plan, outcomes)
    assert _levels(findings, "W2") == [ec.LEVEL_ERROR]


def test_each_step_is_recorded_as_it_finishes(mini_base, tmp_path):
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=tmp_path / "derived",
                 runs_root=runs, run_fn=_honest_solver(runs))

    sweep_dir = sweeps / "unit"
    assert (sweep_dir / es.SWEEP_NAME).is_file()
    records = sorted(sweep_dir.glob("step_*.json"))
    assert [p.name for p in records] == ["step_001.json", "step_002.json",
                                         "step_003.json"]
    payload = json.loads(records[1].read_text("ascii"))
    assert payload["value"] == 1.1
    assert payload["witness"] == pytest.approx(220.0)


def test_step_records_sort_numerically_past_ninety_nine():
    """At two digits step_100 sorts before step_99 and read_outcomes silently
    reorders the curve. A 17-step sweep is already among the presets."""
    names = [es.step_record_name(i) for i in (9, 10, 99, 100, 101)]
    assert names == sorted(names)


def test_a_resume_reuses_finished_steps_and_does_not_resolve_them(
        mini_base, tmp_path):
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs))

    calls = []

    def counting_run_fn(case_csv, run_name, root):
        calls.append(run_name)
        return _honest_solver(runs)(case_csv, run_name, root)

    outcomes = es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                            runs_root=runs, run_fn=counting_run_fn,
                            resume=True)
    assert calls == [], "every step was already recorded"
    assert [round(o.witness, 3) for o in outcomes] == [200.0, 220.0, 240.0]


def test_a_second_sweep_over_the_same_layers_is_refused_without_resume(
        mini_base, tmp_path):
    """Layers are written once. Reusing one silently would solve a case this
    sweep did not write."""
    runs = tmp_path / "runs"
    derived = tmp_path / "derived"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=tmp_path / "s1", derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs))

    again = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                          mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                          sweep_id="unit2")
    outcomes = es.run_sweep(again, sweeps_root=tmp_path / "s2",
                            derived_root=derived, runs_root=runs,
                            run_fn=_honest_solver(runs))
    assert not outcomes[0].ok()
    assert "already exists" in outcomes[0].error


def test_a_resume_with_a_changed_range_does_not_report_the_old_values(
        mini_base, tmp_path):
    """The severe one. Step records are keyed by INDEX, which says nothing
    about what the step was. Resuming a changed plan under the same sweep id
    once replayed the previous run's witnesses under the new plan's labels,
    solved nothing, and returned an all-green verdict."""
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    first = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                          mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                          sweep_id="unit")
    es.run_sweep(first, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs))

    second = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                           mode="scale", kmin=1.0, kmax=1.4, kstep=0.2,
                           sweep_id="unit")
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.run_sweep(second, sweeps_root=sweeps, derived_root=derived,
                     runs_root=runs, run_fn=_honest_solver(runs), resume=True)
    assert "already records a different sweep" in str(excinfo.value)
    assert "values" in str(excinfo.value)

    # And the record of what was originally asked for survives.
    assert es.read_plan(sweeps / "unit").values == [1.0, 1.1, 1.2]


def test_a_resume_re_runs_a_step_whose_record_is_for_a_different_value(
        mini_base, tmp_path):
    """Belt to the plan guard's braces: even reaching the loop with a
    mismatched record, the step is re-run rather than reported under the wrong
    label. Index alone is not identity."""
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=tmp_path / "derived",
                 runs_root=runs, run_fn=_honest_solver(runs))

    # Doctor step 2's record so it claims to be a value this plan never asked
    # for, exactly as a changed range would have left it.
    record = sweeps / "unit" / es.step_record_name(2)
    payload = json.loads(record.read_text("ascii"))
    payload["value"] = 1.9
    payload["slug"] = es.step_slug("k_load", 1.9)
    record.write_text(json.dumps(payload), encoding="ascii")

    calls = []

    def counting(case_csv, run_name, root):
        calls.append(run_name)
        return _honest_solver(runs)(case_csv, run_name, root)

    outcomes = es.run_sweep(plan, sweeps_root=sweeps,
                            derived_root=tmp_path / "derived",
                            runs_root=runs, run_fn=counting, resume=True)
    assert len(calls) == 1, "only the mismatched step is re-run"
    assert [o.value for o in outcomes] == [1.0, 1.1, 1.2]
    assert outcomes[1].witness == pytest.approx(220.0)


def _kline_plan(mini_base: Path, branch: str, sweep_id: str) -> es.SweepPlan:
    return es.plan_sweep(parent=mini_base, lever="k_line", target=branch,
                         mode="scale", kmin=1.0, kmax=0.8, kstep=-0.1,
                         sweep_id=sweep_id)


def _limit_solver(runs_root: Path, branch: str):
    """A fake PSO that reports the derated limit the layer actually wrote for
    the named branch, enforced."""
    def run_fn(case_csv, run_name, root):
        layer = Path(case_csv).parent
        results = Path(runs_root) / run_name / "results"
        write_fake_results(results, load_mw=BASE_LOAD_MW, path_name=branch,
                           limit_mw=es.written_witness("k_line", branch,
                                                       layer),
                           min_enforced=1, max_enforced=0)
        return 0, results, 0.5
    return run_fn


def test_a_resume_through_run_sweep_will_not_replay_another_branchs_limits(
        mini_base, tmp_path):
    """The hole the previous fix only narrowed.

    step_slug omits the target, so two k_line sweeps over the same values on
    different branches produce identical slugs. The resume-accept branch
    returns before _run_one_step, so the layer guard never ran there, and
    deleting sweep.json removed the only other check -- yielding an all-green
    verdict over a sweep that solved nothing and reported branch A's limits
    under branch B's name.
    """
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    branches = _monitored_branches(mini_base, 2)
    a, b = branches[0], branches[1]

    first = _kline_plan(mini_base, a, "s")
    es.run_sweep(first, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_limit_solver(runs, a))

    # Remove the plan file -- one ordinary file, and the refusal message even
    # names it.
    (sweeps / "s" / es.SWEEP_NAME).unlink()

    second = _kline_plan(mini_base, b, "s")
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.run_sweep(second, sweeps_root=sweeps, derived_root=derived,
                     runs_root=runs, run_fn=_limit_solver(runs, b),
                     resume=True)
    assert "no %s" % es.SWEEP_NAME in str(excinfo.value)


def test_the_resume_accept_branch_checks_the_layer_it_is_accepting(
        mini_base, tmp_path):
    """Belt to the plan guard's braces, and the guard that was being skipped.

    With sweep.json present but the target changed, slug and value still match
    -- only the layer's own manifest can tell the two apart, so the accept
    branch has to consult it rather than reason around it.
    """
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    a, b = _monitored_branches(mini_base, 2)

    first = _kline_plan(mini_base, a, "s")
    es.run_sweep(first, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_limit_solver(runs, a))

    # The plan guard would refuse this, so bypass it exactly as a hand-edited
    # or re-created plan file would, and exercise the in-loop check alone.
    second = _kline_plan(mini_base, b, "s")
    es.write_plan(sweeps / "s", second)

    calls = []

    def counting(case_csv, run_name, root):
        calls.append(run_name)
        return _limit_solver(runs, b)(case_csv, run_name, root)

    outcomes = es.run_sweep(second, sweeps_root=sweeps, derived_root=derived,
                            runs_root=runs, run_fn=counting, resume=True)

    # What must NOT happen is branch A's limits being reported as branch B's.
    # The record is rejected, and the layer behind it is branch A's and is
    # write-once, so the step stops rather than being re-solved -- which is
    # why nothing is handed to the solver at all.
    assert calls == [], "nothing may be solved under the wrong label"
    assert not outcomes[0].ok()
    assert "slug-prefix" in outcomes[0].error, (
        "the error must name the way out: %s" % outcomes[0].error)
    # And the verdict refuses the sweep rather than reporting it green.
    findings = es.check_sweep(second, outcomes)
    assert ec.has_errors(findings)
    assert es.verdict_exit_code(findings) == 1


def _monitored_branches(case_dir: Path, count: int) -> list:
    prefix = ec.case_prefix(case_dir)
    table = ec.read_table(case_dir / ("%s_BRN_ID.csv" % prefix))
    found = [r["Branch"] for r in table.records()
             if (r.get("Monitor") or "").strip() in ("1", "1.0")]
    assert len(found) >= count, (
        "the mini7k fixture has %d monitored branches, need %d"
        % (len(found), count))
    return found[:count]


def test_a_resume_refuses_a_layer_built_for_a_different_target(
        mini_base, tmp_path):
    """The slug omits the target, so two k_line sweeps over the same values on
    different branches collide on the directory name. Without --resume that is
    caught by write_layer; with it, this check is the only thing between the
    sweep and solving last week's corridor under this week's label."""
    branch = _monitored_branch(mini_base)
    derived = tmp_path / "derived"
    slug = es.step_slug("k_line", 0.9)
    layer = derived / ec.layer_dir_name(mini_base, slug)
    ec.build_stress_layer(mini_base, layer,
                          es.build_step_rows("k_line", branch, "scale", 0.9),
                          slug)

    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.assert_layer_matches(
            layer, es.build_step_rows("k_line", "SOME_OTHER_BRANCH",
                                      "scale", 0.9)[0])
    assert "slug-prefix" in str(excinfo.value)

    # The matching step is accepted, so the guard is not simply always-refusing.
    es.assert_layer_matches(
        layer, es.build_step_rows("k_line", branch, "scale", 0.9)[0])


def test_a_failed_step_stops_the_sweep_and_leaves_the_rest_unbuilt(
        mini_base, tmp_path):
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)

    def failing_run_fn(case_csv, run_name, root):
        return 5, Path(runs) / run_name / "results", 0.5

    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=failing_run_fn)
    assert len(outcomes) == 1
    assert "exited 5" in outcomes[0].error


# ------------------------------------------------------------------------------
#   6b. The contract with ercot7k_pso.py
#
#   The loop tests above inject a fake solver, so they cannot see this seam at
#   all -- and it is where the integration actually broke: the driver computed
#   each step's results path from its own --runs-root while the runner wrote
#   under the repo root, so a step SOLVED correctly for six minutes and then
#   failed as a missing file.
# ------------------------------------------------------------------------------
def test_the_runner_is_told_the_same_runs_root_the_results_are_read_from(
        tmp_path, monkeypatch):
    seen = {}

    class FakeCompleted:
        returncode = 0

    def fake_run(argv, **kwargs):
        seen["env"] = kwargs["env"]
        seen["stdin"] = kwargs["stdin"]
        return FakeCompleted()

    monkeypatch.setattr(es.subprocess, "run", fake_run)
    runs_root = tmp_path / "somewhere-else"
    code, results, _ = es.pso_run_step(tmp_path / "case" / "texas7k.csv",
                                       "step-01", runs_root)

    assert code == 0
    assert seen["env"]["DEVNET_PSO_RUNS_ROOT"] == str(runs_root.resolve())
    assert results == runs_root.resolve() / "step-01" / "results", (
        "the path the mapper will read must be the one the runner was told to "
        "write")
    assert seen["env"]["DEVNET_PSO_RUN_NAME"] == "step-01"
    assert seen["env"]["DEVNET_PSO_ASSUME_YES"] == "1"
    assert "DEVNET_PSO_RELAUNCHED" not in seen["env"], (
        "a stale value stops the runner re-execing into the aimmspy env")


def test_the_runner_closes_stdin_rather_than_feeding_it_canned_answers(
        tmp_path, monkeypatch):
    """A piped 'Y' would answer a prompt nobody knew had appeared. DEVNULL
    turns a new prompt into an EOFError that stops the step loudly."""
    seen = {}

    class FakeCompleted:
        returncode = 0

    monkeypatch.setattr(es.subprocess, "run",
                        lambda argv, **kw: seen.update(kw) or FakeCompleted())
    es.pso_run_step(tmp_path / "texas7k.csv", "s", tmp_path / "runs")
    assert seen["stdin"] == subprocess.DEVNULL


def test_the_runner_source_still_reads_the_batch_overrides():
    """A SOURCE-level pin, and deliberately labelled as one.

    A behavioural test is not available: ercot7k_pso.py executes at import, and
    driving it far enough as a subprocess to print its resolved results
    directory means passing the aimmspy gate -- at which point, with
    DEVNET_PSO_ASSUME_YES set, it opens AIMMS and takes the machine's only
    licence seat for six minutes. No test may do that.

    So this pins the READ rather than the mention. An earlier version asserted
    the three variable names appeared anywhere in the file, which the comment
    block added alongside them satisfied on its own -- every os.environ.get
    could have been deleted and it would still have passed.
    """
    source = (REPO_ROOT / "ercot7k_pso.py").read_text(encoding="utf-8")
    for name in ("DEVNET_PSO_RUNS_ROOT", "DEVNET_PSO_RUN_NAME",
                 "DEVNET_PSO_ASSUME_YES"):
        assert 'os.environ.get("%s"' % name in source, (
            "%s is mentioned but never read" % name)
    assert "os.path.join(RUNS_ROOT, RUN_NAME)" in source, (
        "the runs root is read but not used to place the run")


# ------------------------------------------------------------------------------
#   7. The summary table
# ------------------------------------------------------------------------------
def test_the_summary_leads_with_what_was_asked_and_what_came_back(
        mini_base, tmp_path):
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    outcomes = es.run_sweep(plan, sweeps_root=sweeps,
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_honest_solver(runs))
    path = es.write_summary(sweeps / "unit", plan, outcomes)

    text = path.read_text("ascii")
    header = text.splitlines()[0].split(",")
    assert header[:8] == ["step", "lever", "target", "value", "witness",
                          "witness_expected", "witness_column", "witness_ok"]
    assert "lmp_spread_p95_p05" in header
    assert "lmp_spread_maxmin" in header, (
        "both definitions are carried; the campaign measured max-min moving "
        "4.6x harder than P95-P05 on this network")
    assert text.count("\n") == 4  # header + 3 steps


def test_the_summary_flags_the_step_whose_witness_disagrees():
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    outcomes = _kline_outcomes([(1, 1.0, 100.0, 100.0, 1.0),
                                (2, 0.9, 100.0, 90.0, 1.0)])
    rows = es.summary_rows(plan, outcomes)
    assert [row["witness_ok"] for row in rows] == [1, 0]


def test_the_report_names_the_pin_and_the_witness():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    text = es.report_text(plan, outcomes, es.check_sweep(plan, outcomes))
    assert "interval 2" in text
    assert "ED_Ara.Load" in text
    assert "not measured" not in text


# ------------------------------------------------------------------------------
#   8. The pin
# ------------------------------------------------------------------------------
def test_a_case_with_no_pin_anywhere_in_its_chain_is_refused(tmp_path):
    base = tmp_path / "mini7k"
    shutil.copytree(MINI_DIR, base)
    with pytest.raises(es.Ercot7kSweepError) as excinfo:
        es.resolve_pin(base)
    assert "pin" in str(excinfo.value).lower()
    assert "ercot7k_results.py pin" in str(excinfo.value)


def test_the_pin_is_found_on_an_ancestor_of_the_parent(mini_base, tmp_path):
    """A sweep stacked on a datacenter layer reports the hour the BASE run
    pinned, which is what makes two layers comparable at all."""
    layer = tmp_path / "dc"
    ec.build_datacenter_layer(
        mini_base, layer,
        ec.DatacenterSpec(dc_name="DC1", node="N111179", p_set_mw=40.0,
                          byog_p_nom_mw=10.0, byog_max_mw=10.0, byog_mc=65.0),
    )
    key, source = es.resolve_pin(layer)
    assert key == pin()
    assert Path(source).name in ("mini7k", "dc")


# ------------------------------------------------------------------------------
#   9. Pruning -- the one irreversible thing in the driver
# ------------------------------------------------------------------------------
def test_a_foreign_run_directorys_results_are_refused_not_deleted(
        mini_base, tmp_path):
    """Composing the run name is the assumption under test, not a guard.

    A run directory can outlive its layers -- a cleaned ercot7k-derived, a
    different --derived-root, a sweep id reused after archiving -- so the
    write-once layer check does not cover this. Someone else's 450 MB must
    not be deleted on the strength of a name this driver made up.
    """
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    foreign = runs / plan.run_name(1, plan.values[0]) / "results"
    foreign.mkdir(parents=True)
    (foreign / "results_MC_Solution.csv").write_text("x\n", encoding="ascii")
    (foreign / "results_PC_Nd.csv").write_text("y\n", encoding="ascii")

    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived",
                            runs_root=runs, run_fn=_honest_solver(runs))
    assert not outcomes[0].ok()
    assert "not this step's" in outcomes[0].error
    assert (foreign / "results_PC_Nd.csv").is_file(), "nothing was deleted"


def test_a_different_plan_reusing_the_sweep_id_does_not_delete_the_results(
        mini_base, tmp_path):
    """The marker has to carry something the DIRECTORY NAME does not.

    run_name is sweep_id + index + slug, so a marker holding only those is a
    re-encoding of the name it came from and can disagree only if hand-edited.
    The plan digest is the part that makes ownership mean "the same plan wrote
    here" -- and this is the one path assert_plan_unchanged cannot see, since
    sweep.json has been removed along with everything else.
    """
    runs = tmp_path / "runs"
    first = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                          mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                          sweep_id="reused")
    es.run_sweep(first, sweeps_root=tmp_path / "s1",
                 derived_root=tmp_path / "d1", runs_root=runs,
                 run_fn=_honest_solver(runs))
    results = runs / first.run_name(1, 1.0) / "results"
    assert list(results.iterdir()), "the first sweep wrote results"

    # Same id, DIFFERENT plan, and nothing left to compare it against except
    # the marker: fresh sweeps root, fresh derived root.
    second = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                           mode="scale", kmin=1.0, kmax=1.4, kstep=0.2,
                           sweep_id="reused")
    outcomes = es.run_sweep(second, sweeps_root=tmp_path / "s2",
                            derived_root=tmp_path / "d2", runs_root=runs,
                            run_fn=_honest_solver(runs))
    assert not outcomes[0].ok()
    assert "not this step's" in outcomes[0].error
    assert list(results.iterdir()), "the earlier plan's results survive"


def test_the_digest_changes_when_any_part_of_the_plan_s_identity_changes():
    """Table-driven over PLAN_IDENTITY so it cannot drift as the tuple grows.

    Varying only the range would leave every other component free to fall out
    of the hash unnoticed -- and `target` is the reachable one: step_slug
    deliberately omits the target, so two k_line sweeps on different branches
    share a run directory name exactly, and once sweep.json is gone the digest
    is the only thing between the second and the first's results.
    """
    base = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    variants = {
        "parent": {"parent": Path("somewhere-else")},
        "lever": {"lever": "k_load"},
        "target": {"target": "BR2"},
        "mode": {"mode": "add"},
        "values": {"values": [1.0, 0.8]},
        "slug_prefix": {"slug_prefix": "v2-"},
        "decimals": {"decimals": 3},
        "report": {"key": er.ReportKey(cycle="RT", scenario="ScnRT",
                                       interval=99)},
    }
    # Every hashed component must have a case here, or the test is not the
    # protection it claims to be.
    assert set(variants) == set(es.PLAN_IDENTITY) | {"report"}

    for name, change in variants.items():
        other = dataclasses.replace(base, **change)
        assert other.identity_digest() != base.identity_digest(), (
            "changing %s leaves the plan digest unchanged, so a sweep "
            "differing only in %s would be treated as the same plan and "
            "could delete its results" % (name, name))


def test_the_digest_is_stable_for_a_plan_that_has_not_changed():
    base = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    twin = _plan(lever="k_line", target="BR1", values=(1.0, 0.9))
    assert base.identity_digest() == twin.identity_digest()
    # sweep_id is carried by the marker separately and must NOT be hashed:
    # the same plan under a new id is still the same plan.
    renamed = dataclasses.replace(base, sweep_id="other")
    assert renamed.identity_digest() == base.identity_digest()


def test_a_slug_prefix_may_end_in_a_dot_because_it_is_never_a_whole_name(
        mini_base):
    """step_slug splices the prefix into the middle of the directory name, so
    the Windows trailing-dot hazard cannot arise there -- and a dotted
    namespace prefix is the natural thing to reach for."""
    plan = es.plan_sweep(parent=mini_base, lever="k_load", target="",
                         mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                         slug_prefix="v2.")
    assert plan.slug(1.0) == "v2.k_load1"
    # The same string is still refused for the sweep id, which IS a component.
    with pytest.raises(es.Ercot7kSweepError, match="directory name"):
        es.plan_sweep(parent=mini_base, lever="k_load", target="",
                      mode="scale", kmin=1.0, kmax=1.2, kstep=0.1,
                      sweep_id="v2.")


def test_a_nested_results_tree_is_not_treated_as_an_empty_directory(
        mini_base, tmp_path):
    """Listing only top-level files made a directory holding
    results/sub/x.csv read as empty: ownership claimed, foreign tree merged
    into this step's output."""
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    nested = runs / plan.run_name(1, plan.values[0]) / "results" / "sub"
    nested.mkdir(parents=True)
    (nested / "results_PC_Nd.csv").write_text("foreign\n", encoding="ascii")

    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived",
                            runs_root=runs, run_fn=_honest_solver(runs))
    assert not outcomes[0].ok()
    assert (nested / "results_PC_Nd.csv").is_file(), "nothing was deleted"


def test_this_sweeps_own_failed_attempt_is_cleared_on_a_re_run(
        mini_base, tmp_path):
    """The other half: a marker that matches means the files ARE this step's,
    and merging into them would read a failed attempt as this one's."""
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs))

    results = runs / plan.run_name(1, plan.values[0]) / "results"
    (results / "results_STALE.csv").write_text("old\n", encoding="ascii")

    # Re-run step 1 by invalidating only its record.
    (sweeps / "unit" / es.step_record_name(1)).unlink()
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs), resume=True)
    assert not (results / "results_STALE.csv").exists(), (
        "a stale file from the previous attempt would be read as this one's")


def test_pruning_refuses_a_directory_that_is_not_a_results_directory(tmp_path):
    (tmp_path / "results_PC_Nd.csv").write_text("x\n", encoding="ascii")
    with pytest.raises(es.Ercot7kSweepError, match="does not look like"):
        es.prune_results(tmp_path)
    assert (tmp_path / "results_PC_Nd.csv").is_file(), "nothing was deleted"


def test_pruning_keeps_the_tables_the_costs_are_re_derivable_from(tmp_path):
    results = tmp_path / "results"
    write_fake_results(results, load_mw=200.0)
    removed = es.prune_results(results)

    assert "results_PC_Nd.csv" in removed
    for name in es.KEEP_TABLES:
        assert (results / ("results_%s.csv" % name)).is_file()
    # Still readable for the two figures the summary stands on.
    assert er.objective_by_cycle(results)["RT"] == pytest.approx(3000.0)
    witness, _ = es.read_witness("k_load", "scale", "", results, pin())
    assert witness == pytest.approx(200.0)


# ------------------------------------------------------------------------------
#   10. The CLI
# ------------------------------------------------------------------------------
def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "ercot7k_sweep.py"), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
    )


def test_the_module_is_importable_without_side_effects():
    """Unlike the front ends, this one is imported by the loop's own tests, so
    it must not print, prompt or create anything at import time."""
    result = subprocess.run(
        [sys.executable, "-c", "import ercot7k_sweep"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_plan_prints_the_steps_and_solves_nothing(mini_base, tmp_path):
    result = run_cli("plan", "--parent", str(mini_base), "--lever", "k_load",
                     "--kmin", "1.0", "--kmax", "1.2", "--kstep", "0.1",
                     "--sweeps-root", str(tmp_path / "sweeps"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1, 1.1, 1.2" in result.stdout
    assert "ED_Ara.Load" in result.stdout
    assert "Nothing was built or solved" in result.stdout
    assert not (tmp_path / "sweeps").exists()


def test_a_bad_range_is_refused_before_anything_is_built(mini_base):
    result = run_cli("plan", "--parent", str(mini_base), "--lever", "k_load",
                     "--kmin", "1.0", "--kmax", "0.25", "--kstep", "-0.1")
    assert result.returncode == 2
    assert "not a whole number of steps" in result.stderr


def test_the_cli_refuses_an_unsweepable_lever(mini_base):
    result = run_cli("plan", "--parent", str(mini_base), "--lever", "k_gen",
                     "--target", "G1", "--mode", "outage",
                     "--kmin", "1.0", "--kmax", "0.5", "--kstep", "-0.1")
    assert result.returncode == 2
    assert "cannot be swept" in result.stderr


def test_check_re_runs_the_verdict_over_a_finished_sweep(mini_base, tmp_path):
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    outcomes = es.run_sweep(plan, sweeps_root=sweeps,
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_honest_solver(runs))
    es.write_summary(sweeps / "unit", plan, outcomes)

    result = run_cli("check", str(sweeps / "unit"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "W2" in result.stdout
    assert (sweeps / "unit" / es.REPORT_NAME).is_file()


def test_check_refreshes_the_summary_as_well_as_the_report(
        mini_base, tmp_path):
    """Refreshing only the report left the two artifacts in one directory
    disagreeing, and the CSV is the one a script reads."""
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    outcomes = es.run_sweep(plan, sweeps_root=sweeps,
                            derived_root=tmp_path / "derived", runs_root=runs,
                            run_fn=_honest_solver(runs))
    summary = es.write_summary(sweeps / "unit", plan, outcomes)
    summary.write_text("stale,nonsense\n1,2\n", encoding="ascii")

    assert run_cli("check", str(sweeps / "unit")).returncode == 0
    refreshed = summary.read_text("ascii")
    assert "stale" not in refreshed
    assert refreshed.splitlines()[0].startswith("step,lever,target,value")


def test_the_disk_guard_stops_the_loop_with_the_finished_steps_intact(
        mini_base, tmp_path, monkeypatch):
    """Drives run_sweep, not enough_disk_for_step.

    The first version of this test called the helper directly and would have
    passed with the call site deleted -- the same species of defect the review
    raised about a test that called assert_layer_matches directly. Here the
    volume is made to look nearly full after the first step, and the assertion
    is on the LOOP's behaviour.
    """
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    real_usage = shutil.disk_usage

    class Tight:
        def __init__(self, free):
            self.total = self.used = 0
            self.free = free

    calls = []

    def fake_usage(path):
        # Roomy until the first step has been measured, then not.
        if calls:
            return Tight(free=int(1024 * 1024 * 10))  # 10 MB left
        return real_usage(path)

    def counting(case_csv, run_name, root):
        calls.append(run_name)
        return _honest_solver(runs)(case_csv, run_name, root)

    monkeypatch.setattr(es.shutil, "disk_usage", fake_usage)
    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived",
                            runs_root=runs, run_fn=counting)

    assert len(calls) == 1, "the loop must stop before solving step 2"
    assert len(outcomes) == 1, "and the finished step survives"
    assert outcomes[0].ok()


def test_enough_disk_for_step_refuses_when_a_step_cannot_fit(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    fits, why = es.enough_disk_for_step(runs, [10.0, 10.0])
    assert fits and why == ""

    huge = shutil.disk_usage(str(runs)).free / (1024.0 * 1024.0) + 1_000_000
    fits, why = es.enough_disk_for_step(runs, [huge])
    assert not fits
    assert "--resume" in why, "it must say the finished steps survive"


def test_the_guard_is_handed_the_pre_prune_peak_not_the_remainder(
        mini_base, tmp_path, monkeypatch):
    """--prune shrinks what a step LEAVES, but the next step still writes the
    full amount before anything is pruned, so sizing on the retained figure
    reserves about a tenth of what is needed.

    Asserted on what the call site actually passes -- the previous version of
    this test called enough_disk_for_step with literal numbers, so removing
    peak_results_mb entirely left it passing.
    """
    runs = tmp_path / "runs"
    plan = _sweep_plan_for(mini_base)
    seen = []
    real = es.enough_disk_for_step

    def spy(runs_root, measured_mb):
        seen.append(list(measured_mb))
        return real(runs_root, measured_mb)

    monkeypatch.setattr(es, "enough_disk_for_step", spy)
    outcomes = es.run_sweep(plan, sweeps_root=tmp_path / "sweeps",
                            derived_root=tmp_path / "derived",
                            runs_root=runs, run_fn=_honest_solver(runs),
                            prune=True)

    assert seen, "the guard must be consulted between steps"
    assert all(o.pruned for o in outcomes), "the fixture must have pruned"
    peak = outcomes[0].peak_results_mb
    retained = outcomes[0].results_mb
    assert peak > retained, "pruning must actually have shrunk the directory"
    assert seen[0][0] == pytest.approx(peak), (
        "the guard was sized on the retained %.4f MB, not the peak %.4f MB"
        % (retained, peak))


def test_the_peak_survives_to_disk_and_is_what_a_resumed_guard_sees(
        mini_base, tmp_path, monkeypatch):
    """The sibling path, and the one the guard exists for.

    A resumed sweep is exactly the case where six steps are already on disk
    and the volume fills at step seven -- and there the peak comes back from
    the step RECORD, not from a live measurement. Nothing read that field
    back: zeroing it in outcome_from_dict left the whole suite passing, and
    the `or results_mb` fallback then hands the guard the pruned remainder,
    which is cycle-3's issue verbatim on the resume path.
    """
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    derived = tmp_path / "derived"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs), prune=True)

    recorded = json.loads(
        (sweeps / "unit" / es.step_record_name(1)).read_text("ascii"))
    peak = recorded["peak_results_mb"]
    assert peak > recorded["results_mb"], "the fixture must have pruned"

    # Re-run only the last step, so steps 1-2 come back from their records.
    (sweeps / "unit" / es.step_record_name(3)).unlink()
    seen = []
    real = es.enough_disk_for_step

    def spy(runs_root, measured_mb):
        seen.append(list(measured_mb))
        return real(runs_root, measured_mb)

    monkeypatch.setattr(es, "enough_disk_for_step", spy)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=derived,
                 runs_root=runs, run_fn=_honest_solver(runs), prune=True,
                 resume=True)

    assert seen, "the guard must be consulted on a resumed sweep too"
    assert seen[0][0] == pytest.approx(peak), (
        "a resumed step's peak must come back from its record, not collapse "
        "to the pruned remainder")


def test_an_unmeasurable_disk_is_not_treated_as_a_pass(tmp_path):
    """The module says in several places that a SKIP is not a pass; its own
    disk guard used to return 'fits' when free space could not be read."""
    plan = _plan()
    projected = es.projection(plan, Path("Z:/no/such/volume"))
    assert not projected["measured"]
    assert not projected["fits"]


def test_one_measured_step_is_unverified_and_exits_non_zero():
    """The regression relaxing W1 to a WARNING introduced: with a single
    measured witness the comparison checks emitted NOTHING, and
    verdict_exit_code can only see findings that exist -- so a sweep with the
    one check this driver exists to perform never run came out green."""
    plan = _plan(lever="k_line", target="BR1", values=(1.0, 0.9, 0.8))
    outcomes = _kline_outcomes([(1, 1.0, 969.8, 969.8, 1.0),
                                (2, 0.9, math.nan, 872.8, math.nan),
                                (3, 0.8, math.nan, 775.8, math.nan)])
    findings = es.check_sweep(plan, outcomes)
    assert not ec.has_errors(findings), "W1 warns; the point is the exit code"
    assert _levels(findings, "W2") == [ec.LEVEL_SKIP]
    assert _levels(findings, "W3") == [ec.LEVEL_SKIP]
    assert es.verdict_exit_code(findings) == 1, (
        "an unverified sweep must never exit 0")


def test_a_sweep_whose_witness_could_not_be_compared_exits_non_zero():
    """An unverified sweep must not be green to anything reading only the exit
    status, or the 'a SKIP is not a pass' wording is decoration.

    A one-value plan is the reachable shape: plan_sweep refuses it, but
    check_sweep also runs over a hand-written or hand-edited sweep.json.
    """
    plan = _plan(values=(1.0,))
    findings = es.check_sweep(plan, [_outcome(1, 1.0, 200.0)])
    assert not ec.has_errors(findings), "every step completed -- no ERROR"
    assert _levels(findings, "W1") == [ec.LEVEL_SKIP]
    assert es.verdict_exit_code(findings) == 1


def test_a_clean_sweep_exits_zero():
    plan = _plan()
    outcomes = [_outcome(1, 1.0, 200.0), _outcome(2, 1.1, 220.0),
                _outcome(3, 1.2, 240.0)]
    assert es.verdict_exit_code(es.check_sweep(plan, outcomes)) == 0


def test_a_truncated_step_record_names_the_problem_rather_than_keyerroring(
        tmp_path):
    with pytest.raises(es.Ercot7kSweepError, match="truncated"):
        es.outcome_from_dict({"index": 1})


def test_the_run_subcommand_reports_a_refusal_rather_than_a_traceback(
        mini_base, tmp_path, monkeypatch, capsys):
    """The `run` path's exception handling had never executed in the suite --
    every resume test called run_sweep in-process -- which is how a refusal
    added for the resume holes came to surface as a stack trace and exit 1,
    the same code as "the sweep ran and was found broken".

    pso_run_step is monkeypatched, so no AIMMS is started.
    """
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    monkeypatch.setattr(es, "pso_run_step", _honest_solver(runs))
    def argv(kmax):
        return ["--parent", str(mini_base), "--lever", "k_load",
                "--kmin", "1.0", "--kmax", kmax, "--kstep", "0.1",
                "--sweeps-root", str(sweeps), "--derived-root",
                str(tmp_path / "derived"), "--runs-root", str(runs),
                "--sweep-id", "cli"]

    assert es.main(["run"] + argv("1.2")) == 0
    capsys.readouterr()

    # Same id, different range: a refusal to START, which must not be exit 1.
    code = es.main(["run"] + argv("1.4"))
    assert code == 2, "a refusal to start is not a failed sweep"
    assert "AMW-ERR" in capsys.readouterr().err


def test_the_run_subcommand_returns_the_verdict_code_on_a_real_loop(
        mini_base, tmp_path, monkeypatch, capsys):
    """And the CLI does return non-zero when the sweep itself is broken."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(es, "pso_run_step", _deaf_solver(runs))
    code = es.main(["run", "--parent", str(mini_base), "--lever", "k_load",
                    "--kmin", "1.0", "--kmax", "1.2", "--kstep", "0.1",
                    "--sweeps-root", str(tmp_path / "sweeps"),
                    "--derived-root", str(tmp_path / "derived"),
                    "--runs-root", str(runs), "--sweep-id", "cli2"])
    assert code == 1
    assert "did not happen" in capsys.readouterr().out


def test_check_reports_a_bad_directory_the_way_every_other_path_does(tmp_path):
    result = run_cli("check", str(tmp_path / "not-a-sweep"))
    assert result.returncode == 2
    assert "AMW-ERR" in result.stderr
    assert "Traceback" not in result.stderr


def test_check_exits_non_zero_on_a_sweep_that_did_not_happen(
        mini_base, tmp_path):
    runs = tmp_path / "runs"
    sweeps = tmp_path / "sweeps"
    plan = _sweep_plan_for(mini_base)
    es.run_sweep(plan, sweeps_root=sweeps, derived_root=tmp_path / "derived",
                 runs_root=runs, run_fn=_deaf_solver(runs))

    result = run_cli("check", str(sweeps / "unit"))
    assert result.returncode == 1
    assert "did not happen" in result.stdout

# ------------------------------------------------------------------------------
# END OF test_ercot7k_sweep.py
# ------------------------------------------------------------------------------
