# convertTESSFA2bypass

Converts CanESM5-DBCCA SSP forcing on the **TESSFA2 (Southeast US) 4km grid**
into ELM `CPL_BYPASS` input files, 2024-2100, for four scenarios
(ssp119/ssp245/ssp370/ssp585) x seven variables
(PRECTmms/FSDS/TBOT/QBOT/FLDS/PSRF/WIND) = 28 files, ~96 GiB each.

A parallel `convertTESSFA1bypass` for the boreal domain is expected; see
[Porting to TESSFA1](#porting-to-tessfa1) for exactly what changes.

For the design rationale behind the dummy year, ocean sentinels, calendar
handling and the `lnd_import_export.F90` patch, see
[`README_cpl_bypass_future.md`](README_cpl_bypass_future.md).

## Layout

```
scripts/
  10_build_future_cpl_bypass.py         Approach A + all shared helpers
                                        (read_month, pack_month,
                                        build_header_with_ncgen, constants)
  11_build_future_cpl_bypass_rowmajor.py  Approach B -- USE THIS ONE
  verify_output_against_source.py       re-packs source months, compares values
  verify_elm_readable.py                structural check vs the historical file
jobs/
  run_scenario_all_vars.sbatch          production driver: one scenario,
                                        all 7 variables, one exclusive node
  submit_future_cpl_bypass_rowmajor.sbatch   single variable, Approach B
  submit_future_cpl_bypass.sbatch             single variable, Approach A
benchmarks/                             how the current design was arrived at
archive/                                superseded one-off drivers
```

`11_*.py` imports `10_*.py` by filename from its own directory, so the two
must stay side by side.

## Running

```bash
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass
sbatch --export=ALL,SCENARIO=ssp119 jobs/run_scenario_all_vars.sbatch
```

Submit once per scenario to put all four on separate nodes (`--exclusive`).
Measured 2026-08-18: ~4-5 min per variable, 30 min-1h50m per scenario
depending on which node it lands on. Output goes to
`/scratch/hpcl-cli185/zw5/future_clim/<scenario>/`, which is **purged
periodically** -- move the files somewhere durable before the actual runs.

Then verify:

```bash
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
$PY scripts/verify_elm_readable.py <file.nc> <VAR>              # structure
$PY scripts/verify_output_against_source.py <file.nc> <scen> <VAR>  # values
```

## Two things that are easy to get wrong

Both cost multiple days of debugging in August 2026 and are the reason this
pipeline looks the way it does.

**1. Never set a netCDF attribute after declaring the big variable.**
These are classic (`NETCDF3_64BIT_OFFSET`) files, whose header sits at the
front. netCDF4-python wraps *each* individually-set attribute on a NETCDF3
file in its own `nc_redef`/`nc_enddef` pair (its own `setncatts` docstring
says so), and a header that grows shifts -- and therefore rewrites -- the
entire ~96 GiB variable region behind it. Setting the 8-9 attributes these
files carry that way meant 8-9 full-file rewrites: "creating the final
file" ran for hours with no visible progress and no data on disk. Reordering
and `setncatts()` batching only get it down to 1 rewrite, because
`add_offset`/`scale_factor` cannot be set until the variable exists.

The fix is `build_header_with_ncgen()`: `ncgen -6 -x` writes dimensions,
variables and every attribute in a single define session, exactly as the
historical Fortran producer (`makezones_reanalysis.f90`) does. Measured
**0.1 s and 0 bytes written** for a 95.7 GiB header. Data is then written
through `mode="a"`, which never touches the header. **Adding an attribute
after that point reintroduces the whole problem.**

**2. `zone_mappings.txt` -- there are two different files with that name.**
Use the one *inside* `cpl_bypass_full/`, not the one in the parent
`Daymet_ERA5_TESSFA2/` directory. The parent copy has zones 2-7 with
`grid_map` restarting per zone; the `cpl_bypass_full/` copy has every zone
flattened to 1 with a single global 1..225625 index, and that is what the
model actually reads.

## Approach A vs Approach B

Same packing code, different way of getting bytes to disk.

- **A** (`10_*.py`) writes year by year into the final file. Each write
  covers a narrow DTIME slice across all 225,625 rows, and `DTIME` is the
  fastest-varying dimension, so every write touches every row
  non-contiguously.
- **B** (`11_*.py`) stages one small file per year (written in parallel, one
  worker per year), then merges row-chunk by row-chunk: each row's full
  78-year series is assembled and written as one contiguous block.

Measured head-to-head on the same filesystem, same resources, same variable
(2026-08-18, after the ncgen fix removed the header cost that had been
masking the difference): **A ~1.6 h, B 4.3 min -- ~23x.** B's output was
verified byte-identical to A's. Use B.

## Porting to TESSFA1

Copy this directory to `convertTESSFA1bypass` and change the following.
Everything else -- the ncgen header construction, the staging/row-major
merge, the dummy-year trick, the verification scripts' logic -- is
domain-independent.

In `scripts/10_build_future_cpl_bypass.py`:

| Constant | TESSFA2 value | Notes for TESSFA1 |
|---|---|---|
| `TESSFA2_ROOT` | `/projects/hpcl-cli185/proj-shared/TESSFA/CanESM5` | source root for the boreal product |
| source subdir | `CanESM5_<scen>_r1i1p1f1_DBCCA_Daymet_TESSFA2` | rename to the TESSFA1 equivalent |
| `ZONE_MAPPINGS` | `.../Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt` | must be the boreal domain's own; re-read the caveat above |
| `NLON, NLAT` | `625, 361` | boreal grid dimensions; `NCELL` follows |
| `RES_HOURS` | `3` | check the boreal product's timestep -- `STEPS_PER_DAY`/`STEPS_PER_YEAR` follow |
| `OCEAN_SENTINEL_RAW` | per-variable int16 values | **re-extract from the boreal historical file**; do not reuse these |
| `VARS` packing ranges | `data_ranges` from `makezones_reanalysis.f90` | keep whatever the boreal historical files used, so `add_offset`/`scale_factor` match |
| output filename | `DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z01.nc` | must match what the Fortran reader builds |
| `OUT_ROOT` | `/scratch/hpcl-cli185/zw5/future_clim` | pick a separate directory |

Also:

- `lnd_import_export.F90` needs its own `metdata_type` branch (or a shared
  one) constructing the TESSFA1 filename, with the right
  `startyear_met`/`endyear_met_trans`.
- `verify_elm_readable.py` hardcodes `HIST_DIR`, the historical filename
  pattern `Daymet_ERA5_TESSFA.4km_<VAR>_1980-2023_z01.nc`, and the domain
  bounds it checks (`lon [-100,-74]`, `lat [25,40]`). All three are TESSFA2.
- Confirm the boreal source calendar. This pipeline strips Feb 29 because
  the source is Gregorian and the model runs `NO_LEAP`; if the boreal
  product is already 365-day, `read_month`'s strip becomes a no-op but the
  step-count assertion still needs to match.
