#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# doctor.py -- preflight check for the PSO route (ercot7k_pso.py). Catches the
# common and silent setup problems before a six-minute solve does, with a fix
# hint for each.
#
# Run from the MAIN env (.venv):
#   .venv\Scripts\python.exe doctor.py
#
# It checks PyPSA in this env, then probes the separate solve interpreter
# (.venv-pso, via `python` in pso.local.toml) for aimmspy and the AIMMS install
# the runner will pick, then the PSO model and the case. It opens nothing: no
# AIMMS session starts and no licence seat is taken. Exit 0 if ready to solve;
# non-zero if a critical check fails.
#
# Adapted from the pso-engine branch's pso/doctor.py (June 2026), which gated
# the solve checks behind the DevNet engine switch. The ercot7k route always
# solves with PSO, so here they always run.

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import pso_config  # noqa: E402

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[warn]"
crit_fail = False

DEFAULT_CASE = REPO / "ercot7k" / "texas7k.csv"

# Run inside the solve interpreter: aimmspy's version and the AIMMS /Bin the
# runner would resolve, by the same precedence ercot7k_pso.py uses
# (aimms_path, then aimms_version, then aimmspy's major.minor).
_PROBE = r'''
import json, os
out = {}
try:
    import aimmspy
    from aimmspy.utils import find_aimms_path
    out["aimmspy"] = str(aimmspy.__version__)
    ap = os.environ.get("DEVNET_PSO_AIMMS_PATH")
    av = os.environ.get("DEVNET_PSO_AIMMS_VERSION")
    if ap:
        out["aimms"], out["by"] = ap, "aimms_path"
    elif av:
        out["aimms"], out["by"] = str(find_aimms_path(av)), "aimms_version " + av
    else:
        mm = ".".join(out["aimmspy"].split(".")[:2])
        out["aimms"], out["by"] = str(find_aimms_path(mm)), "aimmspy major.minor " + mm
except Exception as e:
    out["error"] = repr(e)
print(json.dumps(out))
'''


def line(status, label, detail="", hint=""):
    global crit_fail
    if status == BAD:
        crit_fail = True
    print(f"  {status} {label}" + (f": {detail}" if detail else ""))
    if hint:
        print(f"         -> {hint}")


def main():
    print("PSO route doctor")
    print("=" * 60)

    try:
        applied = pso_config.load_config()
    except pso_config.ConfigError as e:
        line(BAD, "config file", str(e), "fix pso.local.toml (see pso.local.toml.example)")
        applied = {}
    cfg = pso_config.CONFIG_FILE
    if cfg.is_file():
        line(OK, "config file", str(cfg), f"applied {len(applied)} setting(s)")
    else:
        line(BAD, "config file", "not found",
             f"run setup.ps1 / setup.sh, or copy pso.local.toml.example -> {cfg.name}")

    # PyPSA lives in THIS (main) env: the menu, the DevNet workflow, the tests.
    try:
        import pypsa
        line(OK, "pypsa (main env)", pypsa.__version__)
    except Exception as e:
        line(BAD, "pypsa (main env)", str(e),
             "run setup.ps1 / setup.sh, then run this with .venv's python")

    _check_solve_env()
    _check_model_and_case()

    print("=" * 60)
    if crit_fail:
        print("NOT READY -- fix the [FAIL] item(s) above.")
        sys.exit(1)
    print("READY.")
    sys.exit(0)


def _check_solve_env():
    solve_py = os.environ.get("DEVNET_PSO_PYTHON")
    if not solve_py:
        line(BAD, "solve interpreter", "python not set in pso.local.toml",
             "run setup.ps1 / setup.sh, which wires it to .venv-pso")
        return
    if not Path(solve_py).exists():
        line(BAD, "solve interpreter", f"not found: {solve_py}",
             "re-run setup.ps1 / setup.sh, or fix python= in pso.local.toml")
        return
    line(OK, "solve interpreter", solve_py)

    r = subprocess.run([solve_py, "-c", _PROBE], capture_output=True, text=True)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        line(BAD, "aimmspy", (r.stderr.strip().splitlines() or ["probe failed"])[-1],
             "the solve env lacks aimmspy: re-run setup, or "
             "uv pip install --python .venv-pso \"aimmspy>=26.1,<26.2\"")
        return
    if "error" in out:
        line(BAD, "aimmspy / AIMMS", out["error"],
             "install an aimmspy whose major.minor matches your AIMMS, "
             "or set aimms_version / aimms_path in pso.local.toml")
        return

    line(OK, "aimmspy (solve env)", out.get("aimmspy", "?"))
    aimms = out.get("aimms")
    if aimms and Path(aimms).exists():
        line(OK, "AIMMS install", f"{aimms}  (by {out.get('by')})")
    else:
        line(BAD, "AIMMS install", f"resolved but missing: {aimms}",
             "install a matching AIMMS, or set aimms_path / aimms_version in pso.local.toml")

    if Path(solve_py).resolve() == Path(sys.executable).resolve():
        line(WARN, "environments", "the solve interpreter is this PyPSA env",
             "keep aimmspy in .venv-pso: it forces linopy down and breaks n.optimize")

    if os.environ.get("DEVNET_PSO_LICENSE_URL"):
        line(OK, "license", "license_url set (academic/cloud)")
    else:
        line(WARN, "license", "using the machine-configured AIMMS license",
             "set license_url in pso.local.toml if you use an academic/cloud license")


def _check_model_and_case():
    proj = os.environ.get("DEVNET_PSO_PROJECT")
    if not proj:
        line(BAD, "PSO model", "project not set",
             "set project = \"...\\\\PSO.aimms\" in pso.local.toml")
    elif not Path(proj).is_file():
        line(BAD, "PSO model", f"not found: {proj}", "check the project path")
    else:
        line(OK, "PSO model", proj)

    case = os.environ.get("DEVNET_PSO_CASE")
    path = Path(case) if case else DEFAULT_CASE
    if not path.is_absolute():
        path = REPO / path
    if path.is_file():
        line(OK, "case", str(path) + ("" if case else "  (default)"))
    else:
        line(BAD, "case", f"not found: {path}",
             "fix case= in pso.local.toml; a derived layer is printed by ercot7k_build.py")


if __name__ == "__main__":
    main()
