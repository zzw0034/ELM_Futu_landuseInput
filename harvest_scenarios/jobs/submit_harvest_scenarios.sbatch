#!/bin/bash
#SBATCH -J harvest_scenarios
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=64g
#SBATCH -t 03:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

# Builds the 3 management-intervention landuse.timeseries scenarios
# (preserve forest, half harvest off SSP3-7.0, reforest-to-1850). Moved to
# Slurm after an interactive login-node run was OOM-killed (exit 137) --
# PCT_NAT_PFT is a ~1.7GB float64 array, well past what should run on a
# login node per this project's own rules.

set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios/scripts
$PY build_harvest_scenarios.py

ls -lh /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/
