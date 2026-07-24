import numpy as np, xarray as xr
CH="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc"
S=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5); R=6371.0
GROUPS={"Bare":[0],"Tree":[1,2,3,4,5,6,7,8],"Shrub":[9,10,11],"Grass":[12,13,14],"Crop":[15,16]}
GN=list(GROUPS)
d=xr.open_dataset(CH); lat=d.lat.values; lon=d.lon.values
jl=np.where((lat>=S["la0"])&(lat<=S["la1"]))[0]; il=np.where((lon>=S["lo0"])&(lon<=S["lo1"]))[0]
a,b,c,e=jl[0],jl[-1]+1,il[0],il[-1]+1
las=lat[a:b]; lons=lon[c:e]
dla=np.mean(np.diff(las)); dlo=np.mean(np.diff(lons))
band=R**2*np.radians(dlo)*(np.sin(np.radians(las+dla/2))-np.sin(np.radians(las-dla/2)))
area=np.repeat(band[:,None],lons.size,axis=1)   # km^2 per cell
yr=d.time.values.astype(int)
def load(y):
    i=int(np.where(yr==y)[0][0])
    nv=np.nan_to_num(d.PCT_NATVEG.isel(time=i).values[a:b,c:e].astype(np.float64))
    pf=np.nan_to_num(d.PCT_NAT_PFT.isel(time=i).values[:,a:b,c:e].astype(np.float64))
    return nv,pf
nv20,pf20=load(2020); nv100,pf100=load(2100)
def garea(nv,pf,gi,area):  # km^2 of group g = natveg * groupcomp
    gc=pf[GROUPS[GN[gi]]].sum(0)      # group % of natveg
    return (nv/100.0*gc/100.0*area)   # per-cell km^2
print("SEUS land-cover AREA change 2020->2100 [km^2]   (Chen SSP2-RCP45)")
print(f"{'group':<7}{'Chen ΔA(source)':>18}{'ours ΔA(fixed nv)':>20}{'diff':>12}{'diff/|Chen|':>12}")
for gi,g in enumerate(GN):
    A_ch_20=garea(nv20,pf20,gi,area).sum(); A_ch_00=garea(nv100,pf100,gi,area).sum()
    # ours: natveg frozen at 2020, composition = Chen's each year
    A_ou_20=garea(nv20,pf20,gi,area).sum()   # ==A_ch_20 at anchor
    A_ou_00=garea(nv20,pf100,gi,area).sum()  # natveg=2020, comp=2100
    dCh=A_ch_00-A_ch_20; dOu=A_ou_00-A_ou_20
    rel=(dOu-dCh)/abs(dCh)*100 if dCh!=0 else float("nan")
    print(f"{g:<7}{dCh:>18,.0f}{dOu:>20,.0f}{dOu-dCh:>12,.0f}{rel:>11.1f}%")
# total natveg area change
An20=(nv20/100*area).sum(); An00=(nv100/100*area).sum()
print(f"\nTotal NATVEG area: 2020 {An20:,.0f}  2100(Chen) {An00:,.0f}  ΔChen {An00-An20:,.0f} km^2 (ours: 0, frozen)")
print(f"SEUS land area (natveg cells): {area[(nv20>0)|(nv100>0)].sum():,.0f} km^2")
