#!/bin/bash
#SBATCH -A hpcl-cli185
#SBATCH -p serial
#SBATCH -q normal
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem=32g
#SBATCH --time=00:30:00
#SBATCH -J pft_sums
#SBATCH -o /projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/future_runs/jobs/probe_pft_sums.%j.out
set -u
P=/projects/hpcl-cli185/proj-shared/zw5
$P/conda_envs/make_surfdata_pf/bin/python - <<PYEOF
import netCDF4, numpy as np
P="/projects/hpcl-cli185/proj-shared/zw5"
files=[("4km-FUT-ssp370",  P+"/ELM_Futu_landuseInput/outputs/processed/landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_simyr2024-2100.nc"),
       ("4km-HIST-smooth", P+"/ELM_makeSurfdata/Make_surface_data/surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_smoothHARV_simyr1850-2023_c260723.nc"),
       ("0p5-FUT-ssp370",  P+"/SEUS_halfdeg/data/processed/landuse.timeseries_SEUS_0_5deg_SSP3_RCP70_simyr2024-2100.nc"),
       ("4km-FUT-RF",      P+"/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios/landuse.timeseries_SEUS_1_24deg_nlcd2elm_RF_simyr2024-2100.nc")]
print("%-18s %-8s %14s %14s %12s %12s" % ("file","t-rec","max|sum/100-1|","median dev","n>1e-14","n active"))
for lab,f in files:
    d=netCDF4.Dataset(f)
    v=d.variables["PCT_NAT_PFT"]
    nt=v.shape[0]
    for t in ([0, nt-1] if nt>1 else [0]):
        a=np.ma.filled(v[t,:,:,:].astype("f8"), np.nan)      # (natpft, lat, lon)
        s=np.nansum(a,axis=0)/100.0
        act=np.isfinite(s) & (s>0)
        dev=np.abs(s-1.0)[act]
        if dev.size==0:
            print("%-18s %-8d   (no active cells)"%(lab,t)); continue
        print("%-18s %-8d %14.6e %14.6e %12d %12d"
              % (lab, t, dev.max(), np.median(dev), int((dev>1e-14).sum()), int(act.sum())))
    d.close()
PYEOF
