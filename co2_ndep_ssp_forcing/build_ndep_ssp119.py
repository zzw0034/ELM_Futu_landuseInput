#!/usr/bin/env python
"""Build fndep_elm_cbgc_exp ssp119 Ndep file, same recipe as xyk's gen_fndep.py
(NCAR-CCMI ScenarioMIP raw flux files -> annual N deposition on the
fndep_elm_cbgc_exp template), adapted for one difference: the ssp119 raw
source already covers 2015-2100 (1032 months = 86 years) directly, whereas
the ssp245/370/585 sources only went to 2099 (85 years) and needed the
2100/2101 slots filled by repeating 2099. Here 2100 is real data; only 2101
needs to repeat 2100.
"""
import os
import datetime
import xarray as xr
import netCDF4 as nc4

SRC = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/co2_ndep_ssp_forcing/src_ndep_ssp119"
TEMPLATE = "/projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/ndepdata/fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_c190103.nc"
OUT_DIR = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/co2_ndep_ssp_forcing/output"
os.makedirs(OUT_DIR, exist_ok=True)

scen = "ssp119"

def src(v):
    return os.path.join(SRC, f"{v}_input4MIPs_surfaceFluxes_ScenarioMIP_NCAR-CCMI-{scen}-1-0_gn_201501-210012.nc")

ds_drynhx = xr.open_dataset(src("drynhx"))
ds_drynoy = xr.open_dataset(src("drynoy"))
ds_wetnhx = xr.open_dataset(src("wetnhx"))
ds_wetnoy = xr.open_dataset(src("wetnoy"))

# units conversion kg m-2 s-1 -> kg m-2 yr-1 (same as gen_fndep.py)
drynhx = (ds_drynhx.drynhx * 86400.0 * ds_drynhx.time.dt.days_in_month).groupby("time.year").sum("time")
wetnhx = (ds_wetnhx.wetnhx * 86400.0 * ds_wetnhx.time.dt.days_in_month).groupby("time.year").sum("time")
NDEP_NHx_year = drynhx + wetnhx

drynoy = (ds_drynoy.drynoy * 86400.0 * ds_drynoy.time.dt.days_in_month).groupby("time.year").sum("time")
wetnoy = (ds_wetnoy.wetnoy * 86400.0 * ds_wetnoy.time.dt.days_in_month).groupby("time.year").sum("time")
NDEP_NOy_year = drynoy + wetnoy

NDEP_year = NDEP_NHx_year + NDEP_NOy_year

assert NDEP_NHx_year.shape[0] == 86, NDEP_NHx_year.shape  # 2015-2100 inclusive
assert int(NDEP_NHx_year["year"].values[0]) == 2015
assert int(NDEP_NHx_year["year"].values[-1]) == 2100

cdate = "c" + datetime.datetime.now().strftime("%y%m%d")
out_path = os.path.join(OUT_DIR, f"fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp119_{cdate}.nc")
os.system(f"cp -f {TEMPLATE} {out_path}")

fndep = nc4.Dataset(out_path, "r+")

# template index 166 = year 2015, index 251 = year 2100, index 252 = year 2101
# (same convention as gen_fndep.py's comment). ssp119 source has real data for
# 2015-2100 (86 records, source index 0-85) -- fills template 166:252 fully,
# unlike the other scenarios which only had 2015-2099 (85 records) and had to
# repeat 2099 into both the 2100 and 2101 slots. Only 2101 needs repeating here.
fndep.variables["NDEP_NHx_year"][166:252, :, :] = NDEP_NHx_year.values[0:86, :, :] * 1000.0
fndep.variables["NDEP_NOy_year"][166:252, :, :] = NDEP_NOy_year.values[0:86, :, :] * 1000.0
fndep.variables["NDEP_year"][166:252, :, :] = NDEP_year.values[0:86, :, :] * 1000.0

# 2101 repeats 2100 (source index 85)
fndep.variables["NDEP_NHx_year"][252, :, :] = NDEP_NHx_year.values[85, :, :] * 1000.0
fndep.variables["NDEP_NOy_year"][252, :, :] = NDEP_NOy_year.values[85, :, :] * 1000.0
fndep.variables["NDEP_year"][252, :, :] = NDEP_year.values[85, :, :] * 1000.0

fndep.setncattr("source5", ds_drynhx.encoding["source"].split("/")[-1])
fndep.setncattr("source6", ds_wetnhx.encoding["source"].split("/")[-1])
fndep.setncattr("source7", ds_drynoy.encoding["source"].split("/")[-1])
fndep.setncattr("source8", ds_wetnoy.encoding["source"].split("/")[-1])
fndep.setncattr("history", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +
                 " created by zw5, same recipe as gen_fndep.py (xyk/Min Xu) but "
                 "ssp119 source already covers 2015-2100 (86 yr) directly, only "
                 "2101 repeats 2100")
fndep.setncattr("comment", "1849 repeat 1850 data + 1850-2014 historical data + "
                 "2015-2100 ssp119 data (real, not repeated) + 2101 repeat 2100 data")
fndep.sync()
fndep.close()

# sanity check: compare against the ssp245 file at the historical boundary
# (both should be identical for 1849-2014, since only the future branch differs)
ds119 = nc4.Dataset(out_path)
ds245 = nc4.Dataset("/projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/ndepdata/"
                     "fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp245_c240903.nc")
import numpy as np
hist_diff = np.abs(ds119["NDEP_year"][:165, :, :] - ds245["NDEP_year"][:165, :, :]).max()
print("max |diff| over shared historical period (idx 0:165):", float(hist_diff))
print("global-mean NDEP_year at 2015 (idx166):", float(np.nanmean(ds119["NDEP_year"][166, :, :])))
print("global-mean NDEP_year at 2100 (idx251):", float(np.nanmean(ds119["NDEP_year"][251, :, :])))
print("global-mean NDEP_year at 2101 (idx252) == 2100?:",
      float(np.nanmean(ds119["NDEP_year"][252, :, :])) == float(np.nanmean(ds119["NDEP_year"][251, :, :])))
print("wrote:", out_path)
