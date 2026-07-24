#!/bin/bash
#SBATCH -J inspect_tgt
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 00:12:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err
set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
$PY /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/scripts/analysis/inspect_target.py
