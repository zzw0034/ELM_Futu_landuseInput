#!/bin/bash
#SBATCH -J harmonize_regen
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=48g
#SBATCH -t 00:50:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
for SC in SSP1_RCP19 SSP2_RCP45 SSP4_RCP60 SSP5_RCP85; do
  echo "==================== harmonize $SC ===================="
  $PY scripts/02_harmonize_seus.py --scenario "$SC"
done
for SC in SSP1_RCP19 SSP2_RCP45 SSP4_RCP60 SSP5_RCP85; do
  echo "==================== diag $SC ===================="
  $PY scripts/analysis/03_harmonize_seus_diag.py --scenario "$SC"
done
echo "==================== compare ===================="
$PY scripts/analysis/06_harmonize_seus_compare.py
