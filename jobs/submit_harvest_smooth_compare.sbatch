#!/bin/bash
#SBATCH -J harvest_smooth_cmp
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=64g
#SBATCH -t 00:45:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

# Runs scripts/analysis/12_harvest_smooth_compare.py -- old-vs-new (pre/post
# LUH2 harvest smoothing, 2026-08-28) map + timeseries comparison figures.
# Forwards all args to the python script, so this one job script serves both
# comparisons:
#
#   Default (uses the script's own defaults, no args needed):
#     sbatch jobs/submit_harvest_smooth_compare.sbatch
#
#   RH (after Default is validated, RH rebuilt, and old RH archived):
#     sbatch jobs/submit_harvest_smooth_compare.sbatch \
#       --old-dir /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/archive_pre_smoothHARV_20260828 \
#       --new-dir /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios \
#       --suffix _RH --label RH
#
# --mem=64g / -t 00:45:00: unmeasured estimate for reading 5 HARVEST_* vars x
#   77 years x 324x504 from 2 files (old, new) x 4 SSPs plus building 5
#   matplotlib figures in one process. Smoke-test first with a single SSP
#   (--ssps SSP1_RCP19) before trusting these for the full run.
#
# No `module load` here, deliberately -- same self-contained conda env
# reasoning as the other jobs/*.sbatch in this project.
set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
$PY scripts/analysis/12_harvest_smooth_compare.py "$@"
