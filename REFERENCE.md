# Chen2022 → ELM Land-Use Pipeline (Pathfinder)

**Purpose**: Single source of truth for *how* the pipeline works — data format, Chen→ELM mapping, aggregation method, I/O schema, and the canonical run commands on Pathfinder.

**Scope**: Everything runs on Pathfinder (`pflogin3.ornl.gov`). This is the only supported environment.

Project root:
```
/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
```

---

## 1. Input Data Layout

```
data/external/chen2022_1km/
  global_PFT_2015.tif                           # historical, 2015 (20 classes, EPSG:6933, 1 km)
  SSP1_RCP19/global_PFT_SSP1_RCP19_{YEAR}.tif  # YEAR = 2020, 2025, …, 2100
  SSP1_RCP26/…
  SSP2_RCP45/…
  SSP3_RCP70/…
  SSP4_RCP34/…
  SSP4_RCP60/…
  SSP5_RCP34/…
  SSP5_RCP85/…
  readme.txt                                    # original 20-class legend
```

Each raster: `int8`, nodata = `-128`, EPSG:6933 (NSIDC EASE-Grid 2.0, 1 km equal-area).

All 8 scenarios × 17 years (2020:2100:5) plus the 2015 historical raster are present on disk.

---

## 2. Code Layout

```
src/elm_landuse/
  chen_classes.py               20-class names + Chen→ELM mapping (17 PFTs + 4 special cols)
  raster_io.py                  locate .tifs, read subsets by lon/lat bbox
  aggregate.py                  per-class fractional aggregation onto a target lat/lon grid
  common_legend.py              10-class common legend + NLCD/Chen LUTs (§10)

scripts/
  01_chen2022_to_elm_landuse.py Chen 1 km → ELM-PFT NetCDF (`--like` copies a target grid)
  02_harmonize_seus.py          §13 harmonizer; ELM forcing = `--build-timeseries`
  analysis/                     diagnostics, comparisons, figures (03–10, 20–23, 30–34, 50–55)

jobs/
  submit_landuse.sbatch              Chen → CONUS 1/24° (comparison product)
  submit_chen_targetgrid.sbatch      Chen → target SEUS grid (4 SSPs)
  submit_chen_targetgrid_ssp370.sbatch  same, SSP3_RCP70 only
  submit_landuse_future_array.sbatch 02 --build-timeseries (4 SSPs as an array;
                                      preferred for current full rebuilds)
  submit_landuse_future.sbatch       02 --build-timeseries (SSP1/2/5 legacy partial rerun)
  submit_landuse_future_ssp370.sbatch   same, SSP3_RCP70 only legacy partial rerun
  submit_*.sbatch                    matching analysis/figure drivers

outputs/
  processed/                    deliverables (Chen CONUS files + ELM landuse.timeseries)
  interim/                      target-grid Chen files, diag npz, cached tables
  figures/                      QA and comparison figures
  logs/                         SLURM stdout/stderr
```

There is no `pyproject.toml` and the package is not installed — `src/` must be on `PYTHONPATH` (see §6). Plot/analysis scripts live in `scripts/analysis/`; `plot_area_timeseries.py` is standalone and does not import `elm_landuse`.

**Directory rule**: `data/` is inputs only — nothing under it is ever written by this code. Everything generated goes under `outputs/`, so the whole tree can be deleted and rebuilt from `data/external/` + `scripts/`.

**interim vs processed**: the boundary is *"is this the thing we set out to produce?"*

- `processed/` — (1) Chen2022 converted to the ELM PFT classification at 1/24° (`01`); (2) the ELM-readable SEUS `landuse.timeseries` 2024–2100 files (`02 --build-timeseries`). See `FUTURE_LANDUSE_TIMESERIES.md`.
- `interim/` — target-grid Chen files, diagnostic npz, native-resolution counts, and other intermediates.

The Chen CONUS 1/24° runs (`jobs/submit_landuse.sbatch`) are the comparison product used in §10–§12. The ELM forcing path re-aggregates Chen onto the **target** `landuse.timeseries` grid (`01 --like <target>`), then harmonizes (`02 --build-timeseries`). Do not crop the CONUS Chen file onto the target grid — the grids differ by a half-cell offset and 1° of southern extent (`FUTURE_LANDUSE_TIMESERIES.md` §7).

---

## 3. Chen → ELM Mapping

| Chen class | ELM destination |
|---|---|
| 1 Water | `PCT_LAKE` |
| 2–15, 17 (vegetation & barren) | `PCT_NATVEG` → `PCT_NAT_PFT` array |
| 9 Needleleaf deciduous tree | PFT 3 (`needleleaf_deciduous_boreal_tree`), remapped to PFT 1 south of 45°N (see §4) |
| 16 Mixed C3/C4 grass | split 50/50 → PFT 13 (`c3_non-arctic_grass`) + PFT 14 (`c4_grass`) |
| 17 Barren | PFT 0 (`not_vegetated`) |
| 18 Cropland | **PFT 15 (`crop`) inside `PCT_NATVEG`** — *not* `PCT_CROP`; see below |
| 19 Urban | `PCT_URBAN` |
| 20 Permanent snow/ice | `PCT_GLACIER` |

`PCT_NATVEG + PCT_CROP + PCT_LAKE + PCT_URBAN + PCT_GLACIER` sums to 100 over valid cells.

**`PCT_CROP` is always zero, by design.** Chen class 18 (Cropland) is routed to natural PFT 15 (`crop`) and so is carried inside `PCT_NATVEG` / `PCT_NAT_PFT`, leaving the separate `PCT_CROP` column empty (`chen_classes.py`, class 18). This is the usual simplification for runs that do not use the ELM crop submodel. Cropland is *not* missing — to get crop area, read `PCT_NAT_PFT[natpft=15]`, not `PCT_CROP` (for CONUS 2015 that is ≈1.76 million km², vs 0.0 in `PCT_CROP`).

`PCT_WETLAND` is always zero too, for a different reason: Chen2022 has no wetland class.

---

## 4. Aggregation Method

For each Chen class `c` and each output (lat/lon) cell, the fraction of source 1 km pixels of class `c` falling inside that cell is computed using `rasterio.warp.reproject` with `Resampling.average`. Because source pixels are equal-area (EASE-Grid 2.0), this average is the area-weighted fractional coverage. Results are renormalized by the fraction of source pixels that were valid (not nodata).

Only the source window covering the requested bbox is read into memory — processing a limited region (SEUS, CONUS) is fast even with global 1 km input.

### Target domain

The production domain is taken from the NLCD ELM-PFT product:

```
/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc
```

| | |
|---|---|
| grid | 601 × 1441 (lat × lon), 1/24° |
| cell centers | lat `25.0 … 50.0`, lon `-125.0 … -65.0` |
| cell edges | lat `24.979166… … 50.020833…`, lon `-125.020833… … -64.979166…` |

Both products therefore sit on the same grid and can be compared cell by cell.

Pass `--like <REF.nc>` to copy this grid from the reference file. **Do not hand-write it as `--bbox -125 25 -65 50`**: `--bbox` takes cell **edges**, so those round numbers produce a 600 × 1440 grid offset by half a cell (1/48°) from the reference — wrong, and silently so. `--like` reads the reference's `lat`/`lon` centers and expands by half a cell for you (`TargetGrid.from_centers`).

**Post-aggregation lat remapping**: After `fractions_to_elm_columns()`, `remap_boreal_ndt_by_lat()` reassigns PFT 3 (needleleaf deciduous boreal) to PFT 1 (needleleaf evergreen temperate) for all grid cells south of 45°N. Chen class 9 carries no climate-zone label; boreal deciduous is ecologically implausible at mid/low latitudes (e.g. SEUS). PFT totals within `PCT_NATVEG` are conserved.

