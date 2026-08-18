import numpy as np
import netCDF4 as nc

NDEP_FILE = '/projects/hpcl-cli185/world-shared/e3sm/inputdata/lnd/clm2/ndepdata/fndep_elm_cbgc_exp_simyr1849-2101_1.9x2.5_ssp245_c240903.nc'
DOMAIN = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260712_Southeast_hires_s7P_s8hdm_ICB20TRCNPRDCTCBC/run/domain.nc'

ds = nc.Dataset(NDEP_FILE)
ndep_year = ds.variables['NDEP_year']  # units: g(N)/m2/yr, already annual
lat = ds.variables['lat'][:]
lon = ds.variables['lon'][:]  # 0..360 convention

dom = nc.Dataset(DOMAIN)
xc = dom.variables['xc'][:]  # -180..180 convention (SEUS: -95..-74)
yc = dom.variables['yc'][:]
mask = dom.variables['mask'][:]
land = mask == 1

land_idx = np.where(land)
lons = xc[land_idx]
lons_0_360 = np.where(lons < 0, lons + 360.0, lons)
lats = yc[land_idx]

best_lonidx = np.argmin(np.abs(lon[None, :] - lons_0_360[:, None]), axis=1)
best_latidx = np.argmin(np.abs(lat[None, :] - lats[:, None]), axis=1)

print('matched lon range (0-360):', lon[best_lonidx].min(), lon[best_lonidx].max())
print('matched lat range:', lat[best_latidx].min(), lat[best_latidx].max())

years = list(range(2013, 2024))
print()
print(f'{"year":>6} {"true NDEP domain-mean (gN/m2/yr)":>34} {"% vs 2016 (frozen value)":>26}')
base = None
for yr in years:
    idx0 = yr - 1849
    grid_slice = ndep_year[idx0, :, :]
    vals = grid_slice[best_latidx, best_lonidx]
    m = float(np.nanmean(vals))
    if yr == 2016:
        base = m
    pct = (m / base - 1) * 100 if base else float('nan')
    print(f'{yr:6d} {m:34.6f} {pct:26.2f}')
