#!/bin/bash
#SBATCH -J patch_hd_future
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=96g
#SBATCH -t 4:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/ops
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Dummy-year-tail patch for the 0.5 deg PRODUCTION forcing -- what the
# SEUS_halfdeg future cases (20260901_seus_halfdeg_future_*) actually read.
#
# These files are ~518MB each, ~200x smaller than the 4 km ones, so the whole
# scenario finishes in minutes and --sha256 costs almost nothing here.
#
# This is production data. Before submitting, confirm no running case reads
# this directory:
#   squeue -u $USER
#   grep -l cpl_bypass_0p5deg_future /projects/hpcl-cli185/proj-shared/zw5/e3sm_cases/*/user_nl_elm
# and check whether any of those cases has a job in the queue.
#
#   for S in ssp119 ssp245 ssp370 ssp585; do
#     sbatch --dependency=singleton \
#       --export=ALL,SCENARIO=$S,RECORD_DIR=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/patch_records \
#       patch_halfdeg_future_clim.sbatch
#   done
#
# Uses the shared, already-validated ops/patch_dummy_year_tail.py. The only
# differences from the 4 km wrapper are BASE_DIR and the filename pattern
# (note the ".0p5deg" infix); the patch logic is identical and
# resolution-agnostic -- both layouts are (n, DTIME) with DUMMY_YEAR_LEN=2920.
BASE_DIR="/projects/hpcl-cli185/proj-shared/zw5/SEUS_halfdeg/data/processed/cpl_bypass_0p5deg_future"

: "${SCENARIO:?Set SCENARIO, e.g. sbatch --export=ALL,SCENARIO=ssp119,RECORD_DIR=... patch_halfdeg_future_clim.sbatch}"
: "${RECORD_DIR:?Set RECORD_DIR for the patch-record JSON audit trail}"
EXTRA_ARGS="${EXTRA_ARGS:---sha256}"

DIR="$BASE_DIR/$SCENARIO"
[[ -d "$DIR" ]] || { echo "ERROR: $DIR is not a directory" >&2; exit 1; }

VARNAMES=(TBOT PSRF QBOT FSDS PRECTmms WIND FLDS)
for VARNAME in "${VARNAMES[@]}"; do
    FILE="$DIR/DBCCA_Daymet_TESSFA2.0p5deg_${VARNAME}_2023-2100_z01.nc"
    echo "=== [halfdeg/$SCENARIO/$VARNAME] $(date) patching $FILE ==="
    $PY -u patch_dummy_year_tail.py --file "$FILE" --var "$VARNAME" \
        --record-dir "$RECORD_DIR" $EXTRA_ARGS
    echo "=== [halfdeg/$SCENARIO/$VARNAME] $(date) done ==="
done
echo "=== [halfdeg/$SCENARIO] ALL 7 VARIABLES DONE $(date) ==="
