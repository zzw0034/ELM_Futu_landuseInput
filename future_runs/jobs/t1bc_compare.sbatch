#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1 -n 1 -c 4
#SBATCH --mem=96g
#SBATCH --time=02:00:00
#SBATCH -J t1bc_cmp
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/t1bc_compare.%j.out
#
# T1b (segmented: 2 days, restart, 1 day) vs T1c (continuous: 3 days).
# Same A3 initial condition, same inputs, same PE layout, and the same
# executable -- md5 799bc60960aad9b10421e70d8bea6faa on both, verified before
# submission, so the build cannot account for any difference found here.
#
# 2024-01-02 and 2024-01-03 are before and at the restart boundary and should
# match. 2024-01-04 is after it and is where the FSDS/PRECTmms phase reset can
# show. The hourly h0 localises when divergence appears rather than only
# whether it does.

set -u
P=/projects/hpcl-cli185/proj-shared/zw5
PY=$P/conda_envs/make_surfdata_pf/bin/python
T=$P/ELM_Futu_landuseInput/future_runs/tools
O=/scratch/hpcl-cli185/zw5/cime_output_dirs
B=$O/20260908_seus_4km_fut_a3ic_ssp370/run/20260908_seus_4km_fut_a3ic_ssp370
C=$O/20260908_seus_4km_fut_a3ic_cont/run/20260908_seus_4km_fut_a3ic_cont

echo "### $(hostname) $(date -Is)"
for d in 2024-01-02 2024-01-03 2024-01-04; do
  echo
  echo "================ elm.r $d : T1b(segmented) vs T1c(continuous) ================"
  $PY $T/cmp_nc2.py $B.elm.r.$d-00000.nc $C.elm.r.$d-00000.nc --quiet-attrs --max-report 25
done

echo
echo "================ elm.h0 hourly, 72 records ================"
$PY $T/cmp_nc2.py $B.elm.h0.2024-01-01-00000.nc $C.elm.h0.2024-01-01-00000.nc \
    --quiet-attrs --max-report 30

echo
echo "================ per-hour drill: forcing first, then response ================"
$PY $T/cmp_nc2.py $B.elm.h0.2024-01-01-00000.nc $C.elm.h0.2024-01-01-00000.nc \
    --quiet-attrs --max-report 0 \
    --drill FSDS --drill RAIN --drill TBOT --drill GPP
echo "### exit $? $(date -Is)"
