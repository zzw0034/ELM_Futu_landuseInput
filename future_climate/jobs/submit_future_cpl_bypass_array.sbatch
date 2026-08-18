#!/bin/bash
#SBATCH -J fut_cplbp
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem=96g
#SBATCH -t 08:00:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%A_%a.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# Array job: index -> (SCENARIO, VARNAME). Submitting all 27 remaining
# combinations as separate concurrent sbatch jobs (2026-08-17) caused severe
# I/O contention on /scratch -- 27-way concurrent write throughput was
# measured at roughly 15-20x slower per job than running alone (an isolated
# job did 77 years in 4.5h; the 27 concurrent jobs averaged only ~14 years
# each in 8h before hitting the walltime and being killed, all left as
# unfinished .partial files -- see README_cpl_bypass_future.md Sec.6.1).
# %N on the --array line (set at submission time, not here) throttles how
# many array tasks Slurm runs at once, so this doesn't recur.
SCENARIOS=(ssp119 ssp119 ssp119 ssp119 ssp119 ssp119 ssp119 \
           ssp245 ssp245 ssp245 ssp245 ssp245 ssp245 \
           ssp370 ssp370 ssp370 ssp370 ssp370 ssp370 ssp370 \
           ssp585 ssp585 ssp585 ssp585 ssp585 ssp585 ssp585)
VARNAMES=(PRECTmms FSDS TBOT QBOT FLDS PSRF WIND \
          PRECTmms FSDS QBOT FLDS PSRF WIND \
          PRECTmms FSDS TBOT QBOT FLDS PSRF WIND \
          PRECTmms FSDS TBOT QBOT FLDS PSRF WIND)
# ssp245/TBOT (index that would've been here) is already done -- omitted,
# so ssp245 has 6 entries instead of 7 and everything after it shifts by one.

SCENARIO=${SCENARIOS[$SLURM_ARRAY_TASK_ID]}
VARNAME=${VARNAMES[$SLURM_ARRAY_TASK_ID]}
echo "array task $SLURM_ARRAY_TASK_ID -> SCENARIO=$SCENARIO VARNAME=$VARNAME"

$PY scripts/10_build_future_cpl_bypass.py --scenario "$SCENARIO" --var "$VARNAME"

OUTDIR=/scratch/hpcl-cli185/zw5/future_clim/$SCENARIO
mkdir -p "$OUTDIR"
# See submit_future_cpl_bypass.sbatch for why this must be cpl_bypass_full/'s
# copy, not the parent Daymet_ERA5_TESSFA2/ dir's (different file, same name).
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
