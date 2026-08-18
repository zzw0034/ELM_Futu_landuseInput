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
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate/outputs/logs/%x_%j.err
set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_climate
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python

# usage: sbatch --export=ALL,SCENARIO=ssp245,VARNAME=TBOT jobs/submit_future_cpl_bypass.sbatch
: "${SCENARIO:?set SCENARIO=ssp119|ssp245|ssp370|ssp585}"
: "${VARNAME:?set VARNAME=PRECTmms|FSDS|TBOT|QBOT|FLDS|PSRF|WIND}"

$PY scripts/10_build_future_cpl_bypass.py --scenario "$SCENARIO" --var "$VARNAME"

OUTDIR=/scratch/hpcl-cli185/zw5/future_clim/$SCENARIO
mkdir -p "$OUTDIR"
# NOTE: copy from cpl_bypass_full/, NOT the parent Daymet_ERA5_TESSFA2/ dir.
# They differ (found 2026-08-17, md5sum): the parent-dir copy is the
# original 7-zone table (zone column 2-7, grid_map resets to 1 per zone) --
# matches cpl_bypass_full/7zone/, but NOT what the model reads. The copy
# actually inside cpl_bypass_full/ (what metdata_bypass points to, so what
# the Fortran reader's "trim(metdata_bypass)//'/zone_mappings.txt'" opens)
# has every row's zone column flattened to 1, with grid_map running as a
# single GLOBAL 1..225625 index -- matching the merged z01.nc files exactly,
# which is why the model never tries to open a nonexistent z02..z07 for a
# real zone-2+ point. Copying the parent-dir version here would make the
# future case compute zone 2-7 for most of the SEUS domain and crash trying
# to open DBCCA_Daymet_TESSFA2_<VAR>_2023-2100_z02.nc etc., which don't
# exist (only z01 is generated). See tessfa2_cpl_bypass_zone_mapping_mystery
# in the auto-memory system for the full investigation.
cp -n /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt "$OUTDIR/zone_mappings.txt"
