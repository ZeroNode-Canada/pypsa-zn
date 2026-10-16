# Datacenter + BYOG injector templates (Texas7k PSO case)

Template rows for one datacenter site, `DC1`, with three behind-the-meter (BYOG) options:
solar PV, a battery (ESR) and a gas combustion turbine (CT). Headers match the Texas7k
case files (`ercot7k/texas7k_*.csv`).

**Every number is a placeholder.** Replace them with the project data.

| File | What it holds |
|---|---|
| `DC1_INJ_ID.csv` | The four injectors: capacity, ramp rates, energy cost |
| `DC1_INJ_CMT.csv` | Commitment data, CT only (see below) |
| `DC1_SCH_TMP.csv` | Hourly schedules: datacenter load, PV forecast, PV actual |
| `DC1_ESR_ID.csv` | The battery's energy reservoir: size, efficiency, starting charge |

## The injectors

- **Datacenter (`DC1_LOAD`)**: `LoadFlag=1`, 1,000 MW. Its hourly profile is
  `DC1_LOAD_sch` (flat 1,000 MW in the template).
- **PV (`DC1_PV`)**: 300 MW nameplate. Its hourly availability is `DC1_PV_fcst`
  (forecast) and `DC1_PV_act` (actual). The template shape is an existing Texas7k solar
  unit scaled to 300 MW, with forecast = actual.
- **Battery (`DC1_ESR`)**: 250 MW. `MinMw=-250` is charging; a battery does **not** use
  `LoadFlag`. Charge and discharge limits can differ: the charge limit is `|MinMw|`.
  The energy side is in `ESR_ID`: 1,000 MWh (4 h at 250 MW), starting half full (500 MWh),
  and 0.922 efficiency each way, copied from the case's existing batteries. The reservoir
  has the same name as the injector, which is how PSO pairs them.
- **Gas CT (`DC1_CT`)**: 230 MW, $45/MWh, 15 MW/min ramp. Commitment: 100 MW minimum
  dispatch, 1 h minimum on/off, $1,025 start cost, 15 min start time.

## Why only the CT has an INJ_CMT row

PSO enforces commitment only when `MinDispatch` or `BaseCost` is non-zero.

- The datacenter is a fixed load, so it has nothing to commit.
- PV dispatches anywhere from 0 to its availability.
- A battery modelled as one injector cannot have a `MinDispatch`.

## Schedules

Each schedule covers every hour from `MDL_ID.MinDate` to `MaxDate` inclusive, not just the
168 h study week. SC and DA look past the week, and a schedule reads zero after its last
point. Every row has `Enforce=1`. Without it PSO ignores zero values, so PV's night-time
zeros would fall back to the 300 MW nameplate.
