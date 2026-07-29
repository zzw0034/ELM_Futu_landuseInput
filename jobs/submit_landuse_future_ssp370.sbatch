#!/bin/bash
#SBATCH -J lu_future_ssp370
#SBATCH -A hpcl-cli185
#SBATCH -p hpcl-cli185
#SBATCH -q hpcl-cli185
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH --mem=64g
#SBATCH -t 00:40:00
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.out
#SBATCH -e /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/logs/%x_%j.err

# Stage 2 for SSP3_RCP70 only: harmonize + build landuse.timeseries.
# Single-scenario twin of submit_landuse_future.sbatch. Reads the Stage 1
# interim file and the LUH2 v2f ssp3rcp70 harvest transitions.
#
# Submit after Stage 1, e.g.
#   j=$(sbatch --parsable jobs/submit_chen_targetgrid_ssp370.sbatch)
#   sbatch --dependency=afterok:$j jobs/submit_landuse_future_ssp370.sbatch

set -euo pipefail
cd /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput
PY=/projects/hpcl-cli185/proj-shared/zw5/conda_envs/make_surfdata_pf/bin/python
export PYTHONPATH="$PWD/src"
SC=SSP3_RCP70

# Fail early and clearly if either input is missing, rather than deep inside
# the harmonization.
CHEN=outputs/interim/chen_targetgrid_${SC}_2015-2100_1_24deg.nc
LUH=/projects/hpcl-cli185/proj-shared/zw5/luh/ssp3rcp70_transitions.nc
for f in "$CHEN" "$LUH"; do
    [ -s "$f" ] || { echo "FATAL: missing input $f"; exit 1; }
done

echo "==================== $SC ===================="
$PY scripts/02_harmonize_seus.py --build-timeseries --scenario "$SC"

ls -lh outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_${SC}_simyr2024-2100.nc
