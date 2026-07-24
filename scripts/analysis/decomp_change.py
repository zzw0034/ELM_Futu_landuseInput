import numpy as np, xarray as xr
CH="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc"
S=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5)
d=xr.open_dataset(CH); lat=d.lat.values; lon=d.lon.values
jl=np.where((lat>=S["la0"])&(lat<=S["la1"]))[0]; il=np.where((lon>=S["lo0"])&(lon<=S["lo1"]))[0]
a,b,c,e=jl[0],jl[-1]+1,il[0],il[-1]+1
yr=d.time.values.astype(int)
def load(y):
    i=int(np.where(yr==y)[0][0])
    nv=np.nan_to_num(d.PCT_NATVEG.isel(time=i).values[a:b,c:e].astype(np.float64))
    pf=np.nan_to_num(d.PCT_NAT_PFT.isel(time=i).values[:,a:b,c:e].astype(np.float64))
    return nv,pf
nv0,pf0=load(2020); nv1,pf1=load(2100)
m=(nv0>5)|(nv1>5)
# (1) composition change WITHIN natveg (% of natveg) — what ELM KEEPS
dcomp=0.5*np.abs(pf1-pf0).sum(0)   # 0..100
# (2) natveg-fraction change (% of cell) — what ELM DROPS
dnv=nv1-nv0
# (3) express both as area moved in % of CELL, to compare on one scale:
#     composition term ~ natveg * dcomp/100 ; landunit term ~ |dnv|
comp_cell=(nv0/100.0)*dcomp        # % of cell reshuffled among PFTs
land_cell=np.abs(dnv)              # % of cell natveg gained/lost
def s(name,x):
    v=x[m]; print(f"   {name:<34} mean {v.mean():6.2f}  p90 {np.percentile(v,90):6.2f}  max {v.max():6.2f}")
print("Chen SSP2-RCP45  SEUS  2020->2100  (over natveg cells n=%d):"%int(m.sum()))
print(" KEPT  — composition change [% of natveg]:")
s("|Δnatpft| dissimilarity", dcomp)
print(" comparison on one scale [% of CELL area]:")
s("KEPT   composition (natveg*dcomp)", comp_cell)
s("DROPPED natveg-fraction |ΔNATVEG|", land_cell)
print(f"   ratio mean(kept)/mean(dropped) = {comp_cell[m].mean()/land_cell[m].mean():.1f}x")
print(f"   cells where natveg drops >20pp (strong urban): {int((dnv[m]<-20).sum()):,} ({(dnv[m]<-20).mean()*100:.2f}%)")
