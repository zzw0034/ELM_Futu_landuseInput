#!/bin/bash
#SBATCH -J lc_native_stats
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=32g
#SBATCH -t 01:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/lc_native_stats_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/lc_native_stats_%j.err

# Native-resolution land-cover counts: NLCD 30 m vs Chen2022 1 km.
# SLURM runs this from a spool copy, so PROJECT_ROOT must be absolute (see
# REFERENCE.md 7).

set -euo pipefail

PROJECT_ROOT=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

export PYTHONPATH="${PROJECT_ROOT}/src"
cd "${PROJECT_ROOT}"

$PY scripts/analysis/20_landcover_native_stats.py \
  --workers 12 \
  --out outputs/interim/landcover_native_counts.json

echo "done"
