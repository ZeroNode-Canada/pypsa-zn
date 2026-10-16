# ------------------------------------------------------------------------------
# test_ercot7k_pso_peak.py
#
# peak_served_load() is the runner's "verify a real value" check, and the number
# it prints is the one a person reads to decide a run was sane. It reported
# 165,184 MW on the 2030 WA case, whose real RT peak is 82,592: PSO writes area
# "0" as the system aggregate beside the eight weather zones, and the function
# summed both.
#
# ercot7k_pso.py executes at import (it opens AIMMS), so the module cannot be
# imported here. The function is pure -- it reads one CSV -- so it is lifted out
# of the source by name and called for real. That makes these behavioural tests,
# unlike the source-level pin in test_ercot7k_sweep.py, which had no such option.
# ------------------------------------------------------------------------------
import ast
import csv
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "ercot7k_pso.py"

HEADER = "//cyc,scn,ara,int,Load,Loss,P\n"


def _load_peak_served_load():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name == "peak_served_load"]
    assert len(nodes) == 1, "peak_served_load() is not a top-level function"
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"os": os, "csv": csv}
    exec(compile(module, str(RUNNER), "exec"), namespace)
    return namespace["peak_served_load"]


peak_served_load = _load_peak_served_load()


def _results(tmp_path: Path, rows) -> str:
    """rows: (cyc, ara, int, load). Writes PSO's results_ED_Ara.csv layout."""
    lines = [HEADER] + ["%s,Scn%s,%s,%d,%.3f,0.000,%.3f\n"
                        % (cyc, cyc, ara, i, load, load)
                        for cyc, ara, i, load in rows]
    (tmp_path / "results_ED_Ara.csv").write_text("".join(lines), encoding="utf-8")
    return str(tmp_path)


def test_zones_plus_the_aggregate_are_not_double_counted(tmp_path):
    """The 2030 WA case: zones AND area 0 on every interval."""
    rows = []
    for i, zones in ((1, (30.0, 20.0)), (2, (50.0, 25.0))):
        rows += [("RT", z, i, mw) for z, mw in zip(("Coast", "West"), zones)]
        rows.append(("RT", "0", i, sum(zones)))
    assert peak_served_load(_results(tmp_path, rows), "RT") == pytest.approx(75.0)


def test_a_single_area_case_still_reads_its_one_row(tmp_path):
    """The 2018 case: area 0 only. The fix must not move this number."""
    rows = [("RT", "0", 1, 46000.0), ("RT", "0", 2, 46795.0)]
    assert peak_served_load(_results(tmp_path, rows), "RT") == pytest.approx(46795.0)


def test_zones_without_an_aggregate_are_summed(tmp_path):
    rows = [("RT", "Coast", 1, 30.0), ("RT", "West", 1, 20.0),
            ("RT", "Coast", 2, 10.0), ("RT", "West", 2, 15.0)]
    assert peak_served_load(_results(tmp_path, rows), "RT") == pytest.approx(50.0)


def test_the_cycle_filter_still_excludes_other_cycles(tmp_path):
    rows = [("RT", "Coast", 1, 30.0), ("RT", "0", 1, 30.0),
            ("DA", "Coast", 1, 900.0), ("DA", "0", 1, 900.0)]
    assert peak_served_load(_results(tmp_path, rows), "RT") == pytest.approx(30.0)


def test_a_missing_file_is_none_not_zero(tmp_path):
    assert peak_served_load(str(tmp_path), "RT") is None
