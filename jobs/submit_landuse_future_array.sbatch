#!/bin/bash
#SBATCH -J lu_future
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=64g
#SBATCH -t 00:40:00
#SBATCH --array=0-3
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.err

# Job-array replacement for submit_landuse_future.sbatch (looped SSP1/2/5) +
# submit_landuse_future_ssp370.sbatch (SSP3 alone). That split existed only
# because SSP3_RCP70 was added later (2026-07-29) to replace the
# climate-forcing-less SSP4_RCP60, and the loop script explicitly avoided
# adding it so as not to recompute/overwrite the already-verified SSP1/2/5
# outputs (see FUTURE_LANDUSE_TIMESERIES.md sec 9 and that script's own
# comment). That protection no longer applies here: the 2026-08-28 LUH2
# harvest pre-smoothing fix (see the same doc's downscale_harvest section)
# changes every SSP's harvest field, so all four Default landuse.timeseries
# files need rebuilding together, and one job array with disjoint outputs
# and read-only shared inputs is a safe way to do that with per-SSP fault
# isolation. The two single-purpose scripts are left in place for a future
# single/partial rerun; they are not deleted or otherwise made stale by this
# job.
#
# --array=0-3: one task per SSP, index into ALL_SSPS below.
# --mem=64g / -t 00:40:00: unchanged from the two scripts this replaces
# (each already-measured per-scenario run fits inside this budget).
#
# No `module load` here, deliberately -- same self-contained conda env
# reasoning as every other jobs/*.sbatch in this project (see
# harvest_scenarios/jobs/submit_harvest_scenarios.sbatch for the fullest
# writeup of why).
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PWD/src"

ALL_SSPS=(SSP1_RCP19 SSP2_RCP45 SSP3_RCP70 SSP5_RCP85)
SC="${ALL_SSPS[$SLURM_ARRAY_TASK_ID]}"

declare -A LUH_FILE=(
  [SSP1_RCP19]=ssp1rcp19_transitions.nc
  [SSP2_RCP45]=ssp2rcp45_transitions.nc
  [SSP3_RCP70]=ssp3rcp70_transitions.nc
  [SSP5_RCP85]=ssp5rcp85_transitions.nc
)

# Fail early and clearly if either input is missing, rather than deep inside
# the harmonization (matches submit_landuse_future_ssp370.sbatch's check).
CHEN="outputs/interim/chen_targetgrid_${SC}_2015-2100_1_24deg.nc"
LUH="/projects/hpcl-cli185/proj-shared/zw5/luh/${LUH_FILE[$SC]}"
for f in "$CHEN" "$LUH"; do
    [ -s "$f" ] || { echo "FATAL: missing input $f"; exit 1; }
done

echo "==================== task ${SLURM_ARRAY_TASK_ID}: $SC ===================="
$PY scripts/02_harmonize_seus.py --build-timeseries --scenario "$SC"

ls -lh "outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_${SC}_simyr2024-2100.nc"
