#!/bin/bash
#SBATCH -J cmp_pft
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=32g
#SBATCH -t 00:30:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/jobs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/jobs/logs/%x_%j.err

set -euo pipefail
unset SLURM_EXPORT_ENV

PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
$PY /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/scripts/compare/compare_pct_nat_pft_seus_2020.py