> **Fixed 2026-07-17.** The remap was passed ascending `lat_centers` while the aggregated array is north-up (row 0 = north, latitude descending), so the `lat < 45` mask ran upside-down — it remapped 30–50°N and *left* 25–30°N, so boreal larch (PFT 3) persisted up to 100% in Florida / the Gulf coast. The call site now passes `lat_centers[::-1]`. All five processed files were regenerated and verified: PFT 3 = 0 everywhere south of 45°N, and `PCT_NAT_PFT` still sums to 100 (the mass moved into PFT 1).

---

## 5. Output NetCDF Schema

Dimensions: `time` (years), `natpft` (17), `lat`, `lon`

| Variable | Dims | Units | Notes |
|---|---|---|---|
| `PCT_NATVEG` | time, lat, lon | % | natural vegetation column |
| `PCT_CROP` | time, lat, lon | % | cropland column |
| `PCT_LAKE` | time, lat, lon | % | inland water |
| `PCT_URBAN` | time, lat, lon | % | urban (sum over density classes) |
| `PCT_GLACIER` | time, lat, lon | % | permanent snow/ice |
| `PCT_WETLAND` | time, lat, lon | % | always 0 |
| `PCT_NAT_PFT` | time, natpft, lat, lon | % | sums to 100 within `PCT_NATVEG` |
| `pft_name` | natpft | — | string array of ELM PFT names |

All PCT fields: `float32`, range `[0, 100]`, zlib-compressed (level 4). Latitude is ascending in the file.

This is the Chen-on-grid **intermediate** (17 natural PFTs in `PCT_NAT_PFT`, named in `pft_name`) on a regular lat/lon grid. ELM cannot read it. The ELM-readable product is `landuse.timeseries_SEUS_1_24deg_nlcd2elm_<SSP>_simyr2024-2100.nc` from `scripts/02_harmonize_seus.py --build-timeseries` — see `FUTURE_LANDUSE_TIMESERIES.md`.

> **Not an ELM input file.** The deltas against a real `landuse.timeseries_*.nc` (compared against `/projects/hpcl-cli185/proj-shared/zw5/software/mksurfdata_map/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260415.nc`) are:
>
> - dims are `lat`/`lon`, not `lsmlat`/`lsmlon`; no 2-D `LONGXY`/`LATIXY`/`AREA`, no `LANDFRAC_PFT`/`PFTDATA_MASK`
> - `PCT_URBAN` is a single total; ELM wants it split over `numurbl`=3 density classes
> - no `HARVEST_*` / `GRAZING` fields
> - ELM's real files hold `PCT_NATVEG`/`PCT_CROP` time-invariant (2-D) and vary only `PCT_NAT_PFT`; ours are time-varying. Feeding transient crop area to ELM needs `do_transient_crops`, which also requires `PCT_CFT` — a crop-functional-type breakdown Chen2022 does not have (it has one undivided "Cropland" class).

---

## 6. Environment

The conda env `make_surfdata_pf` has everything the pipeline needs (python 3.13, rasterio 1.5, xarray, netCDF4, matplotlib, GDAL CLI tools):

```
/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf
```

Two equivalent ways to use it. **Absolute path (preferred — nothing to load, nothing to deactivate):**

```bash
export PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src
```

**Or activate it** (`~/.condarc` already points `envs_dirs` at `proj-shared/zw5/conda_envs`, so the short name resolves):

```bash
module load miniforge3/24.11.3-0
unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_SHLVL
source "$OLCF_MINIFORGE3_ROOT/etc/profile.d/conda.sh"
conda activate make_surfdata_pf
export PYTHONPATH=$PWD/src        # from the project root
```

Notes:
- `PYTHONPATH` is required either way — `elm_landuse` is not installed as a package.
- `cartopy` is **not** in the env, so `scripts/analysis/plot_seus_bbox.py` exits with `need library cartopy`. To enable it:
  `conda install -n make_surfdata_pf -c conda-forge cartopy`
- The GDAL CLI tools (`gdalinfo`, …) live in the env's `bin/`. Run them with the env activated, otherwise PROJ cannot find its database and warns `proj_create_from_database: Open of …/share/proj failed`. The python path (rasterio/pyproj) resolves PROJ correctly without activation.

---

## 7. Run Commands

Run from the project root. `$PY` / `PYTHONPATH` as in §6.

```bash
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput

# 2015 historical, Southeast US, 0.5°   (~5 s)
$PY scripts/01_chen2022_to_elm_landuse.py \
  --scenario historical --years 2015 \
  --bbox -95 24 -74 37.5 --resolution 0.5 \
  --out outputs/interim/chen2022_landuse_SEUS_2015_0p5deg.nc

# Transient SSP2_RCP45, 2015 + 2020..2100 step 5, SEUS 0.5°
$PY scripts/01_chen2022_to_elm_landuse.py \
  --scenario SSP2_RCP45 --years 2015 \
  --extra-years 2020:2100:5 \
  --bbox -95 24 -74 37.5 --resolution 0.5 \
  --out outputs/interim/chen2022_landuse_SEUS_SSP2_RCP45_0p5deg.nc

# Comparison product: CONUS 1/24° on the NLCD grid (§4)
# (~25 s per year → ~8 min for 18 years; use the batch job)
REF=/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc
$PY scripts/01_chen2022_to_elm_landuse.py \
  --scenario SSP2_RCP45 --years 2015 \
  --extra-years 2020:2100:5 \
  --like "$REF" \
  --out outputs/processed/chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc

# ELM forcing: Chen on the target landuse.timeseries grid, then harmonize
TGT=/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_smoothHARV_simyr1850-2023_c260723.nc
$PY scripts/01_chen2022_to_elm_landuse.py \
  --scenario SSP2_RCP45 --years 2015 \
  --extra-years 2020:2100:5 \
  --like "$TGT" \
  --out outputs/interim/chen_targetgrid_SSP2_RCP45_2015-2100_1_24deg.nc
$PY scripts/02_harmonize_seus.py --build-timeseries --scenario SSP2_RCP45 \
  --anchor-file "$TGT"
```

Quick-look QA figures — maps of one time slice, and total area per column vs year:

```bash
$PY scripts/analysis/plot_elm_landuse_maps.py \
  --in  outputs/interim/chen2022_landuse_SEUS_SSP2_RCP45_0p5deg.nc \
  --out outputs/figures/chen2022_landuse_SEUS_SSP2_RCP45_0p5deg.png

$PY scripts/analysis/plot_area_timeseries.py \
  --in  outputs/interim/chen2022_landuse_SEUS_SSP2_RCP45_0p5deg.nc \
  --out outputs/figures/area_timeseries_SEUS_SSP2_RCP45_0p5deg.png
```

SLURM batch jobs:

```bash
sbatch jobs/submit_landuse.sbatch              # Chen CONUS comparison files
sbatch jobs/submit_chen_targetgrid.sbatch      # Chen → target grid (4 SSPs)
sbatch jobs/submit_landuse_future_array.sbatch # 02 --build-timeseries (4 SSPs, current full rebuild)
squeue -u $USER
```

Edit the CONFIG block of `submit_landuse.sbatch` (`REGION_TAG`, `RES_TAG`, `SCENARIO`, `EXTRA_YEARS`, `YEARS_TAG`) before submitting a Chen CONUS run. The `*_TAG` values only build the output filenames and are not validated — keep them in sync with the values they describe. For the ELM forcing jobs, scenarios are listed in the sbatch loop; do not add SSP3_RCP70 to the 4-SSP loops (that would overwrite already-verified files — use the `*_ssp370.sbatch` scripts).

