#!/bin/bash
#SBATCH -J lu_future
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=64g
#SBATCH -t 00:40:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PWD/src"
# SSP4_RCP60 was dropped from the scenario set on 2026-07-29 (no TESSFA
# climate forcing exists to pair with it); SSP3_RCP70 replaced it and has
# its own single-scenario script. Do NOT add SSP3_RCP70 to this loop -- it
# would recompute and overwrite the already-verified products.
for SC in SSP1_RCP19 SSP2_RCP45 SSP5_RCP85; do
  echo "==================== $SC ===================="
  $PY scripts/02_harmonize_seus.py --build-timeseries --scenario "$SC"
done
