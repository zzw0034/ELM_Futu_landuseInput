#!/bin/bash
#SBATCH -J rowmajor_ssp245_QBOT_scratch
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 32
#SBATCH --mem=190g
#SBATCH -t 08:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Approach B, parallel per-year staging, 32 workers -- test on /scratch
# (Lustre, this directory's default stripe_count=1, unchanged), paired
# with test_rowmajor_ssp119_QBOT_worldshared.sbatch (same variable,
# world-shared) submitted at the same time for a direct timing
# comparison between the two filesystems under identical code/settings.
SCENARIO=ssp245
VARNAME=QBOT
OUT_ROOT=/scratch/hpcl-cli185/zw5/future_clim

$PY -u scripts/11_build_future_cpl_bypass_rowmajor.py --scenario "$SCENARIO" --var "$VARNAME" \
    --out-dir "$OUT_ROOT/$SCENARIO"

OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