Current full ELM-forcing rebuilds use `submit_landuse_future_array.sbatch`
instead of the older split pair. The split pair remains useful for targeted
partial reruns, but the array is the accurate entry point when all four SSP
Default files must be regenerated together, for example after the 2026-08-28
smoothHARV harvest update. The current historical reference lineage is the
smoothHARV historical file
`landuse.timeseries_SEUS_1_24deg_nlcd2elm_smoothHARV_simyr1850-2023_c260723.nc`;
it has the same static/`PCT_NAT_PFT` anchor fields as c260723 and smoothed
historical `HARVEST_*`.

The job calls the env's python by absolute path, so no conda state has to be set up or torn down around `sbatch`, and all paths in it are absolute, so it can be submitted from any directory.

### Pathfinder SLURM specifics

`sbatch` **rejects** jobs that omit QOS or memory. The working header:

| Directive | Value | Note |
|---|---|---|
| `-A` | `hpcl-cli185` | account |
| `-p` | `hpcl-cli185` | project's dedicated 20-node partition (`blc161-180`); `serial` / `parallel` are the general-access alternatives |
| `-q` | `hpcl-cli185` | **required.** Partition `hpcl-cli185` only accepts the same-named QOS (`AllowQos=hpc-admins,hpcl-cli185`). Use `-q normal` on `serial`/`parallel` |
| `--mem` | `32g` | **required.** Job is rejected without it |

Also: SLURM runs the batch script from a spool copy, so `$0` does not point into the project — deriving the project root from `$0` (`dirname $(readlink -f "$0")/..`) lands in `/var/spool/slurmd` and fails. Use an absolute `PROJECT_ROOT`.

Runtime: ~25 s per year at CONUS 1/24°, so the full 18-year transient is ~8 min per run; the 1 h walltime has plenty of headroom.

---

## 8. Active Scenarios

All are on disk with the full 2020–2100 (step 5) series:

`SSP1_RCP19`, `SSP1_RCP26`, `SSP2_RCP45`, `SSP3_RCP70`, `SSP4_RCP34`, `SSP4_RCP60`, `SSP5_RCP34`, `SSP5_RCP85`

---

## 9. Known Constraints

- `PCT_WETLAND` is always zero; Chen2022 has no wetland class. If wetland forcing is needed, a separate data source must be blended in.
- 2015 exists only as the top-level historical raster (`global_PFT_2015.tif`). Any year ≠ 2015 requires a real SSP-RCP scenario directory; `--scenario historical` with a non-2015 year is an error.
- Class 16 "Mixed C3/C4 grass" is split 50/50 heuristically; no empirical basis for the ratio.
- Class 9 "Needleleaf deciduous tree" has no climate-zone label in Chen2022. It is mapped to PFT 3 (boreal) globally, then remapped to PFT 1 (temperate evergreen) south of 45°N. This is an approximation; PFT 1 and PFT 3 differ in phenology, but class 9 occurrence in SEUS is negligible.

---

## 10. NLCD vs Chen2022 Land-Cover Comparison

A side comparison of the two land-cover products over CONUS, independent of the
ELM pipeline in §1–§9. It answers: *how much of the Chen2022 land-use signal is
real land-cover change, and how much is a product/resolution artifact?*

**Both products are counted at their own native resolution.** NLCD (Albers) and
Chen2022 (EASE-Grid 2.0) are both equal-area, so `area = pixel_count ×
pixel_area` is exact and neither is resampled to produce the statistics.

### Code

```
src/elm_landuse/common_legend.py              10-class common legend + NLCD/Chen LUTs
scripts/analysis/20_landcover_native_stats.py native-resolution pixel counts -> JSON
scripts/analysis/21_landcover_map_data.py     1200 m display grid for the maps -> NPZ
scripts/analysis/22_landcover_tables.py       area tables -> CSV/TXT
scripts/analysis/23_landcover_figures.py      the five figures
jobs/submit_landcover_{stats,mapdata,figs}.sbatch
```

Run order: 20 → 21 → 22 → 23. Steps 20/21 take ~1 min each on 12 cores; step 23
must run under SLURM (it OOMs on a login node).

### Inputs

| | |
|---|---|
| NLCD | `/projects/hpcl-cli185/proj-shared/zdr/hires_data/landcover/NLCD/Annual_NLCD_LndCov_{2015,2020}_CU_C1V0.tif` — 160000×105000, 30 m, Albers, nodata 250 |
| Chen2022 | `data/external/chen2022_1km/` — 2015 historical + SSP{1_RCP19,2_RCP45,4_RCP60,5_RCP85}/2020 |

### Domain

CONUS as delineated by the **NLCD data footprint**. Chen2022 is global, so it is
restricted by warping the NLCD footprint onto Chen's own 1 km grid
(`build_conus_mask_on_chen`). Only the *mask* is warped; Chen class values are
read and counted at native 1 km. The two domains agree to **0.013%**
(NLCD 8,080,417 km² vs Chen mask 8,081,504 km²), so percentages of each
product's own total are directly comparable.

### Legend crosswalk

10 common classes (`common_legend.py`). Both legends collapse into it without
inventing information; the residual asymmetries *are* the result:

- **Chen has no wetland class.** NLCD's 490,198 km² of wetland must be absorbed
  by Chen's forest/grass/water. Reaching common code 9 from Chen is impossible.
- **Chen has no pasture class.** NLCD 81 (Pasture/Hay) vs 82 (Cultivated Crops)
  cannot both map onto Chen's single "Cropland", and which one it means is
  genuinely ambiguous — so 81 and 82 stay separate and both readings are
  reported (strict = 82 only, inclusive = 81+82).
- **Chen's nodata inside CONUS** (134,093 km²) is coastal/estuarine water its
  land mask drops but NLCD maps as Open Water. Chen `Water + nodata` = 412,467
  km² vs NLCD Water 416,332 km² (−0.9%), so it is reported as its own row rather
  than folded into Water.

### Headline result (2015)

| class | NLCD 30 m [km²] | Chen 1 km [km²] | Chen − NLCD |
|---|---:|---:|---:|
| Forest | 1,893,712 | 2,831,093 | **+937,381 (+49%)** |
| Grass | 984,573 | 1,546,580 | **+562,007 (+57%)** |
| Pasture/Hay | 548,952 | 0 | −548,952 (no Chen class) |
| Wetland | 490,198 | 0 | −490,198 (no Chen class) |
| Developed | 513,891 | 129,844 | **−384,047 (−75%)** |
| Shrub | 1,842,639 | 1,569,770 | −272,869 (−15%) |
| Cropland | 1,300,684 | 1,508,607 | +207,923 (+16%) |
| Water | 416,332 | 278,374 | −137,958 (−33%; see nodata above) |
| Barren | 88,701 | 82,743 | −5,958 (−7%) |
| Snow/Ice | 735 | 400 | −335 |

Chen's urban (129,844 km²) sits between NLCD's medium+high-intensity developed
(95,664 km²) and all developed incl. open space (513,891 km²): a 1 km pixel
cannot resolve the dispersed low-intensity development that dominates NLCD's
developed area.

### The load-bearing caveat for §1–§9

At 2020 — five years after the scenarios' common 2015 start — the **spread
across the four SSPs is far smaller than the NLCD-vs-Chen gap**:

