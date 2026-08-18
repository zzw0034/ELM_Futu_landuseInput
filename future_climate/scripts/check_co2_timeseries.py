import numpy as np
import xarray as xr

RUNDIR = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC/run'
CASE = '20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC'
DOMAIN = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260712_Southeast_hires_s7P_s8hdm_ICB20TRCNPRDCTCBC/run/domain.nc'

dom = xr.open_dataset(DOMAIN)
mask = dom['mask'].values
land = mask == 1

years = [1850, 1900, 1950, 1980, 2000, 2010, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
print(f'{"year":>6} {"PCO2 mean (Pa)":>16} {"~ppm (Pa/101325*1e6)":>22}')
for yr in years:
    fname = f'{RUNDIR}/{CASE}.elm.h0.{yr}-02-01-00000.nc'
    ds = xr.open_dataset(fname)
    v = ds['PCO2'].mean(dim='time').values
    m = float(np.nanmean(v[land]))
    ppm = m / 101325.0 * 1e6
    print(f'{yr:6d} {m:16.4f} {ppm:22.2f}')
    ds.close()
