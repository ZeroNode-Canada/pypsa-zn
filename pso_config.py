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

# pso_config.py -- load pso.local.toml into the DEVNET_PSO_* environment.
#
# One small config file at the repo root (pso.local.toml, gitignored) instead of
# remembering env vars. Values are applied as env defaults: an already-set env var
# always wins, so CI / one-off overrides still work. ercot7k_pso.py calls
# load_config() before reading any DEVNET_PSO_* var, so the settings reach the
# solve no matter how the script is launched.
#
# Copy pso.local.toml.example -> pso.local.toml and edit. Example:
#   project     = "D:\\path\\to\\PSO.aimms"
#   license_url = "wss://licensing.aimms.cloud/..."   # academic/cloud; omit for machine license
#   case        = "ercot7k/texas7k.csv"
#   python      = "C:\\path\\to\\env-with-aimmspy\\python.exe"
#
# Works on Python 3.10, which the repo supports but which has no "tomllib" (it
# arrived in 3.11). Where tomllib or tomli is importable it is used; otherwise a
# built-in parser reads the flat "key = value" form above. No extra dependency
# either way, and a config file that exists is never silently ignored.
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# Standard imports
# ------------------------------------------------------------------------------
import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
    PARSER = "tomllib"
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # 3.10 backport, if installed
        PARSER = "tomli"
    except ModuleNotFoundError:
        tomllib = None
        PARSER = "built-in fallback"


class ConfigError(RuntimeError):
    """pso.local.toml exists but could not be read."""

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent
CONFIG_FILE = REPO / "pso.local.toml"

# toml key -> environment variable
_MAP = {
    "project":       "DEVNET_PSO_PROJECT",
    "license_url":   "DEVNET_PSO_LICENSE_URL",
    "aimms_path":    "DEVNET_PSO_AIMMS_PATH",
    "aimms_version": "DEVNET_PSO_AIMMS_VERSION",
    "case":          "DEVNET_PSO_CASE",
    "python":        "DEVNET_PSO_PYTHON",
}

# ------------------------------------------------------------------------------
# parse_flat_toml()
# Parses flat TOML configuration when tomllib/tomli is unavailable.
# ------------------------------------------------------------------------------
def parse_flat_toml(text: str) -> dict:
    """
    Read the flat 'key = value' subset that pso.local.toml uses.

    Fallback for Python 3.10, where tomllib does not exist and tomli may not be
    installed. Handles comments, trailing comments, basic ("...") and literal
    ('...') strings, and bare tokens. Anything richer -- tables, arrays,
    multi-line strings -- raises ConfigError rather than guessing, because a
    silently mangled project path is worse than a refusal.
    """
    out: dict[str, str] = {}

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("["):
            raise ConfigError(
                f"line {lineno}: tables are not supported by the built-in parser. "
                f"Install tomli (pip install tomli) or use Python 3.11+."
            )

        if "=" not in line:
            raise ConfigError(f"line {lineno}: expected 'key = value', got: {raw.strip()}")

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if value[:1] in ('"', "'"):
            quote = value[0]
            end = value.find(quote, 1)

            if end == -1:
                raise ConfigError(f"line {lineno}: unterminated string for key '{key}'")

            body = value[1:end]
            # A basic string processes escapes; the only one our own example
            # uses is a doubled backslash for Windows paths. A literal string
            # takes backslashes as-is, which is why it is offered.
            out[key] = body.replace("\\\\", "\\") if quote == '"' else body
        else:
            out[key] = value.split("#", 1)[0].strip()

    return out

# ------------------------------------------------------------------------------
# load_config()
# Loads PSO configuration without overriding existing environment variables.
# ------------------------------------------------------------------------------
def load_config(path: Path = CONFIG_FILE) -> dict:
    """Apply pso.local.toml as env defaults (existing env vars take precedence)."""
    path = Path(path)

    if not path.is_file():
        return {}

    if tomllib is not None:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    else:
        cfg = parse_flat_toml(path.read_text(encoding="utf-8"))

    applied = {}
    for key, env in _MAP.items():
        # os.environ.get() rather than 'env not in os.environ': an env var set
        # to the empty string is not a real override, and treating it as one
        # suppresses the file value and then reports the key as unset.
        if key in cfg and cfg[key] not in (None, "") and not os.environ.get(env):
            os.environ[env] = str(cfg[key])
            applied[env] = os.environ[env]

    # A file that exists, parsed, and contributed nothing is almost always a
    # mistake -- a misspelled key, or a table where a flat key was meant. Say
    # so, rather than letting the caller report the setting as simply unset.
    if not applied and not any(os.environ.get(env) for env in _MAP.values()):
        print(f"AMW-ERR: read {path} with {PARSER}, but found no recognized keys.")
        print(f"Recognized keys: {', '.join(sorted(_MAP))}")

    return applied


# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    if not CONFIG_FILE.is_file():
        print("\nAMW-ERR: PSO configuration file not found.")
        print(f"Expected:\n\t{CONFIG_FILE}")

        print("\nFrom the pypsa-zn repository root, run in PowerShell:")
        print(r"  Copy-Item .\pso.local.toml.example .\pso.local.toml")

        print("\nEdit pso.local.toml to configure:")
        print("  project     = absolute path to PSO.aimms")
        print("  python      = absolute path to PSO Python with aimmspy")
        print("  case        = ercot7k/texas7k.csv (baseline default)")
        print("  license_url = AIMMS license URL, if required")

        print("\nWindows 11 path requirements:")
        print("  - Use absolute paths for 'project' and 'python'.")
        print("  - Replace all backslashes (\\) with forward slashes (/).")
        print("  - Enclose paths in double quotes.")

        print("\nExample:")
        print('  project = "C:/AIMMS/PSO/PSO.aimms"')
        print('  python  = "C:/pypsa-zn/.venv-pso/Scripts/python.exe"')

        print("\nThen validate the environment:")
        print("  python pso_preflight.py")
        print("\nSee README.md -> PSO/AIMMS Environment Dependencies.\n")
        raise SystemExit(1)

    try:
        applied = load_config()
    except (ConfigError, OSError, ValueError) as exc:
        print(f"\nAMW-ERR: Cannot load pso.local.toml: {exc}")
        raise SystemExit(1)

    if applied:
        print(f"\nAMW-DBG::PSO configuration loaded from:\n\t{CONFIG_FILE}")
        for key, value in applied.items():
            print(f"  {key} = {value}")
    else:
        print("\nAMW-INFO: PSO configuration file exists.")
        print("No new settings applied; existing environment overrides may be active.")

    print("\nNext: python pso_preflight.py")

# ------------------------------------------------------------------------------
# END OF pso_config.py
# ------------------------------------------------------------------------------