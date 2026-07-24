import numpy as np, xarray as xr
NL="/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc"
PROC="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed"
SSPS=["SSP1_RCP19","SSP2_RCP45","SSP4_RCP60","SSP5_RCP85"]
SEUS=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5)

nl=xr.open_dataset(NL)
lat=nl.lat.values; lon=nl.lon.values
jl=np.where((lat>=SEUS["la0"])&(lat<=SEUS["la1"]))[0]; il=np.where((lon>=SEUS["lo0"])&(lon<=SEUS["lo1"]))[0]
la0,la1,lo0,lo1=jl[0],jl[-1]+1,il[0],il[-1]+1
i23=int(np.where(nl.time.dt.year.values==2023)[0][0])
nv_nl=np.nan_to_num(nl.PCT_NATVEG.isel(time=i23).values[la0:la1,lo0:lo1].astype(np.float64))
pf_nl=np.nan_to_num(nl.PCT_NAT_PFT.isel(time=i23).values[:,la0:la1,lo0:lo1].astype(np.float64))
print("NLCD 2023 SEUS crop: lat %.3f..%.3f lon %.3f..%.3f  shape %s"%(lat[la0],lat[la1-1],lon[lo0],lon[lo1-1],nv_nl.shape))
print()
for ssp in SSPS:
    h=xr.open_dataset(f"{PROC}/harmonized_SEUS_{ssp}_2023-2100_1_24deg.nc")
    # grid match?
    gok = np.allclose(h.lat.values, lat[la0:la1]) and np.allclose(h.lon.values, lon[lo0:lo1])
    k=int(np.where(h.time.values.astype(int)==2023)[0][0])
    nv_h=np.nan_to_num(h.PCT_NATVEG.isel(time=k).values.astype(np.float64))
    pf_h=np.nan_to_num(h.PCT_NAT_PFT.isel(time=k).values.astype(np.float64))
    dnv=float(np.abs(nv_h-nv_nl).max())
    dpf=float(np.abs(pf_h-pf_nl).max())
    # per-PFT worst
    perpft=np.abs(pf_h-pf_nl).reshape(pf_h.shape[0],-1).max(axis=1)
    worst=int(perpft.argmax())
    print(f"{ssp}: grid_match={gok}  max|Δ PCT_NATVEG|={dnv:.2e}  max|Δ PCT_NAT_PFT|={dpf:.2e}  (worst PFT {worst}: {perpft[worst]:.2e})")
    h.close()
nl.close()
