import numpy as np, xarray as xr
CH="/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/chen2022_landuse_CONUS_SSP2_RCP45_2015-2100_1_24deg.nc"
S=dict(lo0=-95.0,lo1=-74.0,la0=24.0,la1=37.5); TREE=[1,2,3,4,5,6,7,8]
BLK=6  # 0.25deg / (1/24deg) = 6 fine cells per LUH2 coarse cell
d=xr.open_dataset(CH); lat=d.lat.values; lon=d.lon.values
jl=np.where((lat>=S["la0"])&(lat<=S["la1"]))[0]; il=np.where((lon>=S["lo0"])&(lon<=S["lo1"]))[0]
a,b,c,e=jl[0],jl[-1]+1,il[0],il[-1]+1
yr=d.time.values.astype(int)
def load(y):
    i=int(np.where(yr==y)[0][0])
    nv=np.nan_to_num(d.PCT_NATVEG.isel(time=i).values[a:b,c:e].astype(np.float64))
    pf=np.nan_to_num(d.PCT_NAT_PFT.isel(time=i).values[:,a:b,c:e].astype(np.float64))
    tree=pf[TREE].sum(0)   # tree share of natveg (%)
    return nv,tree
nv20,tr20=load(2020); nv100,tr100=load(2100)
# forest fraction of cell (the weight w), two ways, for year 2100:
w1=nv100/100.0*tr100/100.0        # (a) per-year natveg
w2=nv20 /100.0*tr100/100.0        # (b) fixed natveg (2020)
# crop to whole number of blocks
ny,nx=w1.shape; ny-=ny%BLK; nx-=nx%BLK
def blocks(x): return x[:ny,:nx].reshape(ny//BLK,BLK,nx//BLK,BLK)
W1=blocks(w1); W2=blocks(w2)
# normalized allocation within each 0.25deg block (harvest goes proportional to w)
def alloc(W):
    s=W.sum(axis=(1,3),keepdims=True); s[s==0]=1.0
    return W/s
A1=alloc(W1); A2=alloc(W2)
# per-block L1 redistribution = 0.5*sum|a1-a2|  (0..1 = fraction of harvest placed differently)
redist=0.5*np.abs(A1-A2).sum(axis=(1,3))          # (nblocky,nblockx)
bw=W2.sum(axis=(1,3))                             # block forest weight (where harvest lands)
mask=bw>1e-6
print("Harvest allocation difference (a) per-year natveg vs (b) fixed natveg, year 2100")
print(f"  blocks with forest: {int(mask.sum()):,}")
print(f"  redistribution per block (frac of harvest placed differently):")
print(f"     forest-weighted mean {np.average(redist[mask],weights=bw[mask])*100:.2f}%")
print(f"     plain mean {redist[mask].mean()*100:.2f}%  p90 {np.percentile(redist[mask],90)*100:.2f}%  max {redist[mask].max()*100:.2f}%")
# also raw weight relative diff where forest exists
fm=w2>0.05
print(f"  raw weight |w1-w2|/w2 over forest cells: mean {np.abs(w1-w2)[fm].mean()/w2[fm].mean()*100:.1f}%")
