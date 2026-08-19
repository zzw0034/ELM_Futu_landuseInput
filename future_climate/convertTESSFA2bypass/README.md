# convertTESSFA2bypass

Converts CanESM5-DBCCA SSP forcing on the **TESSFA2 (Southeast US) 4 km grid**
into ELM `CPL_BYPASS` input files covering 2024-2100.

Four scenarios (ssp119 / ssp245 / ssp370 / ssp585) x seven variables
(PRECTmms / FSDS / TBOT / QBOT / FLDS / PSRF / WIND) = 28 files, ~96 GiB each.

```
build_cpl_bypass_tessfa2.py   builds one file (one scenario, one variable)
run_scenario.sbatch           runs all 7 variables of one scenario on one node
README.md                     this file
```

A boreal counterpart (`convertTESSFA1bypass`) is expected; see
[Porting to TESSFA1](#porting-to-tessfa1).

## Running

```bash
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass
sbatch --export=ALL,SCENARIO=ssp119 run_scenario.sbatch
sbatch --export=ALL,SCENARIO=ssp245 run_scenario.sbatch
sbatch --export=ALL,SCENARIO=ssp370 run_scenario.sbatch
sbatch --export=ALL,SCENARIO=ssp585 run_scenario.sbatch
```

Four submissions put the four scenarios on four separate nodes
(`--exclusive`). Output lands in `/scratch/hpcl-cli185/zw5/future_clim/<scenario>/`
together with a copy of `zone_mappings.txt`.

A single variable, if needed:

```bash
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
$PY build_cpl_bypass_tessfa2.py --scenario ssp245 --var TBOT
```

Measured on 2026-08-18: **~4-5 min per variable**, 30 min to 1 h 50 min per
scenario depending on which node it lands on. All 28 files completed in one
evening.

**`/scratch` is purged periodically.** Move the finished files somewhere
durable under `/projects` and update `metdata_bypass` before the production
runs.

## What the script does

1. Reads the monthly 3-hourly `clmforc` source files for the requested
   scenario and variable.
2. Strips Feb 29 from leap years — the source calendar is Gregorian, the
   model runs `CALENDAR=NO_LEAP` (fixed 365 days, 2920 3-hourly steps/year).
3. Reindexes each month from `(time, lat, lon)` to the flattened
   `n = ilon*NLAT + ilat` order that `zone_mappings.txt` defines.
4. Packs to `int16` using the same `add_offset`/`scale_factor` convention as
   the historical production script (`makezones_reanalysis.f90`), so decoded
   values are directly comparable to the historical forcing. Ocean/invalid
   cells get the same raw sentinel values the historical files use.
5. Writes one small staging file per year, in parallel, then merges them into
   the final file row-chunk by row-chunk.
6. Renames `.partial` → final name only after everything is written and
   closed, and deletes the staging directory.

### The dummy year

The output spans **2023-2100**, but 2023 is not real data. It is a
placeholder year filled entirely with the ocean sentinel value.

It exists because the patched reader (`lnd_import_export.F90`,
`metdata_type='era5-daymet-fut'`) sets `startyear_met = 2023`. A shared
bound-check in that reader wraps `tindex` back to record 1 when the model
year equals `startyear_met`, which would silently corrupt the first year of a
run starting in 2024. Setting `startyear_met` one year early moves that
wraparound onto a record that is never legitimately read. If it ever *is*
read, the sentinel decodes to an obviously out-of-range value and the run
fails loudly instead of quietly using wrong forcing.

Real forcing begins at `DTIME` index 2920 (2024-01-01 00:00Z).

## Two things that are easy to get wrong

Both of these cost days of debugging in August 2026 and are the reason the
script is written the way it is.

### 1. Never set a netCDF attribute after declaring the big variable

These are classic (`NETCDF3_64BIT_OFFSET`) files, whose header sits at the
front of the file. A header that grows shifts — and therefore rewrites —
everything behind it, which here is the entire ~96 GiB packed variable.
netCDF4-python wraps *each* individually-set attribute on a NETCDF3 file in
its own `nc_redef`/`nc_enddef` pair (its own `setncatts` docstring says so),
so setting the ~9 attributes these files carry after declaring the big
variable meant ~9 full-file rewrites. Symptom: "creating the final file" ran
for **hours** with no log output and no data on disk, while `du` showed the
file slowly filling with zeros.

Neither reordering the attributes nor batching them with `setncatts()` fixes
it completely — `add_offset`/`scale_factor` cannot be set until the variable
exists, and that one remaining call still costs a full rewrite (~37 min).

The fix is `build_header_with_ncgen()`: `ncgen -6 -x` writes dimensions,
variables and every attribute in a single define session, exactly as the
historical Fortran producer does. Measured **0.1 s and 0 bytes written** for
a 95.7 GiB header. Data then goes in through `mode="a"`, which never touches
the header.

**Adding an attribute after that point brings the whole problem back.**

### 2. There are two different files named `zone_mappings.txt`

Use the copy **inside** `cpl_bypass_full/`, not the one in the parent
`Daymet_ERA5_TESSFA2/` directory:

- parent copy: zones 2-7, `grid_map` restarting within each zone
- `cpl_bypass_full/` copy: every zone flattened to 1, single global
  1..225625 index — **this is what the model actually reads**, because
  `metdata_bypass` points at `cpl_bypass_full/`

Only the lon/lat columns are read by this script, and those are identical
between the two, so a wrong choice here does not corrupt the forcing values —
but the copy placed next to the output files must be the right one, or the
model run will fail.

## Why staging + row-major merge

The obvious approach — write year by year straight into the final file — is
about **23x slower**. The final layout is `(n, DTIME)` with `DTIME` the
fastest-varying dimension (required: it matches the historical files and the
reader's per-column full-time-series reads). A write covering one year but
all rows therefore touches every one of the 225,625 rows non-contiguously.

Staging first turns this around: each year is written to its own small file
(in parallel, one worker per year), then the merge walks the final file in
row chunks, assembling each row's complete 78-year series from the staged
files and writing it as one contiguous block.

Measured head-to-head, same node, same resources, same variable: **1.6 h vs
4.3 min**, with byte-identical output.

## Porting to TESSFA1

Copy this directory to `convertTESSFA1bypass` and change the constants
below. Everything else — the ncgen header construction, the staging and
row-major merge, the dummy-year design, the Feb 29 handling — is
domain-independent.

| Constant | TESSFA2 value | For TESSFA1 |
|---|---|---|
| `TESSFA2_ROOT` | `/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5` | boreal source root |
| source subdir pattern | `CanESM5_<scen>_r1i1p1f1_DBCCA_Daymet_TESSFA2` | rename |
| `ZONE_MAPPINGS` | `.../Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt` | boreal domain's own copy — re-read the caveat above |
| `NLON, NLAT` | `625, 361` | boreal grid; `NCELL` follows |
| `RES_HOURS` | `3` | check the boreal timestep; `STEPS_PER_DAY` / `STEPS_PER_YEAR` follow |
| `OCEAN_SENTINEL_RAW` | per-variable int16 | **re-extract from the boreal historical files** — do not reuse these |
| `VARS` packing ranges | from `makezones_reanalysis.f90` | keep whatever the boreal historical files used |
| output filename | `DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc` | must match what the Fortran reader builds |
| `OUT_ROOT` | `/scratch/hpcl-cli185/zw5/future_clim` | separate directory |

Also required:

- `lnd_import_export.F90` needs a `metdata_type` branch constructing the
  TESSFA1 filename, with the right `startyear_met` / `endyear_met_trans`.
- Confirm the boreal source calendar. This pipeline strips Feb 29 because the
  source is Gregorian; if the boreal product is already 365-day, the strip
  becomes a no-op but `read_month`'s step-count assertion still has to match.
