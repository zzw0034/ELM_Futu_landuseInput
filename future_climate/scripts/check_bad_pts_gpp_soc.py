import numpy as np
import xarray as xr
from scipy.spatial import cKDTree

DOMAIN = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260712_Southeast_hires_s7P_s8hdm_ICB20TRCNPRDCTCBC/run/domain.nc'
HIST = '/projects/hpcl-cli185/world-shared/e3sm/inputdata/atm/datm7/Daymet_ERA5_TESSFA2/cpl_bypass_full'
H0 = '/projects/hpcl-cli185/proj-shared/zw5/e3sm_run/20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC/run/20260723_Southeast_hires_s7P_s8hdmfix_harvfix_ICB20TRCNPRDCTCBC.elm.h0.2023-02-01-00000.nc'

dom = xr.open_dataset(DOMAIN)
xc = dom['xc'].values
yc = dom['yc'].values
mask = dom['mask'].values

tbot = xr.open_dataset(f'{HIST}/Daymet_ERA5_TESSFA.4km_TBOT_1980-2023_z01.nc', decode_times=False)
tbot_decoded = tbot['TBOT'].isel(DTIME=64239).values
valid = tbot_decoded < 350.0
lon = tbot['LONGXY'].values
lat = tbot['LATIXY'].values

tree = cKDTree(np.column_stack([lon, lat]))
land_idx = np.where(mask == 1)
nj_arr, ni_arr = land_idx
land_lon = xc[land_idx]
land_lat = yc[land_idx]
dist, nn_idx = tree.query(np.column_stack([land_lon, land_lat]))
bad = ~valid[nn_idx]
print('n bad:', int(bad.sum()))

bad_nj = nj_arr[bad]
bad_ni = ni_arr[bad]
bad_lon = land_lon[bad]
bad_lat = land_lat[bad]

h0 = xr.open_dataset(H0)
h0_lat = h0['lat'].values
h0_lon = h0['lon'].values
print('max abs diff lat:', float(np.max(np.abs(yc[:, 0] - h0_lat))), 'lon:', float(np.max(np.abs(xc[0, :] - h0_lon))))

gpp = h0['GPP'].isel(time=-1).values
totsomc = h0['TOTSOMC'].isel(time=-1).values

print()
header = '{:>9} {:>9} {:>4} {:>4} {:>16} {:>16}'.format('lon', 'lat', 'nj', 'ni', 'GPP(gC/m2/s)', 'TOTSOMC(gC/m2)')
print(header)
for lo, la, j, i in zip(bad_lon, bad_lat, bad_nj, bad_ni):
    line = '{:9.4f} {:9.4f} {:4d} {:4d} {:16.6e} {:16.4f}'.format(lo, la, int(j), int(i), gpp[j, i], totsomc[j, i])
    print(line)

print()
land_gpp = gpp[land_idx]
land_som = totsomc[land_idx]
print('all-land GPP  mean/min/max:', float(np.nanmean(land_gpp)), float(np.nanmin(land_gpp)), float(np.nanmax(land_gpp)))
print('all-land SOMC mean/min/max:', float(np.nanmean(land_som)), float(np.nanmin(land_som)), float(np.nanmax(land_som)))
