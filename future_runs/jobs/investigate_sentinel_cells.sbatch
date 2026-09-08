#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=64g
#SBATCH --time=02:00:00
#SBATCH -J sentinel
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/investigate_sentinel_cells.%j.out
#
# Read-only. Reads T1's h0, the production historical h0, the surfdata, the
# zone_mappings table and seven 96 GB met files -- the last by single-row
# slices, not whole-array reads, so the cost is IOPS on ~194 rows rather than
# bandwidth on 670 GB.

set -u
P=/projects/hpcl-cli185/proj-shared/zw5
PY=$P/conda_envs/make_surfdata_pf/bin/python
T=$P/ELM_Futu_landuseInput/future_runs/tools
O=/scratch/hpcl-cli185/zw5/cime_output_dirs
PROD=$O/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC

echo "### $(hostname)  $(date -Is)"
$PY $T/investigate_sentinel_cells.py \
  --h0 $O/20260905_seus_4km_fut_t0_ssp370/run/20260905_seus_4km_fut_t0_ssp370.elm.h0.2024-01-01-00000.nc \
  --prod-h0 $PROD/run/20260902_Southeast_hires_s7P_s8hdmfix_harvfixsmooth_ICB20TRCNPRDCTCBC.elm.h0.2023-02-01-00000.nc \
  --surfdata $P/ELM_makeSurfdata/Make_surface_data/s7_updataPdata/surfdata_UpdatedsoilP_SEUS_1_24deg_simyr1850_c260712.nc \
  --zones /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/zone_mappings.txt \
  --metdir /projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full/future_clim/ssp370 \
  --json $P/ELM_Futu_landuseInput/future_runs/jobs/sentinel_cells.json
echo "### exit $?  $(date -Is)"
