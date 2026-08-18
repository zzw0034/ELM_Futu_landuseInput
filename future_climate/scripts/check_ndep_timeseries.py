import numpy as np
import xarray as xr

RUNDIR = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC/run'
CASE = '20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC'
DOMAIN = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260712_Southeast_hires_s7P_s8hdm_ICB20TRCNPRDCTCBC/run/domain.nc'

dom = xr.open_dataset(DOMAIN)
mask = dom['mask'].values
land = mask == 1

print(f'{"year":>6} {"NDEP_TO_SMINN mean (gN/m2/s)":>30} {"annualized (gN/m2/yr)":>24}')
for yr in range(2005, 2024):
    fname = f'{RUNDIR}/{CASE}.elm.h0.{yr}-02-01-00000.nc'
    ds = xr.open_dataset(fname)
    v = ds['NDEP_TO_SMINN'].mean(dim='time').values  # annual mean of monthly means, (lat,lon)
    m = float(np.nanmean(v[land]))
    print(f'{yr:6d} {m:30.6e} {m*365*86400:24.6f}')
    ds.close()
