#!/bin/bash
#SBATCH -J harvest_scenarios
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=64g
#SBATCH -t 04:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

# Builds the 12 management-scenario landuse.timeseries files (RF/DF/RH x 4
# SSPs) -- definitions locked 2026-08-19, see HARVEST_SCENARIOS.md.
#
# -c 1: nothing in the script is threaded/parallel (OPENBLAS/OMP pinned to 1
#   thread below, no multiprocessing, netCDF4/HDF5 single-threaded by
#   default) -- there is no step that could use a second core.
# --mem=64g: peak actual usage is a handful of GB (largest single array is
#   PCT_NAT_PFT at ~1.7GB, processed one SSP at a time so it doesn't
#   accumulate across the loop) -- 64g is a deliberate safety margin, not a
#   measured requirement, kept from the original single-SSP version.
# -t 04:00:00: original single-SSP (3-scenario) build was estimated at
#   minutes, given 3h margin. This version does the same work x4 (4 SSPs,
#   sequential, not parallel) -- bumped to 4h to keep a comparable margin,
#   not because 3h was shown to be insufficient.
#
# Must run under Slurm, not on the login node: PCT_NAT_PFT is a
# 77x17x324x504 float64 array (~1.7GB) per file; an earlier interactive
# login-node run of this pipeline was OOM-killed (exit 137).

set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios/scripts
$PY build_harvest_scenarios.py

ls -lh /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/