| | max−min across SSPs | \|Chen−NLCD\| |
|---|---:|---:|
| Forest | 103,770 km² | 937,381 km² |
| Cropland | 173,753 km² | ~250,000 km² |
| Grass | 40,416 km² | 562,007 km² |

So a Chen2022-derived ELM surface dataset is **not interchangeable** with an
NLCD-derived one, and differences between an NLCD-based baseline and a
Chen-based scenario run at 2020 are dominated by product disagreement, not by
scenario. Chen2022's value is the *transient signal within one scenario*
(2020→2100 on a consistent product), not its absolute land cover. Comparing a
Chen2022 scenario against an NLCD-based historical baseline mixes the two and
should be avoided; anchor scenario runs to Chen's own 2015 instead.

### Outputs

```
outputs/interim/landcover_native_counts.json   raw native pixel counts
outputs/interim/landcover_map_data.npz         1200 m display grid
outputs/interim/landcover_areas_{2015,2020}.csv
outputs/interim/landcover_tables.txt
outputs/figures/fig1_conus_dominant_2015.png       CONUS maps, both products
outputs/figures/fig2_native_resolution_zoom.png    true 30 m vs true 1 km
outputs/figures/fig3_area_by_class_2015.png
outputs/figures/fig4_fraction_difference_2015.png  where they disagree
outputs/figures/fig5_area_by_class_2020_ssps.png   dataset gap vs scenario spread
```

`fig2` is the only figure showing the products as they actually are (no
decimation, no warping). The CONUS-wide panels use a 1200 m display grid —
160000×105000 does not fit in a figure, and a difference map needs one grid.
NLCD's display cells are exact 40×40 native-pixel blocks, so no resampling
filter touches it; the sub-grid class *fractions* are true.

---

## 11. NLCD-derived vs Chen2022-derived ELM PFT (apples-to-apples)

§10 compares the two *land-cover* products. This section compares the two
**ELM-PFT products** on the identical 1/24° grid — cell by cell, no regridding.

| | |
|---|---|
| NLCD-derived | `/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc` (time 1850–2023; 2015 = index 165, 2020 = index 170) |
| Chen2022-derived | `outputs/processed/chen2022_landuse_CONUS_{2015,SSP1_RCP19,SSP2_RCP45,SSP4_RCP60,SSP5_RCP85}_*.nc` (§5) |

```
scripts/analysis/30_elmpft_compare.py    tables + elmpft_compare.npz
scripts/analysis/31_elmpft_figures.py    fig6-fig9
jobs/submit_elmpft_{compare,figs}.sbatch
```

### Only PCT_NATVEG and PCT_NAT_PFT are comparable

**The two files do not share a schema.** The NLCD product has *only*
`PCT_NAT_PFT`, `PCT_NATVEG`, `PCT_URBAN(numurbl=3)` — there is no `PCT_CROP`,
`PCT_LAKE`, `PCT_GLACIER` or `PCT_WETLAND` column at all, and water is simply
absent from its budget (`PCT_NATVEG + PCT_URBAN` ≈ 100 over land, 0 over the
Great Lakes, and ~8 over the mostly-water NYC cell). Its `PCT_URBAN` also never
exceeds **33.5%** anywhere in CONUS, so it is not a percent-of-cell in the sense
Chen's single urban column is — **do not compare the urban columns.**

What *is* shared:

- `PCT_NATVEG` — % of the whole grid cell, both products.
- `PCT_NAT_PFT` — % within the natveg column, sums to 100 in both (checked), on
  the **ELM/CLM5 standard 17-PFT axis** — `elm_landuse.chen_classes.ELM_PFT_NAMES`,
  index = position in `PCT_PFT`. That list is the standard, not anything
  Chen-specific; any ELM PFT product follows it by construction.

**Where the PFT labels come from.** `ELM_PFT_NAMES` is the authority.
`01_chen2022_to_elm_landuse.py` writes it into the Chen output as `pft_name`,
and script 30 raises if the two ever disagree. The **NLCD file states nothing** —
no `pft_name`, no `natpft` coordinate, no global attributes — so for that side
the standard order is corroborated by geography instead of metadata: PFT 1 is
97% of natveg in the Oregon Coast Range (Douglas fir), PFT 7 is 92% in the
Kentucky Appalachians (deciduous), PFT 15 is 92% in rural Illinois (corn belt),
and the 9 unpopulated indices are exactly the boreal/arctic/tropical ones that
cannot occur in CONUS. Solid, but it is inference — if that file's producer ever
reorders the axis, nothing here would catch it.

`irrigated_crop` (index 16) is 0 in both products: `ELM_PFT_NAMES` marks it a
placeholder, and neither source product resolves irrigation.

Derived: `PFT area = cell_area × PCT_NATVEG/100 × PCT_NAT_PFT/100`.

Domain: CONUS = cells where the NLCD product carries land (`PCT_NATVEG +
PCT_URBAN > 0` at 2015) → 471,119 cells, 7,773,653 km² of grid-cell area. Chen
is global and must be masked to it.

### The 17-PFT axis is NOT apples-to-apples — aggregate before quoting

Four mapping conventions dominate the raw per-PFT ranking. All are *splits of a
source class the product could not actually resolve*, and each is a fixed ratio
rather than anything climate-driven — verify with the per-cell ratios, they are
degenerate:

1. **The NLCD product splits NLCD's single Shrub/Scrub class 50/50 into PFT 9
   (`broadleaf_evergreen_shrub`) and PFT 10 (`broadleaf_deciduous_temperate_shrub`).
   The two fields are elementwise identical — `max|PFT9 − PFT10| = 0.0` exactly.**
   PFT 9 therefore tops the disagreement ranking at −896,220 km² with zero
   ecological content. Only PFT 9+10+11 (Shrub) means anything.
2. **The NLCD product populates only 8 of 17 PFTs** (0, 1, 7, 9, 10, 13, 14, 15);
   Chen populates 14. Every boreal/arctic PFT is zero-by-construction on the
   NLCD side, so Chen's 53,627 km² of `needleleaf_evergreen_boreal_tree` etc.
   is a legend difference, not a land-cover difference.
3. **Chen splits Mixed C3/C4 grass 50/50 into PFT 13/14** (§3). In CONUS Chen's
   *pure* C4 class (class 15) has **zero** area, so every C4 km² it has comes
   from that 50/50 heuristic: the per-cell C4 share of (C3+C4) takes only the
   values **0 or exactly 0.5**.
4. **The NLCD product caps C4 at 20%.** Its per-cell C4 share of (C3+C4) has
   max = **0.2000** exactly, median 0.1735, and is essentially flat with
   latitude — ~17.5% in every 4° band from 25°N to 50°N. Real CONUS grasslands
   run from C4-dominated (>70%) in the southern Great Plains to C3-dominated in
   the Dakotas, so this split carries no physiological signal either.

So **PFT 13 vs 14 is as meaningless to compare as PFT 9 vs 10** — both sides are
convention, pulling in opposite directions (NLCD 82.5/17.5 C3:C4 vs Chen
62.6/37.4). The −494,935 km² on `c3_non-arctic_grass` and +264,223 km² on
`c4_grass` in the 2015 table are mostly those two conventions colliding, not
land cover.

Summing to functional groups removes all four. **Quote `fig8`, not `fig7`.**

### Result

`PCT_NATVEG` agrees well — the products differ by **+2.2%** over CONUS:

| | NLCD | Chen2022 | Chen−NLCD |
|---|---:|---:|---:|
| 2015 | 7,382,876 | 7,547,467 | +164,591 (+2.2%) |
| 2020 | 7,381,235 | 7,530,854 … 7,534,366 (4 SSPs) | +149,618 … +153,131 |

