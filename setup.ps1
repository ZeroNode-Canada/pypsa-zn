# setup.ps1 -- one-shot environment setup on Windows.
#
# Creates TWO environments (they have conflicting deps and must stay separate):
#   .venv      PyPSA stack -- the menu, the DevNet workflow, ercot7k build/tests
#   .venv-pso  aimmspy     -- drives PSO for the solve (ercot7k_pso.py re-launches
#                             itself here via `python` in pso.local.toml)
# Uses `uv` if present (fast; .venv then follows uv.lock exactly); otherwise falls
# back to stock `python -m venv` + `pip`.
#
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1 -Aimmspy "aimmspy==26.1.8.1"
#
# Prereqs: Python 3.10+ on PATH (3.12 is what uv.lock was tested with), plus AIMMS
# installed for the solve -- this script does not install AIMMS or PSO.aimms.
#
# -Aimmspy is the pip requirement for the solve env. Its major.minor must match
# your AIMMS: the runner picks the AIMMS install by aimmspy's major.minor unless
# pso.local.toml sets aimms_version or aimms_path. The default tracks AIMMS 26.1.

param(
    [string]$Python = "python",
    [string]$Aimmspy = "aimmspy>=26.1,<26.2"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

$deps = @("pypsa==0.35.2","numpy","pandas<3","matplotlib","scipy","networkx","openpyxl","highspy")

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "==> uv found -- building envs with uv" -ForegroundColor Cyan
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    uv venv .venv-pso
    if ($LASTEXITCODE -ne 0) { throw "uv venv .venv-pso failed" }
    uv pip install --python .venv-pso $Aimmspy
    if ($LASTEXITCODE -ne 0) { throw "installing $Aimmspy into .venv-pso failed" }
} else {
    Write-Host "==> uv not found -- using python -m venv + pip" -ForegroundColor Cyan
    & $Python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install @deps
    if ($LASTEXITCODE -ne 0) { throw "installing the PyPSA stack into .venv failed" }
    & $Python -m venv .venv-pso
    & .\.venv-pso\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv-pso\Scripts\python.exe -m pip install $Aimmspy
    if ($LASTEXITCODE -ne 0) { throw "installing $Aimmspy into .venv-pso failed" }
}

# Seed pso.local.toml from the template and wire the solve interpreter.
$cfg = Join-Path $root "pso.local.toml"
if (-not (Test-Path $cfg)) {
    Copy-Item (Join-Path $root "pso.local.toml.example") $cfg
    Write-Host "==> created pso.local.toml (edit: project, and license_url if academic)" -ForegroundColor Yellow
}
if (-not (Select-String -Path $cfg -Pattern '^\s*python\s*=' -Quiet)) {
    $psoPy = (Join-Path $root ".venv-pso\Scripts\python.exe") -replace '\\','\\'
    Add-Content $cfg "python = `"$psoPy`""
    Write-Host "==> wired solve interpreter -> $psoPy"
}

Write-Host "`nSetup done. Next:" -ForegroundColor Green
Write-Host "  1. Edit pso.local.toml  (project = path to PSO.aimms; license_url if academic)"
Write-Host "  2. .\.venv\Scripts\python.exe doctor.py        # verify -- get it to READY"
Write-Host "  3. .\.venv\Scripts\python.exe devnet_menu.py   # option 3 -> PSO route"
