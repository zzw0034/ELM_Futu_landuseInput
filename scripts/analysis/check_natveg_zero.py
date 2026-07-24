import numpy as np, xarray as xr
NL="/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc"
PROC="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed"
SSPS=["SSP1_RCP19","SSP2_RCP45","SSP4_RCP60","SSP5_RCP85"]
S=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5)
nl=xr.open_dataset(NL); lat=nl.lat.values; lon=nl.lon.values
jl=np.where((lat>=S["la0"])&(lat<=S["la1"]))[0]; il=np.where((lon>=S["lo0"])&(lon<=S["lo1"]))[0]
a,b,c,d=jl[0],jl[-1]+1,il[0],il[-1]+1
i23=int(np.where(nl.time.dt.year.values==2023)[0][0])
nv23=np.nan_to_num(nl.PCT_NATVEG.isel(time=i23).values[a:b,c:d].astype(np.float64))
start=nv23>0
print(f"NLCD 2023 anchor: cells with natveg>0 = {int(start.sum()):,} of {start.size:,}\n")
for ssp in SSPS:
    h=xr.open_dataset(f"{PROC}/harmonized_SEUS_{ssp}_2024-2100_1_24deg.nc")
    nv=np.nan_to_num(h.PCT_NATVEG.values.astype(np.float64))     # (77,ny,nx)
    yrs=h.time.values.astype(int)
    hit0_any = (nv==0).any(axis=0) & start          # 起点>0，某年变成 0
    zero_end = (nv[-1]==0) & start                  # 2100 时为 0
    # 最早归零的年份
    if hit0_any.any():
        firstzero=np.where(nv==0, np.arange(nv.shape[0])[:,None,None], 10**6).min(axis=0)
        yr_first=yrs[np.clip(firstzero[hit0_any],0,len(yrs)-1)]
        yspan=f"{yr_first.min()}..{yr_first.max()}"
    else:
        yspan="-"
    # 这些格点的组成是否为全 0
    if zero_end.any():
        pf_end=np.nan_to_num(h.PCT_NAT_PFT.isel(time=len(yrs)-1).values.astype(np.float64))
        comp_sum=pf_end.sum(axis=0)[zero_end]
        comps=f"max comp-sum in those cells = {comp_sum.max():.4f}"
    else:
        comps="-"
    nmin=nv[-1][start].min()
    print(f"{ssp}:")
    print(f"   natveg>0 @2023 → ==0 at some year : {int(hit0_any.sum()):,} cells   (first-zero year range {yspan})")
    print(f"   natveg>0 @2023 → ==0 at 2100      : {int(zero_end.sum()):,} cells   {comps}")
    print(f"   min natveg @2100 among started>0  : {nmin:.4g}")
    h.close()
nl.close()
