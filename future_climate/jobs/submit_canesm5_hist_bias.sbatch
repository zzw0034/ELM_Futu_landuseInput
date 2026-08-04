#!/bin/bash
#SBATCH -J fc_hbias
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=64g
#SBATCH -t 04:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.err
#SBATCH --array=0-1
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
# 0: observed Daymet_ERA5 1980-2014   1: CanESM5 DBCCA historical 1980-2014
if [ "$SLURM_ARRAY_TASK_ID" -eq 0 ]; then
  $PY scripts/04_hist_monthly_means.py --y0 1980 --y1 2014 \
      --out hist_monthly_means_1980-2014.npz
else
  $PY scripts/05_future_monthly_means.py --scenario historical --y0 1980 --y1 2014
fi