The residual is concentrated at cities, rivers and coasts (fig6): Chen at 1 km
cannot resolve the sub-pixel non-vegetated features NLCD sees at 30 m, so Chen
carries slightly *more* natveg there.

`PCT_NAT_PFT` by functional group, 2015 [km²]:

| group | NLCD | Chen2022 | Chen−NLCD |
|---|---:|---:|---:|
| Bare | 86,969 | 81,283 | −5,685 (−6.5%) |
| Tree | 2,400,369 | 2,858,456 | +458,087 (+19.1%) |
| Shrub | 1,846,275 | 1,568,994 | −277,281 (−15.0%) |
| Grass | 1,761,131 | 1,534,697 | −226,434 (−12.9%) |
| Crop | 1,288,132 | 1,504,037 | +215,905 (+16.8%) |

### Why this looks better than §10 — and what the NLCD→ELM mapping does

§10 (raw land cover) found Forest **+49.5%** and Grass **+57.1%**; here Tree is
+19.1% and Grass is **−12.9%** — a sign flip. Both are correct; the NLCD→ELM
conversion redistributes the classes Chen lacks. Cross-checking §10's raw
30 m areas against this section's PFT areas:

| | | |
|---|---|---|
| Barren → Bare | 88,701 → 86,969 | −2.0% — passes through |
| Shrub → Shrub | 1,842,639 → 1,846,275 | +0.2% — passes through |
| Cropland (82) → crop | 1,300,684 → 1,288,132 | −1.0% — passes through |
| Forest + **woody wetland** | 2,267,804 → Tree 2,400,369 | residual +132,565 |
| Grass + **pasture** + herb. wetland | 1,649,631 → Grass 1,761,131 | residual +111,500 |

Three groups pass through the mapping untouched (<2%), which pins down what it
does: **NLCD's woody wetland becomes Tree, and its pasture + herbaceous wetland
become Grass.** The two residuals sum to 244,065 km², consistent with the
vegetated remainder of NLCD's 513,891 km² of developed land being carried in
natveg (ELM `PCT_URBAN` absorbs only part of it).

So the §10 wetland/pasture gap does not disappear in PFT space — it is *hidden*
inside Tree and Grass. The NLCD-derived product has no wetland column either, so
neither ELM product represents wetland.

### Scenario spread vs product gap (2020) — same conclusion as §10

| PFT group | \|Chen(mean of SSPs) − NLCD\| | SSP max−min |
|---|---:|---:|
| crop | 264,381 km² | 172,707 km² |
| c3_non-arctic_grass | 525,576 km² | 35,033 km² |
| needleleaf_evergreen_temperate_tree | 401,174 km² | 50,128 km² |

Crop is the one PFT where scenario choice approaches product choice in
magnitude (SSP4-RCP6.0 is the outlier at 1,654,321 km²). For everything else the
product gap dominates by 5–15×. This reinforces §10: anchor Chen scenario runs
to Chen's own 2015, not to the NLCD-derived baseline.

### Outputs

```
outputs/interim/elmpft_compare_tables.txt   full 17-PFT tables, both years
outputs/interim/elmpft_areas.csv
outputs/interim/elmpft_compare.npz
outputs/figures/fig6_elmpft_natveg_2015.png       PCT_NATVEG + difference
outputs/figures/fig7_elmpft_per_pft_2015.png      all 17 PFTs, artifacts flagged
outputs/figures/fig8_elmpft_groups.png            functional groups <- quote this
outputs/figures/fig9_elmpft_group_diff_2015.png   where they disagree
```

### 11a. The 2020 slice on its own

`scripts/analysis/32_elmpft_2020.py` (job `jobs/submit_elmpft_2020.sbatch`) re-cuts §11 at
2020 only, reading the cached `elmpft_compare.npz` — run script 30 first.

Note `chen2022_landuse_CONUS_2015_1_24deg.nc` carries **2015 only** and cannot
enter a 2020 comparison; the Chen 2020 state comes from the four SSP files
(time index 1). All five share Chen's 2015 start, so at 2020 they are five
years apart — hence the spread panels.

**PCT_NATVEG 2020 [km²]** — the SSPs are essentially one field:

| | area | vs NLCD |
|---|---:|---:|
| NLCD-derived | 7,381,235 | — |
| SSP1-RCP1.9 | 7,532,780 | +151,545 (+2.1%) |
| SSP2-RCP4.5 | 7,532,634 | +151,399 (+2.1%) |
| SSP4-RCP6.0 | 7,534,366 | +153,131 (+2.1%) |
| SSP5-RCP8.5 | 7,530,854 | +149,618 (+2.0%) |
| **spread across the 4 SSPs** | **3,512** | vs a ~151,423 product gap → **43×** |

**Functional groups 2020 [km²]:**

| group | NLCD | SSP1-1.9 | SSP2-4.5 | SSP4-6.0 | SSP5-8.5 | gap | spread | gap/spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Bare | 86,775 | 74,218 | 64,530 | 38,059 | 71,841 | −24,612 | 36,158 | **0.7×** |
| Tree | 2,399,593 | 2,898,160 | 2,861,957 | 2,795,199 | 2,848,704 | +451,412 | 102,961 | 4.4× |
| Shrub | 1,847,671 | 1,576,999 | 1,577,317 | 1,550,266 | 1,568,092 | −279,502 | 27,051 | 10.3× |
| Grass | 1,770,494 | 1,501,789 | 1,504,286 | 1,496,521 | 1,538,361 | −260,255 | 41,839 | 6.2× |
| Crop | 1,276,703 | 1,481,614 | 1,524,544 | 1,654,321 | 1,503,856 | +264,381 | 172,707 | 1.5× |

Two things worth knowing beyond "the product gap dominates":

- **Bare_Ground is the one exception** (gap/spread = 0.7×): the SSPs disagree
  about bare ground *more* than the products do. SSP4-RCP6.0 has roughly half
  the bare ground of SSP1-RCP1.9 (38,059 vs 74,218 km²) and correspondingly the
  most cropland (1,654,321 km²) — cropland expanding onto barren land is the one
  place where scenario choice is the leading term at 2020.
- **Crop is the runner-up** at 1.5×, again driven by SSP4-RCP6.0.

For Shrub/Grass/Tree the product gap is 4–10× the scenario spread, so those
three carry essentially no scenario information at 2020.

The `PCT_NATVEG` SSP-spread map (fig10, bottom right) is near-zero everywhere
except **hot spots at urban fringes** — what little the scenarios disagree about
five years in is where cities expand.

```
outputs/interim/elmpft_2020_tables.txt
outputs/figures/fig10_elmpft_natveg_2020.png      NLCD | Chen | gap | SSP spread
outputs/figures/fig11_elmpft_per_pft_2020.png     all 17 PFTs, artifacts flagged
outputs/figures/fig12_elmpft_groups_2020.png      groups + gap-vs-spread ratios
outputs/figures/fig13_elmpft_group_diff_2020.png  where they disagree
```

### 11b. Both years side by side, and the 2015→2020 signal

`scripts/analysis/33_elmpft_maps_2015_2020.py` (job `jobs/submit_elmpft_maps1520.sbatch`),
reading the cached `elmpft_compare.npz`.

**fig14** — dominant functional group within natveg, (NLCD | Chen) × (2015 | 2020).
Mapped as *functional group*, not raw PFT: PFT 9/10 are an exact 50/50 tie on the
NLCD side, so a per-PFT `argmax` would be decided by tie-breaking, not data.

