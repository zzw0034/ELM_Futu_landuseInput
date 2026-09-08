#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=96g
#SBATCH --time=02:00:00
#SBATCH -J a3_check
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/a3_check_restart.%j.out
#
# Scientific acceptance of the A3 2024-01-01 restart, the initial condition all
# seven 4km future scenarios will start from.
#
# --mem=96g: the two restarts are 14.85 GB each and are read variable by
# variable, so the working set is bounded by the largest variable
# (H2OSOI_LIQ, column x levtot = 1226904 x 20 x 8 B ~ 196 MB) times two files
# plus f8 copies, not by file size. 96g is generous headroom, not a measurement.
#
# -p serial -q normal: single-process analysis, and it must not compete with
# anything on parallel.

set -u
P=/projects/hpcl-cli185/proj-shared/zw5
PY=$P/conda_envs/make_surfdata_pf/bin/python
T=$P/ELM_Futu_landuseInput/future_runs/tools
C=/scratch/hpcl-cli185/zw5/cime_output_dirs/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC
CASE=20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC

NEW=$C/run/$CASE.elm.r.2024-01-01-00000.nc
OLD=$C/pre_A3_baseline/run/$CASE.elm.r.2024-01-01-00000.nc

echo "### $(hostname)  $(date -Is)"
echo
echo "=== identity ==="
ls -l --time-style=full-iso $NEW $OLD
echo
echo "=== sha256 (both, for the record) ==="
sha256sum $NEW $OLD
echo

$PY $T/check_a3_restart.py --new $NEW --old $OLD \
    --json $P/ELM_Futu_landuseInput/future_runs/jobs/a3_check_restart.json \
    --top 40
RC=$?
echo
echo "### check_a3_restart exit code: $RC"
echo "### done $(date -Is)"
