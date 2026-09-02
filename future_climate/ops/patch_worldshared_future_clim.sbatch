#!/bin/bash
#SBATCH -J patch_ws_future
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=96g
#SBATCH -t 12:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/ops
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Dummy-year-tail patch for the 4 km CANONICAL forcing -- the copy
# metdata_bypass actually resolves to for a 4 km future case.
#
# This is production data. Before submitting, confirm no running job reads
# this directory (squeue -u $USER, plus metdata_bypass in any running case's
# user_nl_elm / run/lnd_in). The patch itself is idempotent and reversible
# (the pre-patch state of record 2919 was a known per-variable constant --
# the ocean sentinel -- so it can be restored exactly), but a file being
# read mid-write is still a real hazard.
#
# Submit one job per scenario, SERIALIZED. 4-way concurrency against this
# filesystem was measured to inflate the same operation from 626s to 3416s:
#
#   for S in ssp119 ssp245 ssp370 ssp585; do
#     sbatch --dependency=singleton \
#       --export=ALL,SCENARIO=$S,RECORD_DIR=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/patch_records \
#       patch_worldshared_future_clim.sbatch
#   done
#
# Uses the shared, already-validated ops/patch_dummy_year_tail.py -- the same
# script that patched the /scratch copy. Nothing about the logic is
# location-specific; only BASE_DIR and the filename pattern differ from the
# 0.5 deg wrapper.
BASE_DIR="/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim"

: "${SCENARIO:?Set SCENARIO, e.g. sbatch --export=ALL,SCENARIO=ssp119,RECORD_DIR=... patch_worldshared_future_clim.sbatch}"
: "${RECORD_DIR:?Set RECORD_DIR for the patch-record JSON audit trail}"
# --sha256 doubles a full 96GiB read per file (~200s each). Kept on by
# default: this is canonical data and the before/after hashes are the
# audit trail. Override with EXTRA_ARGS="" to skip.
EXTRA_ARGS="${EXTRA_ARGS:---sha256}"

DIR="$BASE_DIR/$SCENARIO"
[[ -d "$DIR" ]] || { echo "ERROR: $DIR is not a directory" >&2; exit 1; }

VARNAMES=(TBOT PSRF QBOT FSDS PRECTmms WIND FLDS)
for VARNAME in "${VARNAMES[@]}"; do
    FILE="$DIR/DBCCA_Daymet_TESSFA2_${VARNAME}_2023-2100_z01.nc"
    echo "=== [worldshared/$SCENARIO/$VARNAME] $(date) patching $FILE ==="
    $PY -u patch_dummy_year_tail.py --file "$FILE" --var "$VARNAME" \
        --record-dir "$RECORD_DIR" $EXTRA_ARGS
    echo "=== [worldshared/$SCENARIO/$VARNAME] $(date) done ==="
done
echo "=== [worldshared/$SCENARIO] ALL 7 VARIABLES DONE $(date) ==="