A dominant-class map amplifies near-ties, so the eye over-reads it — the script
therefore counts the flips instead of leaving it to the caption:

| dominant group differs | share of the 469,811 valid cells |
|---|---:|
| NLCD 2015 vs NLCD 2020 (temporal, observed) | **1.2%** |
| Chen 2015 vs Chen 2020 (temporal, projected) | **2.1%** |
| NLCD vs Chen, both 2015 (product) | **17.1%** |
| NLCD vs Chen, both 2020 (product) | **16.8%** |

The product gap is 8–14× either product's 5-year signal — §11's conclusion, now
in map form.

**fig15** — what each product says changed over 2015→2020, each measured against
its *own* 2015 (so the mean-state offset of §11 cancels). This is the one window
where Chen's projection overlaps observation.

Δ area 2015→2020 by functional group [km²]:

| group | NLCD (obs) | SSP1-1.9 | SSP2-4.5 | SSP4-6.0 | SSP5-8.5 | SSPs agreeing in sign |
|---|---:|---:|---:|---:|---:|:---:|
| Bare | −194 | −7,066 | −16,753 | −43,224 | −9,442 | 4/4 |
| Tree | −776 | +39,704 | +3,502 | −63,257 | −9,752 | 2/4 |
| Shrub | +1,396 | +8,005 | +8,323 | −18,728 | −902 | 2/4 |
| Grass | +9,363 | −32,908 | −30,411 | −38,176 | +3,664 | 1/4 |
| Crop | −11,430 | −22,423 | +20,507 | **+150,284** | −181 | 2/4 |
| TOTAL | −1,640 | −14,687 | −14,832 | −13,101 | −16,613 | |

Two things to take from it:

- **Sign agreement is a coin flip** (1/4 to 2/4 except Bare), and the magnitudes
  are off by 1–2 orders: NLCD's observed 5-year change is small and diffuse
  (largest single term +9,363 km² of Grass, in the Dakotas), while SSP4-RCP6.0
  projects +150,284 km² of cropland in the same five years.
- **The spatial character differs completely.** NLCD's observed ΔPCT_NATVEG is
  diffuse — cropland/grass turnover across the Plains plus scattered urban loss.
  Chen's projected ΔPCT_NATVEG is *almost purely urban expansion*: near-zero
  everywhere except a purple dot at every city (fig15 top right). Whatever
  Chen2022 moves over 5 years, it moves at city fringes.

**Caveat — do not over-read this.** The two are not measuring the same thing:
NLCD 2020−2015 is observed change in a 30 m product; Chen 2020−2015 is a 1 km
projection stepping off its own 2015, and the SSPs only begin to diverge from
each other well after 2020. Sign disagreement over five years does not
invalidate Chen's long-term trajectory. What it does establish is narrower and
still useful: **the Chen2022 transient cannot be validated against NLCD at this
lead time**, so "use Chen for the transient signal" (§10, §11) is advice about
its *internal consistency across decades*, not a claim that its near-term change
tracks observation.

```
outputs/interim/elmpft_change_2015_2020.txt
outputs/figures/fig14_elmpft_dominant_group_2015_2020.png
outputs/figures/fig15_elmpft_change_2015_2020.png
```

### 11c. Dominant-PFT visual check (fig16)

`scripts/analysis/34_elmpft_dominant_pft_maps.py` (job `jobs/submit_elmpft_dompft.sbatch`)
— dominant natural PFT, (NLCD | Chen) × (2015 | 2020), for eyeballing.

**A plain `argmax` over natpft would lie here.** Both products carry a 50/50
split of a class they could not resolve, so over large regions two PFTs tie
*exactly* and the winner is decided by numpy's lower-index tie-break, not by
data. The script detects ties and gives them their own categories:

| | tied cells | 99%+ of its ties are | where |
|---|---:|---|---|
| NLCD-derived | **20.0%** | PFT 9 ≡ 10 (Shrub/Scrub 50/50) | Great Basin / Southwest |
| Chen2022 | **11.1%** | PFT 13 ≡ 14 (Mixed C3/C4 50/50, §3) | Great Plains |

Each product's artifact lands in a *different* region. Left un-flagged, a plain
argmax would paint the entire Great Basin as `broadleaf_evergreen_shrub` on the
NLCD side — an artifact of index order, and one that looks perfectly plausible.

Ties are drawn in loud **red** (NLCD 9≡10) and **pink** (Chen 13≡14) — not in a
growth-form hue. A tie is not ecology, it is the product failing to resolve a
class, so it should read as an alarm. Two earlier attempts to keep the ties in
the shrub/grass hue (first a colour midway between the two tied PFTs, then a
darker version of it) both let the artifact blend into the real classes, hiding
the one thing the figure exists to show. Don't "fix" the palette back.

Dominant-PFT composition (% of CONUS natveg cells, 2015):

| | NLCD | Chen |
|---|---:|---:|
| crop | 21.0% | 21.4% |
| c3_non-arctic_grass | 20.8% | 5.6% |
| **TIE shrub 9≡10** | **19.9%** | — |
| needleleaf_evergreen_temperate_tree | 19.8% | 22.7% |
| broadleaf_deciduous_temperate_tree | 17.5% | 16.6% |
| broadleaf_deciduous_temperate_shrub | — | 19.9% |
| **TIE grass 13≡14** | — | **11.1%** |
| Bare_Ground | 1.0% | 0.9% |
| boreal/other (2,3,6,8,9,11,12) | 0.0% | 1.8% |

What the eye should take from fig16: the two products agree closely on crop and
on both tree PFTs (within ~1–3 points), and disagree structurally exactly where
each one's 50/50 split lives — NLCD's shrubland is unresolved, Chen's Plains
grass is unresolved, and the two never overlap.

```
outputs/figures/fig16_dominant_pft_2015_2020.png
```

---

## 12. Harmonization prep — difference inventory

**Status: input to a decision, not a decision.** Nothing here has been
harmonized. This section consolidates every difference established in §10/§11
between the two products that a harmonized CONUS land-use timeseries would have
to join:

| | |
|---|---|
| historical | `elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc` (NLCD-derived) |
| scenario | `outputs/processed/chen2022_landuse_CONUS_{SSP}_2015-2100_1_24deg.nc` |

Each difference is classified by what harmonization must *do* about it:
**aligned** (nothing), **mechanical** (a conversion exists), or **irreducible**
(one product does not carry the information — a convention must be *chosen* or
external data brought in).

### 12.1 Already aligned — no work needed

- **Grid.** Identical: 601 × 1441, 1/24°, centers lat 25…50, lon −125…−65.
  Cell-by-cell, no regridding. (Chen was built with `--like` this file, §4.)
- **PFT axis.** Both are the ELM/CLM5 standard 17-PFT list (`ELM_PFT_NAMES`,
  index = position in `PCT_PFT`). Chen writes it as `pft_name` and script 30
  raises if it ever drifts.
- **`PCT_NAT_PFT` normalization.** Sums to 100 within natveg in both (checked).
- **`PCT_NATVEG` normalization.** % of the whole grid cell in both.
- **Cropland placement.** Both carry cropland as **PFT 15 inside natveg**, and
  `PCT_CROP` is unused on both sides (absent in NLCD, present-but-zero in Chen).
  `irrigated_crop` (PFT 16) is zero in both.

### 12.2 The overlap window — where the splice can go

| | range | steps |
|---|---|---|
| NLCD-derived | 1850–2023 | 174, annual |
| Chen2022 SSP | 2015, 2020, 2025 … 2100 | 18, 5-yearly |

