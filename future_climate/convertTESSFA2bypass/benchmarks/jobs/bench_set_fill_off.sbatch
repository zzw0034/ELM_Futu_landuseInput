#!/bin/bash
#SBATCH -J bench_fill
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 03:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Tests whether Dataset.set_fill_off() (the dataset-level netCDF-3 fill
# switch) is what actually disables pre-fill for classic files, vs the
# per-variable fill_value=False both builders currently rely on. See the
# script docstring for why this is suspected. The set_fill_off() variant
# runs FIRST so its number is available even if the default variant runs
# long and hits walltime.
$PY -u /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass/benchmarks/scripts/bench_set_fill_off.py
