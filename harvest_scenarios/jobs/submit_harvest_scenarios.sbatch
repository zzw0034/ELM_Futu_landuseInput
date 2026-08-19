#!/bin/bash
#SBATCH -J harvest_scenarios
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=24g
#SBATCH -t 04:00:00
#SBATCH --array=0-3
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.err

# Builds the 12 management-scenario landuse.timeseries files (RF/DF/RH x 4
# SSPs) -- definitions locked 2026-08-19, see HARVEST_SCENARIOS.md.
#
# --array=0-3: one task per SSP (index into ALL_SSPS in the script). The
#   per-SSP loop body is fully independent -- shared inputs are read-only and
#   output filenames are disjoint -- so this is safe. Note the expected
#   speedup is uncertain: the work is write-I/O-bound (~26GB written in
#   total, uncompressed classic NetCDF) on a shared NFS filesystem, not
#   CPU-bound, so 4 concurrent tasks may contend rather than scale linearly.
#   The reliable benefit is fault isolation: one SSP failing no longer takes
#   the rest down, and only that task needs re-running (resubmit with
#   --array=<i>). To run all 4 sequentially in one job instead, delete this
#   --array line and drop the argument from the python call below.
# -c 1: nothing in the script is threaded/parallel (OPENBLAS/OMP pinned to 1
#   thread below, no multiprocessing, netCDF4/HDF5 single-threaded by
#   default) -- there is no step that could use a second core.
# --mem=24g: DERIVED, per array task (AGENTS.md: derive, do not guess).
#   PCT_NAT_PFT is 77*17*324*504 float64 = 1.71GB; each HARVEST_* is
#   77*324*504 float64 = 100MB. Live at peak, within one SSP iteration:
#     default_pft 1.71 + rf_pft 1.71 (still referenced during the DF block)
#     + df_pft 1.71 + validation read-back of PCT_NAT_PFT 1.71
#     + default/df/rh_harvest 3x5x100MB = 1.50
#     + increment_target/grass_removed/default_forest 0.30
#     + 1850/2023 anchors and 2-D weights 0.05
#     + interpreter/numpy/netCDF4 overhead ~0.30      => ~9GB
#   24g leaves ~2.6x margin. Confirm against `seff` after the first run and
#   tighten if warranted; peak could be cut further by `del rf_pft` once the
#   RF file is written.
# -t 04:00:00: NOT yet measured -- placeholder for the first (smoke) run
#   only. Replace with a value derived from that run's actual elapsed time
#   before submitting the remaining tasks.
#
# Must run under Slurm, not on the login node: PCT_NAT_PFT is a
# 77x17x324x504 float64 array (~1.7GB) per file; an earlier interactive
# login-node run of this pipeline was OOM-killed (exit 137).

# No `module load` here, deliberately -- do not add any.
#   1. ~/.bashrc returns early for non-interactive shells (`case $- in *i*)`),
#      so its module loads never apply to a batch job anyway.
#   2. The conda env below is fully self-contained: verified with `env -i`
#      (completely empty environment, no PATH/LD_LIBRARY_PATH, no modules)
#      that it imports numpy and netCDF4 and runs fine, using its own bundled
#      libnetcdf 4.10.0 / libhdf5 2.1.0.
#   3. Loading ~/.bashrc's modules would actively risk breaking it: they carry
#      hdf5/1.14.5-mpi and netcdf-c/4.9.2-mpi-h5f, different (and for HDF5,
#      major-version-different) from what this python links against, and
#      LD_LIBRARY_PATH injection of a mismatched libhdf5 is a classic failure.
#      Those modules exist to build ELM/PFLOTRAN, not to run this env.
# This matches every other working sbatch in this project (jobs/submit_*.sbatch),
# all of which invoke this same absolute python path with no modules loaded.
set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios/scripts
$PY build_harvest_scenarios.py "${SLURM_ARRAY_TASK_ID}"

echo "--- array task ${SLURM_ARRAY_TASK_ID} done; current output dir ---"
ls -lh /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/
