#!/bin/bash
#SBATCH -J harvest_rh_only
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=48g
#SBATCH -t 00:20:00
#SBATCH --array=0-3
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%A_%a.err

# Rebuild ONLY the 4 RH (reduced-harvest) files after the Default landuse.timeseries
# files were regenerated with LUH2 harvest pre-smoothing (2026-08-28). RF and DF
# zero out HARVEST_* by construction (see HARVEST_SCENARIOS.md sec 1), so neither
# depends on whether Default's harvest field was smoothed -- rebuilding them here
# would just re-copy the same ~2.2GB per file for byte-identical output. RH is the
# only one of the three that reads Default's HARVEST_* values (RH = Default x 0.5),
# so it is the only one that needs to change. See build_harvest_scenarios.py's
# --only-rh flag (added 2026-08-28) for the guarded code path this job calls.
#
# PRECONDITION: this must run AFTER the smoothHARV Default files are validated in
# outputs/processed/ (the old ones already moved aside to archive_pre_smoothHARV_20260828/,
# per FUTURE_LANDUSE_TIMESERIES.md / this session's plan) and AFTER the existing 4 RH
# files (and RF/DF, untouched) have been archived to
# outputs/processed/harvest_scenarios/archive_pre_smoothHARV_20260828/ -- this job
# does not do that archiving itself, and build_harvest_scenarios.py's clone_structure
# will silently overwrite outputs/processed/harvest_scenarios/<...>_RH_simyr2024-2100.nc
# in place if it is still holding the pre-smoothing values.
#
# --array=0-3: one task per SSP (index into ALL_SSPS in the script), same
#   independence argument as submit_harvest_scenarios.sbatch.
# --mem=48g: projected, NOT measured -- the --only-rh path skips reading the
#   ~1.7GB PCT_NAT_PFT array (only used by the now-skipped DF section) and skips
#   the DF write, so peak RSS should be well under the 96g / 17.6GB measured for
#   the full RF+DF+RH build. Treat this as a starting point and re-derive if a
#   smoke test on --array=0 gets OOM-killed.
# -t 00:20:00: projected from the full-build measurement (00:02:20 for one SSP's
#   3 files); RH alone is one file per SSP, so this should be a strict subset of
#   that time. Re-derive from a smoke test if this is wrong.
#
# No `module load` here, deliberately -- same self-contained conda env reasoning
# as submit_harvest_scenarios.sbatch.
set -euo pipefail
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/harvest_scenarios/scripts
$PY build_harvest_scenarios.py --only-rh "${SLURM_ARRAY_TASK_ID}"

echo "--- array task ${SLURM_ARRAY_TASK_ID} done; current output dir ---"
ls -lh /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/
