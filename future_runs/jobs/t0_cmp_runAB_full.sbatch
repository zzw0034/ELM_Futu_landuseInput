#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH --time=00:30:00
#SBATCH -J t0_cmp_full
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/t0_cmp_runAB_full.%j.out
#
# Completes test 2a (restart consistency, 0.5deg historical) by covering what
# the first pass left out:
#   * the 2023 h0/h1 history output, which rh0/rh1 do not stand in for
#   * char/string variables, which the first comparator skipped
#   * global and per-variable attributes, so the differing elm.r checksum is
#     attributed to something specific instead of assumed to be metadata
#
# Run A = continuous 1995->2024 (job 511752); baseline saved outside RUNDIR.
# Run B = restart from A's 2023-01-01 checkpoint, one year (job 511762).
# Run B's 2023 h0 is its first output file of the job and is 500 KB larger
# than A's, so record alignment is expected to matter here.

set -u
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
T=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/tools
D=/scratch/hpcl-cli185/zw5/cime_output_dirs/20260904_dbg_halfdeg_2023end
CASE=20260904_dbg_halfdeg_2023end

echo "### host $(hostname)  $(date -Is)"

echo
echo "=== sha256: 2023 history, run A (baseline) vs run B (run/) ==="
sha256sum $D/baseline_runA_verified/$CASE.elm.h0.2023-02-01-00000.nc \
          $D/baseline_runA_verified/$CASE.elm.h1.2023-02-01-00000.nc \
          $D/run/$CASE.elm.h0.2023-02-01-00000.nc \
          $D/run/$CASE.elm.h1.2023-02-01-00000.nc

for t in h0 h1; do
  echo
  echo "================ elm.$t 2023 : runA vs runB ================"
  $PY $T/cmp_nc2.py $D/baseline_runA_verified/$CASE.elm.$t.2023-02-01-00000.nc \
                    $D/run/$CASE.elm.$t.2023-02-01-00000.nc
done

for f in elm.r cpl.r elm.rh0 elm.rh1; do
  echo
  echo "================ $f 2024-01-01 : runA vs runB  (TEXT + META pass) ================"
  $PY $T/cmp_nc2.py $D/baseline_runA/$CASE.$f.2024-01-01-00000.nc \
                    $D/run/$CASE.$f.2024-01-01-00000.nc
done

echo
echo "### done $(date -Is)"
