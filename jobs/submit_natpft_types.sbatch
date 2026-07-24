#!/bin/bash
#SBATCH -J natpft_types
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32g
#SBATCH -t 00:20:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

set -euo pipefail
PROJECT_ROOT=/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
cd "$PROJECT_ROOT"
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
$PY scripts/52_natpft_types_2020.py
