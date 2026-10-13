#!/usr/bin/env sh
# setup.sh -- one-shot environment setup (Linux/macOS).
#
# Creates TWO environments (conflicting deps -> must stay separate):
#   .venv      PyPSA stack -- the menu, the DevNet workflow, ercot7k build/tests
#   .venv-pso  aimmspy     -- drives PSO for the solve
# Uses `uv` if present (fast; .venv then follows uv.lock exactly); otherwise falls
# back to `python -m venv` + `pip`.
#
#   sh setup.sh
#   AIMMSPY="aimmspy==26.1.8.1" sh setup.sh
#
# Prereqs: Python 3.10+ (3.12 is what uv.lock was tested with) and AIMMS installed
# for the solve. AIMMSPY is the pip requirement for the solve env; its major.minor
# must match your AIMMS (see setup.ps1). The default tracks AIMMS 26.1.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
AIMMSPY="${AIMMSPY:-aimmspy>=26.1,<26.2}"

if command -v uv >/dev/null 2>&1; then
    echo "==> uv found -- building envs with uv"
    uv sync
    uv venv .venv-pso
    uv pip install --python .venv-pso "$AIMMSPY"
else
    echo "==> uv not found -- using python -m venv + pip"
    "$PY" -m venv .venv
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install "pypsa==0.35.2" numpy "pandas<3" matplotlib scipy networkx openpyxl highspy
    "$PY" -m venv .venv-pso
    ./.venv-pso/bin/python -m pip install --upgrade pip
    ./.venv-pso/bin/python -m pip install "$AIMMSPY"
fi

# Seed pso.local.toml and wire the solve interpreter.
[ -f pso.local.toml ] || { cp pso.local.toml.example pso.local.toml; \
    echo "==> created pso.local.toml (edit: project, and license_url if academic)"; }
if ! grep -q '^[[:space:]]*python[[:space:]]*=' pso.local.toml; then
    echo "python = \"$(pwd)/.venv-pso/bin/python\"" >> pso.local.toml
    echo "==> wired solve interpreter -> $(pwd)/.venv-pso/bin/python"
fi

echo ""
echo "Setup done. Next:"
echo "  1. Edit pso.local.toml  (project = path to PSO.aimms; license_url if academic)"
echo "  2. ./.venv/bin/python doctor.py       # verify -- get it to READY"
echo "  3. ./.venv/bin/python devnet_menu.py  # option 3 -> PSO route"
