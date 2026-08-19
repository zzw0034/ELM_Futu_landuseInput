#!/bin/bash
#SBATCH -J bench_ncgen
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 01:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Can ncgen build the whole 96GiB-variable header in one define session,
# avoiding the single ~37min rewrite that the attribute-ordering fix cannot
# remove (job 465262)? See the script docstring for the full chain of what
# has already been ruled in and out.
$PY -u /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass/benchmarks/scripts/bench_ncgen_header.py
