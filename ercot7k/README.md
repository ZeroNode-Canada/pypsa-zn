# ercot7k - Texas7k 2030 WA case (per-unit VRE)

A 7132-bus, 9555-branch, 1063-injector synthetic ERCOT case built on
TAMU/Overbye's **Texas7k 2030** network, converted to PSO-native CSV input
tables. This is a **PSO-only** case: it is driven straight into PSO through
`aimmspy` (see `../ercot7k_pso.py`) and never touches PyPSA.

Until 2026-10-09 this directory held the 2018 `texas7k_fullcycle` case (6717
buses, 634 injectors, a 2018 April week, SC -> DA -> RT). Every stress and
datacenter number recorded before that date was measured on that case, not on
this one.

## What's here

- `texas7k*.csv` (29 files, ~44.5 MB) - the full set of PSO input tables plus
  `texas7k.csv`, the options/control file (`SelectedDataFile` target).

These tables are byte-identical to `texas7k2030_ercot_perunit`, built in the
`ercot-public-dataset` repo from commit `7801163`. That is the repo's
`pso/texas7k2030_ercot` case (as of `37b5e2e`, PR #43) with one table replaced:
`texas7k_SCH_TMP1.csv`, whose wind and solar availability comes per unit from
ERCOT's 60-day disclosures instead of regional series allocated by capacity
share. Its manifest and build notes are in `../ercot7k_geo/`.

Bus coordinates are deliberately NOT in this directory: every CSV here is read
as a PSO table and copied into each derived layer. They are in
`../ercot7k_geo/texas7k_bus_coords.csv` (enode, busnum, lat, lon, zone), all
7132 buses, taken from the 2030 AUX's substation coordinates.

## The case

- **Network:** 7132 buses, 9555 branches, 1063 injectors, 24 storage units,
  8 weather-zone areas.
- **Horizon:** `2026.06.15 00:00` -> `2026.06.22 00:00`, hourly (168 hours),
  inside a `2026.06.12` -> `2026.06.28` model window, per `texas7k_MDL_ID.csv`.
- **Cycle stack:** `SC` -> `SCEsr` -> `WA` -> `DA` -> `RT`, per
  `texas7k_CYC_ID.csv`.
- **Results:** a full run writes ~54 result files, ~850 MB. They are **not**
  committed - run the case locally.

`results_ED_Ara.csv` reports the eight zones AND area `0`, the system
aggregate. Sum the zones or read area `0`, never both.

## Known-good baseline

One run, 2026-10-09, local `PSO-3.3-Main` + AIMMS 26.1.4.12, 6m09s:

| Check | Value |
|---|---|
| Solves | 221, all `Optimal` (`results_MC_Solution.csv`) |
| Penalty | 0.00 on every cycle (`results_MC_Hrzn.csv`, `DeltaPenalty`) |
| Peak RT load | 82,591.9 MW at interval 161 (`results_ED_Ara.csv`, area `0`) |
| SC cycle cost | 231,236,413.4 (`DeltaCost` summed over `cyc=SC`) |
| SCEsr cycle cost | 154,948,993.8 |
| WA cycle cost | 155,711,676.0 |
| DA cycle cost | 159,776,821.1 |
| RT cycle cost | 124,640,771.0 |

The solve count matches the source build's own run (221, PSO
3.3.0-nightly.20261007). How far the costs move across PSO builds has NOT been
measured on this case; on the 2018 case DA and RT moved 0.4-0.8% between builds
(MIP gap) while SC was bit-exact. A solve count or peak load that differs at
all means the run is wrong; treat cost differences under ~1% as build noise
until measured otherwise.

For comparison, the same case with REGIONAL VRE (`37b5e2e` as shipped) gave 223
solves, all `Optimal`, zero penalty, the same 82,591.9 MW peak, and SC
220,387,837.4 / DA 152,279,423.3 / RT 125,425,602.6.

## Known issues

Carried from the source build notes, not re-measured here:

- The DA cycle drives batteries to full at every midnight.
- Placed dispatchable capacity is ~75% of June coincident peak, with no
  forced-outage derate, and June excludes the annual peak. Relevant if load is
  stressed upward.
- On the actual (SCED) side, 71,875 MWh over 7,329 unit-hours is clipped at
  each unit's own MaxMw.
- 313 VRE settlement points with no usable plant identity sit at
  region-consistent but not real locations.

## Running it

See `../ercot7k_pso.py` at the repo root, and its `Prerequisites` / `Setup`
section in the top-level `README.md`. In short:

1. Copy `pso.local.toml.example` -> `pso.local.toml` at the repo root and
   fill in `project` (path to your PSO.aimms) and, for an academic AIMMS
   license, `license_url`.
2. `python ercot7k_pso.py`

## Attribution

The Texas7k network is TAMU/Overbye synthetic data
(electricgrids.engr.tamu.edu), "free for commercial or non-commercial use,"
with a requested registration + paper citation. Load, offers and VRE
availability derive from ERCOT public reports. Full field-level provenance and
the attribution block live in the source dataset repo (`ercot-public-dataset`:
`SOURCE.md`, `LICENSE-DATA.md`, `pso/INPUT_SOURCES.md`). Read them before
publishing results or redistributing this case.
