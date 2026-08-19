#!/bin/bash
#SBATCH -J compareA_ssp370_QBOT
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

# Approach A half of the first FAIR A-vs-B comparison. Every previous
# timing was dominated by the header-rewrite bug (fixed by building the
# header with ncgen), which masked the actual difference between the two
# write strategies.
#
# Paired with test_rowmajor_ssp245_QBOT_scratch.sbatch (Approach B, job
# 465277): same variable, same filesystem (/scratch), same resources
# (32 CPU / 190g), submitted together so both see the same contention.
# Only the scenario differs, and scenarios are identical in grid, time
# span and file size, so that does not affect timing.
SCENARIO=ssp370
VARNAME=QBOT
OUT_ROOT=/scratch/hpcl-cli185/zw5/future_clim

$PY -u scripts/10_build_future_cpl_bypass.py --scenario "$SCENARIO" --var "$VARNAME" \
    --out-dir "$OUT_ROOT/$SCENARIO"

OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
