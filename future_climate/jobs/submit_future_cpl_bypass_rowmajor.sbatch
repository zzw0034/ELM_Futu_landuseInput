#!/bin/bash
#SBATCH -J fut_cplbp_rowmajor
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=96g
#SBATCH -t 08:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Approach B (row-major merge) production-scale test: ssp119/PRECTmms on
# /scratch -- same combo that stalled under Approach A as job 465060
# (cancelled 2026-08-18 after 2h17m stuck before even finishing the dummy
# year). Validated on a 3-year real-data sample (job 465163): byte-identical
# output to Approach A, ~31x faster on pure data movement. This is the
# first full 78-year run of this method.
SCENARIO=ssp119
VARNAME=PRECTmms
OUT_ROOT=/scratch/hpcl-cli185/zw5/future_clim

$PY -u scripts/11_build_future_cpl_bypass_rowmajor.py --scenario "$SCENARIO" --var "$VARNAME" \
    --out-dir "$OUT_ROOT/$SCENARIO"

OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
