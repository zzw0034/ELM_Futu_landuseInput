#!/bin/bash
#SBATCH -J fut_scenario
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 32
#SBATCH --mem=190g
#SBATCH --exclusive
#SBATCH -t 12:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# One scenario, all 7 variables, sequential within this node -- run 4 of
# these (one per scenario) to get 4 scenarios on 4 separate nodes at once.
# --exclusive reserves the whole node so Slurm can't pack more than one of
# these jobs onto the same node.
#
# Uses Approach B (11_build_future_cpl_bypass_rowmajor.py) with the ncgen
# header fix (2026-08-18): the header-rewrite bug that made file creation
# take hours is gone, so 7 variables sequentially at ~5min each is ~35min
# per scenario instead of the ~3-4h/variable this pipeline needed before.
#
# usage: sbatch --export=ALL,SCENARIO=ssp119 jobs/run_scenario_all_vars.sbatch
: "${SCENARIO:?Set SCENARIO, e.g. sbatch --export=ALL,SCENARIO=ssp119 jobs/run_scenario_all_vars.sbatch}"
OUT_ROOT=/scratch/hpcl-cli185/zw5/future_clim
OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"

VARNAMES=(PRECTmms FSDS TBOT QBOT FLDS PSRF WIND)
for VARNAME in "${VARNAMES[@]}"; do
    echo "=== [$SCENARIO/$VARNAME] starting $(date) ==="
    $PY -u scripts/11_build_future_cpl_bypass_rowmajor.py --scenario "$SCENARIO" --var "$VARNAME" \
        --out-dir "$OUTDIR"
    echo "=== [$SCENARIO/$VARNAME] done $(date) ==="
done

cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
echo "=== [$SCENARIO] ALL 7 VARIABLES DONE $(date) ==="