**The overlap is exactly two years: 2015 and 2020.** Chen's next step (2025) is
past NLCD's last year (2023). 2015 is Chen's own historical raster and the
common start of all eight SSPs, which makes it the natural splice point; 2020 is
the only independent check available.

### 12.3 Schema — mechanical

| variable | NLCD-derived | Chen2022 | note |
|---|---|---|---|
| `PCT_NATVEG` | ✓ | ✓ | aligned |
| `PCT_NAT_PFT` | ✓ (17) | ✓ (17) | aligned |
| `PCT_URBAN` | `numurbl`=3 | single column | **incomparable — see 12.4** |
| `PCT_CROP` | absent | present, always 0 | unused both sides |
| `PCT_LAKE` | **absent** | present | NLCD water is an implicit residual |
| `PCT_GLACIER` | absent | present | |
| `PCT_WETLAND` | absent | present, always 0 | **see 12.4** |
| `pft_name` | **absent** | present | NLCD has no `natpft` coord or global attrs either |

**Column budgets do not close the same way.** Chen closes exactly
(`NATVEG+CROP+LAKE+URBAN+GLACIER` = 100.000). NLCD has no water column at all:
`PCT_NATVEG + PCT_URBAN` ≈ 100 over land (median 98.95), 0 over the Great Lakes,
and ~8 in the mostly-water NYC cell — water is simply whatever is left over.
It also **exceeds 100 on 50 cells (max 104.61)**, which is impossible for a
percent-of-cell and should be clipped before use.

### 12.4 Irreducible — a convention must be chosen

1. **Wetland: neither ELM product has it.** Chen2022 has no wetland class at
   all. NLCD *did* (490,198 km², §10) but the NLCD→ELM mapping dissolved it —
   woody wetland into Tree, herbaceous wetland into Grass (§11 cross-check).
   A harmonized product will have **no wetland** unless an external source is
   blended in. This is a pre-existing property of the historical product, not
   something Chen introduces.
2. **Pasture: only NLCD had it** (548,952 km²), and it went into Grass. Chen has
   a single undivided Cropland. So "Grass" already means different things on the
   two sides before any blending.
3. **Urban is not comparable.** NLCD's `PCT_URBAN` never exceeds **33.5%**
   anywhere in CONUS, so it is not a percent-of-cell in Chen's sense (Chen's NYC
   cell is 83.4% urban; NLCD's is 6.9%). Harmonizing urban requires first
   establishing what the NLCD column means. **Until then, harmonize `PCT_NATVEG`
   and `PCT_NAT_PFT` only** — which is exactly the scope of §11.
4. **Boreal/arctic PFTs exist only on the Chen side.** NLCD populates 8 of 17
   PFTs (0, 1, 7, 9, 10, 13, 14, 15); Chen populates 14. Chen's 53,627 km² of
   `needleleaf_evergreen_boreal_tree`, 33,632 km² of `broadleaf_deciduous_boreal
   _tree` etc. have no NLCD counterpart to blend against.

### 12.5 The four 50/50 artifacts — handle before any PFT-level blend

Each product hard-splits a source class it could not resolve. These are fixed
ratios, not climate-driven, and they are **not the same split**:

| # | product | artifact | extent |
|---|---|---|---|
| 1 | NLCD | PFT 9 ≡ PFT 10 elementwise, `max\|diff\| = 0.0` exactly (Shrub/Scrub 50/50) | ties on **20.0%** of natveg cells — the Great Basin/Southwest |
| 2 | Chen | PFT 13/14 from the Mixed C3/C4 50/50 (§3); Chen's *pure* C4 class has **zero** area in CONUS, so its C4 share is only ever **0 or 0.5** | ties on **11.1%** of natveg cells — the Great Plains |
| 3 | NLCD | C4 share of (C3+C4) capped at **0.2000** exactly, median 0.1735, flat with latitude (~17.5% in every band 25–50°N) | all grassland |
| 4 | NLCD | only 8 of 17 PFTs populated | 9 PFTs structurally zero |

**Consequence — the operative rule.** A weighted blend at PFT level would
average an artifact against a real value: e.g. NLCD PFT 9 (923,137 km², a
tie-break) against Chen PFT 9 (26,917 km², real), producing a number that means
nothing. Ditto PFT 13/14, where the two products' conventions pull in opposite
directions (NLCD 82.5/17.5 C3:C4 vs Chen 62.6/37.4).

> **Harmonize at functional-group level** (Bare / Tree / Shrub / Grass / Crop),
> then re-split to 17 PFTs using **one declared convention**. Which product's
> convention wins is an open decision (12.8), but it must be a choice, not an
> average. `fig16` shows the two artifact regions are disjoint, so neither
> product can supply the other's missing split.

### 12.6 The gap to be harmonized (2015, 471,119 cells / 7,773,653 km²)

`PCT_NATVEG`: NLCD 7,382,876 vs Chen 7,547,467 km² → **+2.2%** — close.

`PCT_NAT_PFT` by functional group:

| group | NLCD | Chen | Chen−NLCD |
|---|---:|---:|---:|
| Bare | 86,969 | 81,283 | −5,685 (−6.5%) |
| Tree | 2,400,369 | 2,858,456 | +458,087 (**+19.1%**) |
| Shrub | 1,846,275 | 1,568,994 | −277,281 (**−15.0%**) |
| Grass | 1,761,131 | 1,534,697 | −226,434 (−12.9%) |
| Crop | 1,288,132 | 1,504,037 | +215,905 (**+16.8%**) |

### 12.7 Why a state swap is not an option — the case for deltas

The step discontinuity a naive splice would inject is ~10× the signal it is
supposed to carry:

| metric | product gap | 5-year signal | ratio |
|---|---:|---:|---:|
| dominant group flips (§11b) | 17.1% of cells | 1.2% (NLCD) / 2.1% (Chen) | 8–14× |
| Tree area | 451,412 km² | 776 km² (NLCD 2015→2020) | ~580× |

So **NLCD 2015 → Chen 2020 read as a timeseries is ~90% dataset swap**. The
standard remedy (LUH2-style) is to carry the historical product's *state* and
apply the scenario product's *relative deltas from its own 2015* — which is what
`fig15` computes.

**Declare this when using it:** §11b showed those deltas disagree in sign with
observation over 2015→2020 (1/4–2/4 of SSPs agree per group) and Chen's 5-year
change is almost purely urban expansion while NLCD's is diffuse Plains turnover.
Delta-harmonization therefore inherits a transient that is unvalidated at short
lead. That is not a reason to prefer the state swap — the swap is strictly worse
— but it bounds what the harmonized product can claim.

### 12.8 Open decisions

1. **Splice year** — 2015 (Chen's own baseline, all SSPs' common start) or 2020
   (uses one more year of observation, but then 2015→2020 disagreement is baked
   in)?
