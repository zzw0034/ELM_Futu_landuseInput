#!/usr/bin/env python
"""Chen2022 SSP1-RCP1.9 spatial evolution over SEUS at several years.
  row 1: PCT_NATVEG          (natveg loss / urbanization)
  row 2: dominant functional group within natveg  (composition change)
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap

sys.path.insert(0, "/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/src")

CH = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/"
          "processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
SEUS = dict(lon0=-95.0, lon1=-74.0, lat0=24.0, lat1=37.5)
YEARS = [2020, 2040, 2060, 2080, 2100]
GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8], "Shrub": [9, 10, 11],
          "Grass": [12, 13, 14], "Crop": [15, 16]}
GN = list(GROUPS)
GCOL = {"Bare": "#b3ac9f", "Tree": "#1c5f2c", "Shrub": "#ccb879",
        "Grass": "#dfdfc2", "Crop": "#ab6c28"}
GMAP = ListedColormap([GCOL[g] for g in GN] + ["#ffffff"])


def main():
    ch = xr.open_dataset(CH)
    lat = ch.lat.values; lon = ch.lon.values
    jl = np.where((lat >= SEUS["lat0"]) & (lat <= SEUS["lat1"]))[0]
    il = np.where((lon >= SEUS["lon0"]) & (lon <= SEUS["lon1"]))[0]
    la0, la1, lo0, lo1 = jl[0], jl[-1] + 1, il[0], il[-1] + 1
    lat_s, lon_s = lat[la0:la1], lon[lo0:lo1]
    ext = (float(lon_s[0]), float(lon_s[-1]), float(lat_s[0]), float(lat_s[-1]))
    yrs = ch.time.values.astype(int)

    def load(y):
        i = int(np.where(yrs == y)[0][0])
        nv = np.nan_to_num(ch.PCT_NATVEG.isel(time=i).values[la0:la1, lo0:lo1].astype(np.float64))
        pf = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=i).values[:, la0:la1, lo0:lo1].astype(np.float64))
        return nv, pf

    def dom_group(nv, pf):
        stack = np.stack([pf[GROUPS[g]].sum(axis=0) for g in GN])
        d = stack.argmax(axis=0).astype(np.int16)
        d[~((nv > 0) & (stack.sum(axis=0) > 0))] = len(GN)
        return d

    nyr = len(YEARS)
    fig, axes = plt.subplots(2, nyr, figsize=(3.4 * nyr, 6.6), layout="constrained")
    for c, y in enumerate(YEARS):
        nv, pf = load(y)
        # row 1: PCT_NATVEG
        a = axes[0, c]
        im = a.imshow(nv, origin="lower", extent=ext, cmap="YlGn", vmin=0, vmax=100,
                      interpolation="nearest")
        a.set_title(f"{y}", fontsize=11); a.set_xticks([]); a.set_yticks([])
        if c == 0:
            a.set_ylabel("PCT_NATVEG [%]", fontsize=10)
        if c == nyr - 1:
            fig.colorbar(im, ax=a, shrink=0.8)
        # row 2: dominant group
        b = axes[1, c]
        b.imshow(dom_group(nv, pf), origin="lower", extent=ext, cmap=GMAP,
                 vmin=0, vmax=len(GN), interpolation="nearest")
        b.set_xticks([]); b.set_yticks([])
        if c == 0:
            b.set_ylabel("dominant group\nwithin natveg", fontsize=10)
    fig.legend(handles=[mpatches.Patch(color=GCOL[g], label=g) for g in GN]
               + [mpatches.Patch(color="#ffffff", ec="0.5", label="no natveg")],
               loc="outside lower center", ncol=6, fontsize=10, frameon=False)
    fig.suptitle("Chen2022 SSP1-RCP1.9 spatial evolution over SEUS "
                 "(PCT_NATVEG · dominant functional group)", fontsize=13)
    out = OUTDIR / "figures" / "fig_chen_spatial_years_SEUS_ssp1.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")

    # quick numbers: SEUS-total natveg area proxy + group shares over years
    print("\nyear   mean_natveg%   dominant-group cell shares:")
    for y in YEARS:
        nv, pf = load(y)
        d = dom_group(nv, pf); valid = d < len(GN)
        shares = {g: 100 * np.mean(d[valid] == gi) for gi, g in enumerate(GN)}
        print(f"  {y}   {nv[nv>0].mean():6.2f}     "
              + "  ".join(f"{g} {shares[g]:4.1f}" for g in GN))
    ch.close()


if __name__ == "__main__":
    main()
