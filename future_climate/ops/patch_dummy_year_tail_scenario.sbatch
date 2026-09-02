#!/bin/bash
#SBATCH -J patch_dummy_tail_scn
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 8:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/ops
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# All 7 variables, one scenario, sequentially -- so 4 scenarios can each run
# as their own job in parallel. Idempotent (see patch_dummy_year_tail.py's
# docstring): safe to include a variable that's already been patched, it
# just reports 0 cells changed on re-verification.
#
#   sbatch --export=ALL,BASE_DIR=/scratch/hpcl-cli185/zw5/future_clim,SCENARIO=ssp119,\
#RECORD_DIR=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/patch_records \
#       patch_dummy_year_tail_scenario.sbatch
: "${BASE_DIR:?Set BASE_DIR, e.g. /scratch/hpcl-cli185/zw5/future_clim}"
: "${SCENARIO:?Set SCENARIO, e.g. ssp119}"
: "${RECORD_DIR:?Set RECORD_DIR for the patch-record JSON audit trail}"
EXTRA_ARGS="${EXTRA_ARGS---sha256}"

DIR="$BASE_DIR/$SCENARIO"
VARNAMES=(TBOT PSRF QBOT FSDS PRECTmms WIND FLDS)
for VARNAME in "${VARNAMES[@]}"; do
    FILE="$DIR/DBCCA_Daymet_TESSFA2_${VARNAME}_2023-2100_z01.nc"
    echo "=== [$SCENARIO/$VARNAME] $(date) patching $FILE ==="
    $PY -u patch_dummy_year_tail.py --file "$FILE" --var "$VARNAME" \
        --record-dir "$RECORD_DIR" $EXTRA_ARGS
    echo "=== [$SCENARIO/$VARNAME] $(date) done ==="
done
echo "=== [$SCENARIO] ALL 7 VARIABLES DONE $(date) ==="
