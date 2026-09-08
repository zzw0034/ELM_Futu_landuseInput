#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1 -n 1 -c 4
#SBATCH --mem=64g
#SBATCH --time=02:00:00
#SBATCH -J reconcile
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/reconcile_sentinel_sets.%j.out
set -u
P=/projects/hpcl-cli185/proj-shared/zw5
W=/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full
echo "### $(hostname) $(date -Is)"
$P/conda_envs/make_surfdata_pf/bin/python \
  $P/ELM_Futu_landuseInput/future_runs/tools/reconcile_sentinel_sets.py \
  --h0 /scratch/hpcl-cli185/zw5/cime_output_dirs/20260905_seus_4km_fut_t0_ssp370/run/20260905_seus_4km_fut_t0_ssp370.elm.h0.2024-01-01-00000.nc \
  --mask $P/SEUS_halfdeg/data/processed/contamination_masks_SEUS.nc \
  --zones $W/zone_mappings.txt \
  --metdir-fut $W/future_clim/ssp370 \
  --metdir-hist $W
echo "### exit $? $(date -Is)"