2. **Blend altitude** — functional group (recommended, 12.5) or PFT?
3. **Re-split convention** — whose C3/C4 and whose shrub split survives? Note
   *neither* is defensible on physiology (12.5, #2 and #3); a third, climate-based
   rule may be better than either.
4. **Urban** — exclude (harmonize natveg only), or first establish what NLCD's
   `PCT_URBAN` means?
5. **Wetland** — accept 0 (both products already lack it), or blend an external
   source?
6. **Clip** NLCD's 50 cells where `NATVEG+URBAN` > 100.

### 12.9 Evidence index

| claim | where |
|---|---|
| raw land-cover gap, native resolution | §10, `scripts/analysis/20`–`23`, `fig1`–`fig5` |
| ELM-PFT gap, shared grid | §11, `scripts/analysis/30`–`31`, `fig6`–`fig9` |
| 2020 slice, gap vs scenario spread | §11a, `scripts/analysis/32`, `fig10`–`fig13` |
| product gap vs 5-year signal; the deltas | §11b, `scripts/analysis/33`, `fig14`–`fig15` |
| the tie artifacts, mapped | §11c, `scripts/analysis/34`, `fig16` |
| all numbers | `outputs/interim/elmpft_{compare_tables,2020_tables,change_2015_2020}.txt` |

---

## 13. Harmonization method — decided (SEUS pilot)

§12 was an inventory ("input to a decision, not a decision"). This section
records the **method chosen** and resolves §12.8. The formula spec is in
`HARMONIZATION_SEUS_PILOT.md`. Implementation: `scripts/02_harmonize_seus.py`.
ELM forcing is `--build-timeseries` (`FUTURE_LANDUSE_TIMESERIES.md`); the
default/standalone mode is diagnostic only and is not maintained. Pilot region
= SEUS (bbox lon −95..−74, lat 24..37.5); full CONUS is the same method plus
the boreal drop-list of §12.5, which is inert in SEUS.

**Principle.** Historical / near-term state from the NLCD base map; future change
from Chen; joined by **delta harmonization anchored at 2023** (NLCD's last observed year). Only Chen's
*change* from its own 2023 ever enters — never its absolute state. This is the
LUH2 / Chen2020-§2.3 / Chen2022-§1.4 approach; the area-ratio calibration of
Chen2022 §1.4 is algebraically the additive delta (`NLCD_base + ΔChen`).

**§12.8 decisions, resolved:**

1. **Splice year → 2023** (NLCD's last observed year) — observation owns
   everything through 2023 and Chen takes over only from 2024. Anchoring at 2020
   would discard the 2021–2023 observations (§11b, §12.7).
2. **Blend altitude → functional group**, then re-split to 17 PFT (§12.5). The
   PFT1↔PFT7 relabel (Chen calls SEUS forest needleleaf-evergreen, NLCD mixes
   1/7) and the 9/10, 13/14 conventions make raw-PFT blending meaningless.
3. **Re-split convention → NLCD's frozen 2023 within-group proportions.** Chen
   sets group totals only; NLCD keeps PFT identity (1/7 tree mix, 13/14 C3/C4,
   9/10 shrub, and the low-% understory "sprinkle" Chen lacks).
4. **Urban → excluded** (natveg + PFT only). Chen's urban expansion enters
   implicitly as a decline of the vegetated groups (§12.4).
5. **Wetland → accept 0** (neither product has it).
6. **Clip** NLCD cells >100; force boreal (2,3,8,11,12) and PFT 6 to 0 in SEUS.

**Cadence.** Chen is linearly interpolated (on `p(j)`) from its native 5-year
steps to annual before marching, so the harmonized future is produced **annually**
(2024–2100); the full series 1850–2100 is annual (history ≤2023 = NLCD, unchanged).

**Working quantity.** `p(j) = PCT_NATVEG · PCT_NAT_PFT(j)/100` = PFT j as % of
the whole cell — the only per-PFT quantity commensurable across the two products
(shared denominator = the cell; `PCT_NAT_PFT(j)` alone is not, its denominator
being each product's own natveg column). Outputs are recovered as
`PCT_NATVEG = Σ_j p(j)` (clip ≤100) and `PCT_NAT_PFT(j) = 100·p(j)/Σ_j p(j)`, so
sum-to-100 is automatic.

**Core formula** (group totals `P_g` in % of cell, marched annually 2024→2100
per cell; init `P_harm_g[2023] = P_nl_g[2023]`, Chen annual-interpolated):

```
Ph, Cprev, Cnow = P_harm_g[t-1], P_ch_g[t-1], P_ch_g[t];   dC = Cnow - Cprev
Ph == 0     : P_harm_g[t] = max(dC, 0)          # SEED (all groups real in SEUS)
Cprev <= Ph : P_harm_g[t] = Ph + dC             # ADDITIVE       (eq.1 case A)
else        : P_harm_g[t] = Ph * (Cnow/Cprev)   # MULTIPLICATIVE (eq.1 case B)
```

This is Chen2022 eq. (1): effective absolute change `= dC · min(1, Ph/Cprev)`
(min-footprint), continuous at ratio = 1. Marched step-by-step because the branch
depends on the evolving ratio (does not telescope). Additive is written `Ph+dC`,
never `Ph·(1+r)`, so a group emerging from `Cprev=0` never divides by zero.

Re-split: `p_harm(j,t) = P_harm_g[t] · w_nl(j)`, with frozen
`w_nl(j) = p_nl(j,2023)/P_nl_g(2023)`; fallback to Chen's within-group split where
`P_nl_g(2020)=0` (seeded groups, essentially Crop→PFT15).

**Why SEUS first.** Boreal PFTs (2,3,8,11,12) are identically 0 in SEUS, so the
CONUS boreal-artifact drop/seed judgement is empty — every Chen group that grows
is real and seeded additively. The pilot avoids the method's thorniest branch;
full CONUS reinstates the drop-list (§11c, §12.5).

**Peaky Chen vs spread NLCD.** Chen (categorical, aggregated from 1 km) is peaky
— PFT 1 or 7 at ~100% in a cell, the rest hard-zero — while NLCD spreads over
~4.5 PFT/cell. The delta method keeps NLCD's spread as the baseline and only adds
Chen's changes, so NLCD's low-% sprinkle (which Chen holds at a constant 0,
Δ=0) is **frozen and preserved**, not overwritten by Chen's 100%. Group-level
re-split then attributes a group's change across NLCD's real within-group mix
rather than dumping it on whichever single PFT Chen happened to use.

### 13a. New comparison evidence (post-PFT3-fix, SSP1-RCP1.9)

Diagnostics generated for the harmonization decisions above (`scripts/analysis/50–55`):

```
outputs/figures/fig_natveg_diff_nlcd_vs_chen_ssp1.png      PCT_NATVEG level diff: +2.1 pp, one-directional, city/coast
outputs/figures/fig_natpft_dissimilarity_ssp1.png          composition diff: group 21% vs raw-17 37% of the natveg column
outputs/figures/fig_natpft_groupdiff_ssp1_2015.png         per functional group, Chen−NLCD
outputs/figures/fig_natpft_perpft_diff_ssp1_2020.png       per-PFT diff, all 17
outputs/figures/fig_natpft_presence_ssp1_2020.png          per-PFT has/has-not, 4-class (CONUS)
outputs/figures/fig_natpft_presence_SEUS_ssp1_2020.png     per-PFT has/has-not (SEUS)
outputs/figures/fig_nlcdonly_correspondence_ssp1_2020.png  NLCD-only cells: what Chen has instead (PFT 7/9/13)
outputs/interim/natpft_{diff,types,presence,...}_*_ssp1.txt
```

What they establish, in one line each:

- **Composition disagrees far more than natveg** — ~21% of the natveg column by
  functional group (West-heavy), vs `PCT_NATVEG` agreeing to +2.1 pp. So the
  delta-freeze of NLCD's composition matters most here.
- **"NLCD-only" presence is two things**: NLCD's fractional sprinkle (trees 7 /
  grass 13 at median 5–10%) — frozen; or the 9≡10 shrub artifact (NLCD PFT 9 ↔
  Chen PFT 10) — a within-Shrub relabel. Both are static level/convention
  differences the delta method absorbs.
- Both facts confirm **group-level blend + NLCD-frozen re-split** (13, decision
  2–3) rather than any per-PFT blend.
