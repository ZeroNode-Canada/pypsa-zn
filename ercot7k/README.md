# ercot7k - Texas7k full-cycle PSO case

A 6717-bus, 9140-branch, 634-injector synthetic ERCOT case (TAMU/Overbye's
**Texas7k**), converted to PSO-native CSV input tables. This is a **PSO-only**
case: it is driven straight into PSO through `aimmspy` (see
`../ercot7k_pso.py`) and never touches PyPSA.

## What's here

- `texas7k*.csv` (24 files, ~4.89 MB) - the full set of PSO input tables plus
  `texas7k.csv`, the options/control file (`SelectedDataFile` target).

These tables are copied byte-identical from the `ercot-public-dataset` repo's
`pso/texas7k_fullcycle/` case directory. The `results/` and `runs/`
subdirectories from that source are **not** included here - this case is
meant to be solved locally, not shipped with pre-solved output.

## The case

- **Network:** 6717 buses, 9140 branches, 634 injectors (generators).
- **Horizon:** `2018.04.09 00:00` -> `2018.04.16 00:00`, hourly (168 hours),
  per `texas7k_MDL_ID.csv`.
- **Cycle stack:** `SC` (security-constrained, 24 h lead) -> `DA`
  (day-ahead, 24 h lead) -> `RT` (real-time, 1 h), per `texas7k_CYC_ID.csv`.
- **Scale:** roughly 188 solves across the horizon / cycle stack, ~3-4
  minutes wall clock on PSO 3.3 (BETA 2026-07-14) + AIMMS 26.1.4.12 with
  CPLEX.
- **Results:** a full run writes ~47 result files, ~459 MB total. These are
  **not** committed to the repo - run the case locally and inspect them from
  the run's own results directory. Peak served load on the RT cycle is
  ~46,795 MW (this is a spring week; do not expect a summer-peak figure).

## Data vintage - read this before interpreting results

This is an **illustrative synthetic blend, not a replay of any single year**:

- grid topology and generation fleet: roughly 2021
- offer economics: derived from roughly 2021 ERCOT SCED data
- load and renewable profiles: **2018** ARPA-E PERFORM weather/load series

So the hours are 2018 weather driving a 2021 fleet at 2021 offer prices. It is
built for demonstration and training, and it is not a hindcast.

## Known issues

- **Negative offers.** `San Miguel 1` offers at about -$249/MWh, and 468
  injector-rows carry a negative `CostTotal`. This is the first thing a
  power-markets reader tends to find in an LMP plot, so it is called out here
  rather than left to be discovered. A fix is in progress upstream; until then,
  treat the low tail of the price surface with suspicion.

## Known-good baseline

A clean run of this case should reproduce:

| Check | Value | Reproducible? |
|---|---|---|
| Solves | 190, all `Optimal` (`results_MC_Solution.csv`) | exactly |
| Peak RT area load | 46,794.5 MW at interval 184 (`results_ED_Ara.csv`) | exactly |
| SC cycle cost | 11,727,676.8 (`results_MC_Hrzn.csv`, `DeltaCost` summed over `cyc=SC`) | exactly |
| DA cycle cost | about 20.3M | within the MIP gap |
| RT cycle cost | about 12.0M | within the MIP gap |

**Do not expect the DA and RT costs to match to the digit across builds.** DA
carries about 10,700 integer variables and is solved to `MipGap` 0.005, so a
different PSO build or solver version lands on a different incumbent inside
that gap - the runs above differ by 0.4%. RT is an LP but inherits DA's
commitment through the cycle chain, so it carries the same variation (0.8%
observed). SC is an LP with nothing upstream, which is why it is bit-exact and
is the better regression check of the three.

If the solve count, the optimal status or the peak load differ at all, or the
costs move by more than about 1%, something is wrong with the run and no
interpretation is worth doing yet.

Note `ED_Ara.Load` is fixed input load and does not fall when load is shed, so
it confirms the case was read - not that it was served.

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
with a requested registration + paper citation. Several other inputs (ARPA-E
PERFORM forecast/actual series, EIA, HIFLD) carry their own attribution
requirements, mostly CC-BY.

Full field-level provenance and the complete attribution block live in the
source dataset repo (`ercot-public-dataset`: `SOURCE.md`, `LICENSE-DATA.md`,
`pso/INPUT_SOURCES.md`) and are **not** duplicated here yet. They follow in a
separate change. Read them before publishing results or redistributing this
case.
