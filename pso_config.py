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

import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # 3.10 backport, if installed
    except ModuleNotFoundError:
        tomllib = None

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


def load_config(path: Path = CONFIG_FILE) -> dict:
    """Apply pso.local.toml as env defaults (existing env vars take precedence)."""
    if tomllib is None or not Path(path).is_file():
        return {}
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    applied = {}
    for key, env in _MAP.items():
        if key in cfg and cfg[key] not in (None, "") and env not in os.environ:
            os.environ[env] = str(cfg[key])
            applied[env] = os.environ[env]
    return applied


if __name__ == "__main__":
    applied = load_config()
    if applied:
        print(f"loaded {CONFIG_FILE}:")
        for k, v in applied.items():
            print(f"  {k} = {v}")
    else:
        print(f"no config applied (missing {CONFIG_FILE} or all keys already in env)")
