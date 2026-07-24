#!/usr/bin/env python
"""
Compare PCT_NAT_PFT (per natpft) over the Southeast US for year 2020 between:
  A) elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc   (NLCD-based, historical)
  B) chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc (Chen2022 projection)

Layout: one row per PFT, three columns:
  col1 = A (NLCD 2020), col2 = B (Chen2022 2020), col3 = A - B (difference).
"""
import os
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FILE_A = "/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/s4_LUToutput_pft/scr_out/elmpft_from_nlcd_frac_pred_1850-2023_1_24deg.nc"
FILE_B = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc"
OUT_PNG = "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/figures/compare_PCT_NAT_PFT_SEUS_2020_A-nlcd_vs_B-chen2022.png"

# Southeast US bounding box
LON_MIN, LON_MAX = -95.0, -75.0
LAT_MIN, LAT_MAX = 24.0, 37.0
YEAR = 2020

PFT_NAMES = [
    "0 Bare_Ground",
    "1 needleleaf_evergreen_temperate_tree",
    "2 needleleaf_evergreen_boreal_tree",
    "3 needleleaf_deciduous_boreal_tree",
    "4 broadleaf_evergreen_tropical_tree",
    "5 broadleaf_evergreen_temperate_tree",
    "6 broadleaf_deciduous_tropical_tree",
    "7 broadleaf_deciduous_temperate_tree",
    "8 broadleaf_deciduous_boreal_tree",
    "9 broadleaf_evergreen_shrub",
    "10 broadleaf_deciduous_temperate_shrub",
    "11 broadleaf_deciduous_boreal_shrub",
    "12 c3_arctic_grass",
    "13 c3_non-arctic_grass",
    "14 c4_grass",
    "15 crop",
    "16 irrigated_crop",
]


def load_slice(path, year):
    ds = xr.open_dataset(path, decode_times=False)
    lat = ds["lat"].values
    lon = ds["lon"].values

    tunits = ds["time"].attrs.get("units", "")
    tvals = ds["time"].values
    if tunits.strip().lower().startswith("year"):
        tidx = int(np.where(tvals == year)[0][0])
    else:
        # "days since 1850-07-01", noleap -> year = 1850 + days/365
        yrs = 1850 + np.round(tvals / 365.0).astype(int)
        tidx = int(np.where(yrs == year)[0][0])

    ymask = (lat >= LAT_MIN) & (lat <= LAT_MAX)
    xmask = (lon >= LON_MIN) & (lon <= LON_MAX)
    yi = np.where(ymask)[0]
    xi = np.where(xmask)[0]

    da = ds["PCT_NAT_PFT"].isel(time=tidx)  # (natpft, lat, lon)
    sub = da.isel(lat=slice(yi[0], yi[-1] + 1),
                  lon=slice(xi[0], xi[-1] + 1)).values
    latsub = lat[yi[0]:yi[-1] + 1]
    lonsub = lon[xi[0]:xi[-1] + 1]
    ds.close()
    return sub.astype(float), latsub, lonsub, tidx


print("Loading A (NLCD)...")
A, latA, lonA, tiA = load_slice(FILE_A, YEAR)
print("  A time index", tiA, "shape", A.shape)
print("Loading B (Chen2022)...")
B, latB, lonB, tiB = load_slice(FILE_B, YEAR)
print("  B time index", tiB, "shape", B.shape)

assert A.shape == B.shape, "shape mismatch %s vs %s" % (A.shape, B.shape)
assert np.allclose(latA, latB) and np.allclose(lonA, lonB), "grid mismatch"

lat = latA
lon = lonA


def edges(c):
    c = np.asarray(c, float)
    e = np.empty(c.size + 1)
    e[1:-1] = 0.5 * (c[:-1] + c[1:])
    e[0] = c[0] - (c[1] - c[0]) / 2
    e[-1] = c[-1] + (c[-1] - c[-2]) / 2
    return e


lon_e = edges(lon)
lat_e = edges(lat)

npft = A.shape[0]
fig, axes = plt.subplots(npft, 3, figsize=(13.5, 2.4 * npft),
                         constrained_layout=True)

aspect = 1.0 / np.cos(np.deg2rad(0.5 * (LAT_MIN + LAT_MAX)))

for p in range(npft):
    a = A[p]
    b = B[p]
    d = a - b

    vmax = np.nanmax([np.nanmax(a) if np.isfinite(a).any() else 0.0,
                      np.nanmax(b) if np.isfinite(b).any() else 0.0])
    if not np.isfinite(vmax) or vmax <= 0:
        vmax = 1.0
    dmax = np.nanmax(np.abs(d)) if np.isfinite(d).any() else 1.0
    if not np.isfinite(dmax) or dmax <= 0:
        dmax = 1.0

    panels = [
        (a, "viridis", 0, vmax, "A: NLCD 2020"),
        (b, "viridis", 0, vmax, "B: Chen2022 2020"),
        (d, "RdBu_r", -dmax, dmax, "A - B"),
    ]
    for col, (data, cmap, vmin, vmaxx, title) in enumerate(panels):
        ax = axes[p, col]
        pm = ax.pcolormesh(lon_e, lat_e, data, cmap=cmap, vmin=vmin,
                           vmax=vmaxx, shading="auto")
        ax.set_aspect(aspect)
        ax.set_xlim(LON_MIN, LON_MAX)
        ax.set_ylim(LAT_MIN, LAT_MAX)
        cb = fig.colorbar(pm, ax=ax, fraction=0.046, pad=0.02)
        cb.ax.tick_params(labelsize=6)
        if p == 0:
            ax.set_title(title, fontsize=10)
        ax.tick_params(labelsize=6)
        if col == 0:
            ax.set_ylabel(PFT_NAMES[p], fontsize=7)

fig.suptitle("PCT_NAT_PFT (%) over Southeast US, year 2020\n"
             "A = elmpft_from_nlcd_frac_pred | B = chen2022_landuse SSP1_RCP19 "
             "| diff = A - B", fontsize=12)

os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
print("Saved:", OUT_PNG)
