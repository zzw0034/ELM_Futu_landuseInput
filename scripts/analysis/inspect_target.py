import xarray as xr, numpy as np
T="/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260712.nc"
d=xr.open_dataset(T, decode_times=False)
yr=d.YEAR.values
# temporal variation of composition, per-year vs first year, memory-safe (per time slice)
p0=np.nan_to_num(d.PCT_NAT_PFT.isel(time=0).values)
mx=0.0; changed_years=[]
for it in range(1,d.sizes["time"]):
    pt=np.nan_to_num(d.PCT_NAT_PFT.isel(time=it).values)
    dd=np.abs(pt-p0).max()
    mx=max(mx,float(dd))
    if dd>1e-6: changed_years.append(int(yr[it]))
print("PCT_NAT_PFT max|t - t0| over all years:", mx)
print("n years differing from 1850:", len(changed_years), "  first/last changed:", 
      (changed_years[0], changed_years[-1]) if changed_years else None)
# sum-to-100
s=p0.sum(0); print("PCT_NAT_PFT sum @1850: min %.3f max %.3f"%(s.min(),s.max()))
# harvest temporal: does it vary?
h0=np.nan_to_num(d.HARVEST_VH1.isel(time=0).values)
hL=np.nan_to_num(d.HARVEST_VH1.isel(time=d.sizes["time"]-1).values)
print("HARVEST_VH1 max|last-first|:", float(np.abs(hL-h0).max()))
# input filename labels
f=d.input_pftdata_filename.values
def dec(row): return "".join(c.decode() if isinstance(c,(bytes,np.bytes_)) else str(c) for c in row).strip()
print("pftdata_filename[0]  ->", dec(f[0])[-75:])
print("pftdata_filename[-1] ->", dec(f[-1])[-75:])
