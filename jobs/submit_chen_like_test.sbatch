#!/bin/bash
#SBATCH -J chen_like
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=24g
#SBATCH -t 00:10:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PWD/src"
TGT=/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc
$PY scripts/01_chen2022_to_elm_landuse.py --scenario historical --years 2015 \
    --like "$TGT" --out outputs/interim/chen_like_test_2015.nc
