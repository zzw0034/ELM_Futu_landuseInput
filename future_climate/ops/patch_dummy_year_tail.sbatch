#!/bin/bash
#SBATCH -J patch_dummy_tail
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 1:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/ops
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Patch (or --dry-run report) one variable's dummy-year-tail record in one
# already-built future forcing file. See patch_dummy_year_tail.py for the
# full design; this is just the Slurm wrapper (single-column strided reads/
# writes on a potentially 96GB file should not run on a login node).
#
#   sbatch --export=ALL,FILE=/path/to/file.nc,VARNAME=TBOT,EXTRA_ARGS="--dry-run" \
#       patch_dummy_year_tail.sbatch
#
# EXTRA_ARGS is optional (e.g. "--dry-run", or "--sha256 --record-dir /path").
: "${FILE:?Set FILE, e.g. sbatch --export=ALL,FILE=...,VARNAME=TBOT patch_dummy_year_tail.sbatch}"
: "${VARNAME:?Set VARNAME}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

echo "=== [$VARNAME] $(date) patching $FILE ==="
$PY -u patch_dummy_year_tail.py --file "$FILE" --var "$VARNAME" $EXTRA_ARGS
echo "=== [$VARNAME] $(date) done ==="
