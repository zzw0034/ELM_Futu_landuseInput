#!/usr/bin/env python
"""Build the 3 management-intervention landuse.timeseries scenarios
(preserve forest, half harvest, reforest-to-1850).

v2: the first attempt copied the (compressed, chunked) SSP3-7.0 NetCDF4
template with shutil.copyfile and then modified variables in place via
nc4.Dataset(..., 'r+') -- this corrupted every touched variable (HDF errors
on read-back, files ballooned to ~2x size). This is the same failure class
already documented for the climate-forcing pipeline: rewriting a compressed/
chunked HDF5 variable in place is unsafe. Fix, matching that pipeline's own
documented resolution: build each output as a brand-new NETCDF3_64BIT_OFFSET
(classic, unchunked, uncompressed) file, writing every variable once in a
single full-array assignment -- no in-place edits of compressed data.
"""
import os
import numpy as np
import netCDF4 as nc4

HIST = ("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
        "surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc")
SSP370 = ("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/"
          "landuse.timeseries_SEUS_1_24deg_nlcd2elm_SSP3_RCP70_simyr2024-2100.nc")
OUT_DIR = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/harvest_scenarios"
os.makedirs(OUT_DIR, exist_ok=True)

HARVEST_VARS = ["HARVEST_VH1", "HARVEST_VH2", "HARVEST_SH1", "HARVEST_SH2", "HARVEST_SH3"]


def clone_structure(src_path, out_path, overrides, global_note):
    """Create a fresh classic-format (NETCDF3_64BIT_OFFSET) copy of src_path,
    with every dim/var/attr copied, except variable names in `overrides`
    (dict: varname -> new ndarray) get the override data instead of the
    source's own data. No compression, no chunking, one write per variable."""
    src = nc4.Dataset(src_path)
    dst = nc4.Dataset(out_path, "w", format="NETCDF3_64BIT_OFFSET")

    for name, dim in src.dimensions.items():
        dst.createDimension(name, (None if dim.isunlimited() else len(dim)))

    for name, var in src.variables.items():
        newvar = dst.createVariable(name, var.dtype, var.dimensions)
        newvar.setncatts({k: var.getncattr(k) for k in var.ncattrs()})
        if name in overrides:
            newvar[:] = overrides[name]
        else:
            newvar[:] = var[:]

    dst.setncatts({k: src.getncattr(k) for k in src.ncattrs()})
    dst.setncattr("scenario_note", global_note)
    dst.close()
    src.close()


with nc4.Dataset(HIST) as ds:
    year_hist = ds["YEAR"][:]
    i1850 = int(np.where(year_hist == 1850)[0][0])
    i2023 = int(np.where(year_hist == 2023)[0][0])
    pft_1850 = np.array(ds["PCT_NAT_PFT"][i1850, :, :, :])
    pft_2023 = np.array(ds["PCT_NAT_PFT"][i2023, :, :, :])

with nc4.Dataset(SSP370) as ds:
    ntime = ds.dimensions["time"].size
    npft = ds.dimensions["natpft"].size
    nlat = ds.dimensions["lsmlat"].size
    nlon = ds.dimensions["lsmlon"].size
    years_future = np.array(ds["YEAR"][:])

zero_harvest = np.zeros((ntime, nlat, nlon), dtype="float64")

# ---------------------------------------------------------------- preserve forest
pft_preserve = np.broadcast_to(pft_2023, (ntime, npft, nlat, nlon)).copy()
overrides = {"PCT_NAT_PFT": pft_preserve}
overrides.update({v: zero_harvest for v in HARVEST_VARS})
out1 = os.path.join(OUT_DIR, "landuse.timeseries_SEUS_1_24deg_nlcd2elm_PRESERVE_simyr2024-2100.nc")
clone_structure(SSP370, out1, overrides,
                "preserve_forest: PCT_NAT_PFT frozen at 2023 anchor for all years "
                "2024-2100; all HARVEST_* set to zero. Built 2026-08-18 (v2, classic "
                "NetCDF format after v1's compressed in-place edit corrupted the file).")
