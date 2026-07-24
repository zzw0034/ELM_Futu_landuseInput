import glob, numpy as np, xarray as xr
files=sorted(glob.glob("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/chen2022_landuse_CONUS_*_1_24deg.nc"))
print("verifying %d files\n"%len(files))
for f in files:
    ds=xr.open_dataset(f)
    lat=ds.lat.values; south=lat<45.0
    nt=ds.sizes["time"]
    p3max=0.0; p3cells=0; devmax=0.0
    for it in range(nt):                      # per-time to keep memory low
        pf=np.nan_to_num(ds.PCT_NAT_PFT.isel(time=it).values.astype(np.float64))  # (npft,lat,lon)
        nv=np.nan_to_num(ds.PCT_NATVEG.isel(time=it).values.astype(np.float64))
        p3=pf[3]
        p3max=max(p3max,float(p3[south,:].max()))
        p3cells+=int((p3[south,:]>0.01).sum())
        s=pf.sum(axis=0); m=nv>0
        if m.any(): devmax=max(devmax,float(np.abs(s[m]-100.0).max()))
    # also check PFT1 got the mass (nonzero somewhere south)
    p1_south=float(np.nan_to_num(ds.PCT_NAT_PFT.isel(time=nt-1).values[1])[south,:].max())
    print("%-52s PFT3 south<45N: max=%.4f cells>0.01=%6d | max|sum-100|=%.4f | PFT1 south max=%.1f"%(
        f.split("/")[-1], p3max, p3cells, devmax, p1_south))
    ds.close()
