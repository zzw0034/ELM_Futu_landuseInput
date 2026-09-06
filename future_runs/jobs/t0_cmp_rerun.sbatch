#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH --time=00:30:00
#SBATCH -J t0_cmp_rerun
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/t0_cmp_rerun.%j.out
set -u
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
T=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/tools
D=/scratch/hpcl-cli185/zw5/cime_output_dirs/20260904_dbg_halfdeg_2023end
CASE=20260904_dbg_halfdeg_2023end
echo "### $(date -Is)"
for f in elm.r elm.rh0 elm.rh1; do
  echo; echo "================ $f 2024-01-01 : runA vs runB ================"
  $PY $T/cmp_nc2.py $D/baseline_runA/$CASE.$f.2024-01-01-00000.nc $D/run/$CASE.$f.2024-01-01-00000.nc
done
echo; echo "================ SEEDC_GRC drill-down, elm.h0 2023 ================"
$PY $T/cmp_nc2.py $D/baseline_runA_verified/$CASE.elm.h0.2023-02-01-00000.nc \
                  $D/run/$CASE.elm.h0.2023-02-01-00000.nc \
                  --drill SEEDC_GRC --quiet-attrs --max-report 5
echo; echo "### done $(date -Is)"