print("wrote", out1)
del pft_preserve

# ---------------------------------------------------------------- half harvest (SSP3-7.0 baseline)
with nc4.Dataset(SSP370) as ds:
    half = {v: np.array(ds[v][:]) * 0.5 for v in HARVEST_VARS}
out2 = os.path.join(OUT_DIR, "landuse.timeseries_SEUS_1_24deg_nlcd2elm_HALFHARVEST_SSP370_simyr2024-2100.nc")
clone_structure(SSP370, out2, half,
                "half_harvest: SSP3-7.0 PCT_NAT_PFT trajectory unchanged; all 5 "
                "HARVEST_* variables scaled by 0.5 relative to the SSP3-7.0 baseline. "
                "Built 2026-08-18 (v2, classic NetCDF format).")
print("wrote", out2)
del half

# ---------------------------------------------------------------- reforest to 1850, 30-yr linear transition
TRANSITION_YEARS = 30
alphas = np.clip((years_future.astype(float) - 2023) / TRANSITION_YEARS, 0.0, 1.0)
pft_reforest = np.empty((ntime, npft, nlat, nlon), dtype="float64")
for t, a in enumerate(alphas):
    pft_reforest[t] = (1 - a) * pft_2023 + a * pft_1850
overrides = {"PCT_NAT_PFT": pft_reforest}
overrides.update({v: zero_harvest for v in HARVEST_VARS})
out3 = os.path.join(OUT_DIR, "landuse.timeseries_SEUS_1_24deg_nlcd2elm_REFOREST1850_simyr2024-2100.nc")
clone_structure(SSP370, out3, overrides,
                f"reforest_1850: PCT_NAT_PFT linearly transitions from the 2023 anchor "
                f"to the 1850 historical state over {TRANSITION_YEARS} years (2024-2053), "
                f"then holds the 1850 composition through 2100; all HARVEST_* set to "
                f"zero. Built 2026-08-18 (v2, classic NetCDF format).")
print("wrote", out3)
del pft_reforest

# ---------------------------------------------------------------- validation (read-back, must not error)
print("\n--- validation ---")
for path, label in [(out1, "preserve"), (out2, "half_harvest"), (out3, "reforest")]:
    ds = nc4.Dataset(path)
    for v in ["PCT_NAT_PFT"] + HARVEST_VARS:
        arr = np.array(ds[v][:])
        print(f"{label} {v}: read OK, shape {arr.shape}, has_nan={bool(np.isnan(arr).any())}")
    ds.close()

with nc4.Dataset(out1) as ds:
    s = np.array(ds["PCT_NAT_PFT"][:]).sum(axis=1)
    print("preserve sum-to-100 max|err|:", round(float(np.abs(s[s > 0] - 100).max()), 6))
    print("preserve 2024 vs 2023-anchor max diff:", float(np.abs(np.array(ds["PCT_NAT_PFT"][0]) - pft_2023).max()))

with nc4.Dataset(out3) as ds:
    s = np.array(ds["PCT_NAT_PFT"][:]).sum(axis=1)
    print("reforest sum-to-100 max|err|:", round(float(np.abs(s[s > 0] - 100).max()), 6))
    i2053 = int(np.where(years_future == 2053)[0][0])
    print("reforest 2053 vs 1850-target max diff:", float(np.abs(np.array(ds["PCT_NAT_PFT"][i2053]) - pft_1850).max()))
    print("reforest 2100 vs 1850-target max diff:", float(np.abs(np.array(ds["PCT_NAT_PFT"][-1]) - pft_1850).max()))

with nc4.Dataset(SSP370) as dso, nc4.Dataset(out2) as dsn:
    for v in HARVEST_VARS:
        so = float(np.nansum(dso[v][:]))
        sn = float(np.nansum(dsn[v][:]))
        ratio = sn / so if so != 0 else float("nan")
        print(f"half_harvest {v}: orig_total={round(so,4)} new_total={round(sn,4)} ratio={round(ratio,6) if so else 'orig=0'}")
