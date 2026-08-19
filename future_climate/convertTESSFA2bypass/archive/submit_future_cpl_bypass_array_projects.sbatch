#!/bin/bash
#SBATCH -J fut_cplbp_proj
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
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Companion to submit_future_cpl_bypass_array.sbatch: writes to /projects
# instead of /scratch, so this stream and the /scratch array (job 464840)
# run concurrently without competing for the same filesystem's I/O.
# /projects/hpcl-cli185 had ~46TB free as of 2026-08-17 -- this stream's
# 5 files (~96GiB each, ~480GiB total) fit comfortably.
#
# ssp370 only here -- ssp585 goes to the canonical world-shared inputdata
# path instead (submit_future_cpl_bypass_array_ssp585.sbatch), since that's
# where metdata_bypass will actually need to point eventually, avoiding a
# later move. NOTE: world-shared and proj-shared are the SAME physical NFS
# mount (both under /projects/hpcl-cli185), so that split doesn't add any
# I/O parallelism on top of the /scratch-vs-/projects split -- it's purely
# to land ssp585 in its final location, not a speed optimization.
OUT_ROOT=/projects/hpcl-cli185/proj-shared/zw5/future_clim

# 5 combinations, indices 0-4 (part of the original /scratch array's
# indices 15-26, cancelled before they started, split three ways: this
# stream, the ssp585-to-world-shared stream, and the rest staying on
# /scratch under job 464840).
SCENARIOS=(ssp370 ssp370 ssp370 ssp370 ssp370)
VARNAMES=(TBOT QBOT FLDS PSRF WIND)

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
