#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1 -n 1 -c 4
#SBATCH --mem=96g
#SBATCH --time=03:00:00
#SBATCH -J t3_cmp
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/t3_compare.%j.out
#
# T3: A = T4 run continuously 2024-01-01 -> 2026-01-01.
#     B = restarted from A's 2025-01-01 checkpoint, run to 2026-01-01.
# Same executable (md5 e8b487b04a27adfd8f683359dfd73df5), same inputs, same
# 20-node layout, production history, netcdf.
#
# Only metadata differences are allowed through: the case name, the history
# paths recorded inside the restart, and creation timestamps. Every numeric
# difference has to be located and explained; "small" is not a verdict.

set -u
P=/projects/hpcl-cli185/proj-shared/zw5
PY=$P/conda_envs/make_surfdata_pf/bin/python
T=$P/ELM_Futu_landuseInput/future_runs/tools
O=/scratch/hpcl-cli185/zw5/cime_output_dirs
A=$O/20260908_seus_4km_fut_t4_n20/run/20260908_seus_4km_fut_t4_n20
B=$O/20260908_seus_4km_fut_t3_restart/run/20260908_seus_4km_fut_t3_restart
AN=20260908_seus_4km_fut_t4_n20
BN=20260908_seus_4km_fut_t3_restart

echo "### $(hostname) $(date -Is)"

echo
echo "############ 1. restart set at 2026-01-01 ############"
for f in elm.r cpl.r elm.rh0 elm.rh1; do
  if [[ -f $A.$f.2026-01-01-00000.nc && -f $B.$f.2026-01-01-00000.nc ]]; then
    echo
    echo "================ $f 2026-01-01 ================"
    $PY $T/cmp_nc2.py $A.$f.2026-01-01-00000.nc $B.$f.2026-01-01-00000.nc --max-report 30
  else
    echo "  $f 2026-01-01: missing on one side (A:$([[ -f $A.$f.2026-01-01-00000.nc ]] && echo y || echo n) B:$([[ -f $B.$f.2026-01-01-00000.nc ]] && echo y || echo n))"
  fi
done

echo
echo "############ 2. 2025 history, aligned on the time coordinate ############"
# January 2025 is the 12th record of the 2024-02-01 file; Feb-Dec 2025 are in
# the 2025-02-01 file. Both files exist on both sides, and cmp_nc2 aligns on
# mcdate/mcsec, so a differing record count cannot hide the comparison.
# The 2024-02-01 tapes were staged into B under A's case name, because elm.r's
# locfnh names them and ELM reopens them to append January 2025. So in B's run
# directory they are still called <A>.elm.h0.2024-02-01, not <B>.*. Comparing
# by B's name would silently find nothing and report "not present".
BDIR=$(dirname $B)
for tape in h0 h1; do
  echo
  echo "================ elm.$tape 2024-02-01  (holds Feb 2024 - Jan 2025; B appended Jan 2025) ================"
  $PY $T/cmp_nc2.py $A.elm.$tape.2024-02-01-00000.nc \
                    $BDIR/$AN.elm.$tape.2024-02-01-00000.nc --max-report 30
  echo
  echo "================ elm.$tape 2025-02-01  (Feb 2025 - Jan 2026) ================"
  $PY $T/cmp_nc2.py $A.elm.$tape.2025-02-01-00000.nc \
                    $B.elm.$tape.2025-02-01-00000.nc --max-report 30
done

echo
echo "############ 3. named fields: forcing, CO2, Ndep, HDM, land use, SEEDC_GRC ############"
$PY $T/cmp_nc2.py $A.elm.h0.2025-02-01-00000.nc $B.elm.h0.2025-02-01-00000.nc \
  --quiet-attrs --max-report 0 \
  --drill TBOT --drill PBOT --drill QBOT --drill FSDS --drill FLDS --drill WIND \
  --drill RAIN --drill SNOW --drill PCO2 --drill NDEP_TO_SMINN --drill HDM \
  --drill TLAI --drill TOTVEGC --drill SEEDC_GRC

echo
echo "### exit $? $(date -Is)"
