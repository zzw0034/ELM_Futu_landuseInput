#!/bin/bash
# Chen2022 -> ELM land-use NetCDF, on Pathfinder.
#
#     sbatch jobs/submit_landuse.sbatch
#
# Edit the CONFIG block below before submitting.
#
# Paths are absolute: SLURM runs the script from a spool copy, so $0 does not
# point into the project and submission cwd does not matter.
#
#SBATCH -J chen2022_landuse
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32g
#SBATCH -t 02:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

set -euo pipefail

PROJECT_ROOT=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
cd "$PROJECT_ROOT"

# The env's python is used by absolute path: no `module load` / `conda activate`
# needed, and nothing to deactivate before sbatch.
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PROJECT_ROOT/src"

# --- CONFIG ------------------------------------------------------------------
# Keep the *_TAG values consistent with BBOX / RESOLUTION / EXTRA_YEARS: they are
# only used to build the output filenames, nothing validates them.
#
# The domain/grid is taken from the NLCD ELM-PFT product, so the two are on the
# same 1/24 deg grid (601 x 1441; centers lat 25..50, lon -125..-65) and can be
# compared cell by cell. Do NOT replace this with --bbox -125 25 -65 50: --bbox
# takes cell EDGES, so those round numbers give a grid offset by half a cell.
GRID_LIKE=/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc
REGION_TAG="CONUS"
RES_TAG="1_24deg"

# Available: SSP1_RCP19 SSP1_RCP26 SSP2_RCP45 SSP3_RCP70
#            SSP4_RCP34 SSP4_RCP60 SSP5_RCP34 SSP5_RCP85
SCENARIOS=(SSP1_RCP19 SSP2_RCP45 SSP4_RCP60 SSP5_RCP85)

EXTRA_YEARS="2020:2100:5"       # future years merged with the 2015 historical slice
YEARS_TAG="2015-2100"

# Deliverable (CONUS 1/24 deg, full series) -> processed/.
# Point this at outputs/interim for exploratory / coarser / partial-year runs.
OUTDIR="outputs/processed"
# -----------------------------------------------------------------------------

mkdir -p "$OUTDIR" outputs/figures outputs/logs

# --- Run 1: historical 2015 only ---------------------------------------------
OUT_HIST="$OUTDIR/chen2022_landuse_${REGION_TAG}_2015_${RES_TAG}.nc"
$PY scripts/01_chen2022_to_elm_landuse.py \
    --scenario historical \
    --years 2015 \
    --like "$GRID_LIKE" \
    --out "$OUT_HIST"

$PY scripts/analysis/plot_elm_landuse_maps.py \
    --in "$OUT_HIST" \
    --out "outputs/figures/$(basename "${OUT_HIST%.nc}").png"

# --- Run 2: one transient file per scenario, 2015 + EXTRA_YEARS --------------
for SCENARIO in "${SCENARIOS[@]}"; do
    OUT_SSP="$OUTDIR/chen2022_landuse_${REGION_TAG}_${SCENARIO}_${YEARS_TAG}_${RES_TAG}.nc"
    echo "=== $SCENARIO -> $OUT_SSP"
    $PY scripts/01_chen2022_to_elm_landuse.py \
        --scenario "$SCENARIO" \
        --years 2015 \
        --extra-years "$EXTRA_YEARS" \
        --like "$GRID_LIKE" \
        --out "$OUT_SSP"

    $PY scripts/analysis/plot_elm_landuse_maps.py \
        --in "$OUT_SSP" \
        --out "outputs/figures/$(basename "${OUT_SSP%.nc}").png"

    $PY scripts/analysis/plot_area_timeseries.py \
        --in "$OUT_SSP" \
        --out "outputs/figures/area_timeseries_${REGION_TAG}_${SCENARIO}_${YEARS_TAG}_${RES_TAG}.png"
done

echo "done: $OUT_HIST + ${#SCENARIOS[@]} scenarios (${SCENARIOS[*]})"
