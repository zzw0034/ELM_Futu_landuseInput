#!/bin/bash
#SBATCH -J fut_cplbp_585
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=96g
#SBATCH -t 10:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# ssp585 only, written directly to the canonical world-shared inputdata
# location (same path convention as the historical cpl_bypass_full/ files)
# rather than a scratch/proj-shared staging area, since this is where
# metdata_bypass will actually need to point -- saves a later move. Runs
# concurrently with submit_future_cpl_bypass_array.sbatch (/scratch) and
# submit_future_cpl_bypass_array_projects.sbatch (ssp370, proj-shared);
# note world-shared and proj-shared share the same physical NFS mount as
# /projects/hpcl-cli185, so this split is about final location, not adding
# I/O parallelism beyond the /scratch-vs-/projects split.
OUT_ROOT=/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim

# 7 combinations, indices 0-6 -- all of ssp585 (part of the original
# /scratch array's indices 15-26, cancelled before they started).
SCENARIOS=(ssp585 ssp585 ssp585 ssp585 ssp585 ssp585 ssp585)
VARNAMES=(PRECTmms FSDS TBOT QBOT FLDS PSRF WIND)

SCENARIO=${SCENARIOS[$SLURM_ARRAY_TASK_ID]}
VARNAME=${VARNAMES[$SLURM_ARRAY_TASK_ID]}
echo "array task $SLURM_ARRAY_TASK_ID -> SCENARIO=$SCENARIO VARNAME=$VARNAME -> $OUT_ROOT"

$PY scripts/10_build_future_cpl_bypass.py --scenario "$SCENARIO" --var "$VARNAME" \
    --out-dir "$OUT_ROOT/$SCENARIO"

OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"
# See submit_future_cpl_bypass.sbatch for why this must be cpl_bypass_full/'s
# copy, not the parent Daymet_ERA5_TESSFA2/ dir's (different file, same name).
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
