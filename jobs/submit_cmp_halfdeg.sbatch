#!/bin/bash
# Compare our SEUS 1/24 deg landuse.timeseries (aggregated to 0.5 deg)
# against landuse.timeseries_0.5x0.5_rcp8.5_simyr2015-2100_c191004.nc
# cropped to SEUS. Pairing: our SSP5-RCP8.5 vs E3SM RCP8.5.
#
#     sbatch jobs/submit_cmp_halfdeg.sbatch
#
#SBATCH -J cmp_halfdeg
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 00:40:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PWD/src"
$PY scripts/analysis/11_compare_halfdeg_rcp85.py
