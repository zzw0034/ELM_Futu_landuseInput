import numpy as np, xarray as xr
NL="/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc"
PROC="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed"
CHEN={"SSP1_RCP19":"chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc",
      "SSP2_RCP45":"chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc",
      "SSP5_RCP85":"chen2022_landuse_CONUS_SSP5_RCP85_2015-2100_1_24deg.nc"}
S=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5)
nl=xr.open_dataset(NL); lat=nl.lat.values; lon=nl.lon.values
jl=np.where((lat>=S["la0"])&(lat<=S["la1"]))[0]; il=np.where((lon>=S["lo0"])&(lon<=S["lo1"]))[0]
a,b,c,d=jl[0],jl[-1]+1,il[0],il[-1]+1
lat_s,lon_s=lat[a:b],lon[c:d]
i23=int(np.where(nl.time.dt.year.values==2023)[0][0])
nv23=np.nan_to_num(nl.PCT_NATVEG.isel(time=i23).values[a:b,c:d].astype(np.float64))
for ssp,cf in CHEN.items():
    h=xr.open_dataset(f"{PROC}/harmonized_SEUS_{ssp}_2024-2100_1_24deg.nc")
    nvh=np.nan_to_num(h.PCT_NATVEG.values.astype(np.float64))
    zero=(nvh[-1]==0)&(nv23>0)
    jj,ii=np.where(zero)
    ch=xr.open_dataset(f"{PROC}/{cf}")
    cy=ch.time.values.astype(int)
    k20=int(np.where(cy==2020)[0][0]); k00=int(np.where(cy==2100)[0][0])
    print(f"\n=== {ssp}: {len(jj)} cell(s) natveg>0@2023 -> 0@2100 ===")
    for j,i in zip(jj,ii):
        J,I=a+j,c+i
        def g(v,k): return float(np.nan_to_num(ch[v].isel(time=k).values[J,I]))
        print(f"  lat {lat_s[j]:.2f} lon {lon_s[i]:.2f} | NLCD2023 natveg={nv23[j,i]:.2f}%")
        print(f"     Chen 2020: natveg={g('PCT_NATVEG',k20):6.2f} urban={g('PCT_URBAN',k20):6.2f} "
              f"lake={g('PCT_LAKE',k20):6.2f} glacier={g('PCT_GLACIER',k20):5.2f}")
        print(f"     Chen 2100: natveg={g('PCT_NATVEG',k00):6.2f} urban={g('PCT_URBAN',k00):6.2f} "
              f"lake={g('PCT_LAKE',k00):6.2f} glacier={g('PCT_GLACIER',k00):5.2f}")
    ch.close(); h.close()
nl.close()
