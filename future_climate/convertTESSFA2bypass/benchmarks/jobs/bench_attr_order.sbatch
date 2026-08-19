#!/bin/bash
#SBATCH -J bench_attr_order
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH -t 01:30:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Times the one header rewrite the proposed fix cannot avoid: the big
# variable's add_offset/scale_factor, which can only be set once the
# variable exists. Everything else moves ahead of the big variable's
# declaration. See the script docstring for what's already been ruled in
# and out. Walltime is deliberately short -- if a variant needs more than
# ~45 min for a single attribute step, that is itself the answer.
$PY -u /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/convertTESSFA2bypass/benchmarks/scripts/bench_attr_order.py
