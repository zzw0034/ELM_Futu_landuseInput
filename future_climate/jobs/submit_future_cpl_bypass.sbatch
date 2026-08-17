#!/bin/bash
#SBATCH -J fut_cplbp
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=48g
#SBATCH -t 08:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# usage: sbatch --export=ALL,SCENARIO=ssp245,VARNAME=TBOT jobs/submit_future_cpl_bypass.sbatch
: "${SCENARIO:?set SCENARIO=ssp119|ssp245|ssp370|ssp585}"
: "${VARNAME:?set VARNAME=PRECTmms|FSDS|TBOT|QBOT|FLDS|PSRF|WIND}"

$PY scripts/10_build_future_cpl_bypass.py --scenario "$SCENARIO" --var "$VARNAME"

OUTDIR=/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/$SCENARIO
mkdir -p "$OUTDIR"
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
