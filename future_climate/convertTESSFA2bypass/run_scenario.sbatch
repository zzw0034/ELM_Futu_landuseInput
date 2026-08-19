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

# One scenario, all 7 variables, sequentially on one exclusive node.
# Submit once per scenario to put all four scenarios on four nodes at once.
#
#   sbatch --export=ALL,SCENARIO=ssp119 run_scenario.sbatch
#
# --exclusive matters: two of these packed onto the same node contend for the
# same local I/O and both slow down noticeably.
: "${SCENARIO:?Set SCENARIO, e.g. sbatch --export=ALL,SCENARIO=ssp119 run_scenario.sbatch}"
OUT_ROOT=/scratch/hpcl-cli185/zw5/future_clim
OUTDIR=$OUT_ROOT/$SCENARIO
mkdir -p "$OUTDIR"

VARNAMES=(PRECTmms FSDS TBOT QBOT FLDS PSRF WIND)
for VARNAME in "${VARNAMES[@]}"; do
    echo "=== [$SCENARIO/$VARNAME] starting $(date) ==="
    $PY -u build_cpl_bypass_tessfa2.py --scenario "$SCENARIO" --var "$VARNAME" \
        --out-dir "$OUTDIR"
    echo "=== [$SCENARIO/$VARNAME] done $(date) ==="
done

# The model reads zone_mappings.txt from the same directory as the forcing
# files. This must be cpl_bypass_full/'s copy -- see the note in the python
# script about the two different files with this name.
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
echo "=== [$SCENARIO] ALL 7 VARIABLES DONE $(date) ==="
