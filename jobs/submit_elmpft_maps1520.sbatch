#!/bin/bash
#SBATCH -J elmpft_m1520
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=32g
#SBATCH -t 01:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/elmpft_m1520_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/elmpft_m1520_%j.err

set -euo pipefail
PROJECT_ROOT=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="${PROJECT_ROOT}/src"
cd "${PROJECT_ROOT}"
$PY scripts/33_elmpft_maps_2015_2020.py
echo "done"
