#!/usr/bin/env python
"""Chen2022 SSP1-RCP1.9 change map 2020->2100 over SEUS.
Per functional group, Delta of its share of the WHOLE cell
  P_g = PCT_NATVEG * (group PFT sum within natveg)/100     [% of cell]
plus Delta PCT_NATVEG. Diverging maps make the trend direct.
"""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

CH = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/"
          "processed/chen2022_landuse_CONUS_SSP1_RCP19_2015-2100_1_24deg.nc")
OUTDIR = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs")
SEUS = dict(lon0=-95.0, lon1=-74.0, lat0=24.0, lat1=37.5)
Y0, Y1 = 2020, 2100
GROUPS = {"Bare": [0], "Tree": [1, 2, 3, 4, 5, 6, 7, 8], "Shrub": [9, 10, 11],
          "Grass": [12, 13, 14], "Crop": [15, 16]}
GN = list(GROUPS)
R = 6371.0


def cell_area_km2(lat, lon):
    dlat = float(np.mean(np.diff(lat))); dlon = float(np.mean(np.diff(lon)))
    ln = np.radians(lat + dlat/2); ls = np.radians(lat - dlat/2)
    return np.repeat((R**2 * np.radians(dlon) * (np.sin(ln) - np.sin(ls)))[:, None], lon.size, axis=1)


def main():
    ch = xr.open_dataset(CH)
    lat = ch.lat.values; lon = ch.lon.values
    jl = np.where((lat >= SEUS["lat0"]) & (lat <= SEUS["lat1"]))[0]
    il = np.where((lon >= SEUS["lon0"]) & (lon <= SEUS["lon1"]))[0]
    la0, la1, lo0, lo1 = jl[0], jl[-1] + 1, il[0], il[-1] + 1
    lat_s, lon_s = lat[la0:la1], lon[lo0:lo1]
    ext = (float(lon_s[0]), float(lon_s[-1]), float(lat_s[0]), float(lat_s[-1]))
    area = cell_area_km2(lat_s, lon_s)
    yrs = ch.time.values.astype(int)

    def Pg(y):
        i = int(np.where(yrs == y)[0][0])
        nv = np.nan_to_num(ch.PCT_NATVEG.isel(time=i).values[la0:la1, lo0:lo1].astype(np.float64))
        pf = np.nan_to_num(ch.PCT_NAT_PFT.isel(time=i).values[:, la0:la1, lo0:lo1].astype(np.float64))
        p = pf * nv[None] / 100.0                              # p(j), % of cell
        return nv, np.stack([p[GROUPS[g]].sum(0) for g in GN])  # (NG,ny,nx)

    nv0, P0 = Pg(Y0); nv1, P1 = Pg(Y1)
    dP = P1 - P0                                               # (NG,ny,nx)
    dnv = nv1 - nv0
    mask = (nv0 > 0) | (nv1 > 0)

    # panels: 5 groups + dNATVEG
    panels = [(f"Δ {g}  [% of cell]", np.where(mask, dP[gi], np.nan), 15) for gi, g in enumerate(GN)]
    panels.append(("Δ PCT_NATVEG  [pp]", np.where(mask, dnv, np.nan), 15))

    fig, axes = plt.subplots(2, 3, figsize=(16, 8.2), layout="constrained")
    for ax, (ttl, arr, vm) in zip(axes.ravel(), panels):
        im = ax.imshow(arr, origin="lower", extent=ext, cmap="RdBu_r",
                       norm=TwoSlopeNorm(vmin=-vm, vcenter=0, vmax=vm), interpolation="nearest")
        ax.set_title(ttl, fontsize=11); ax.set_xticks([]); ax.set_yticks([])
        fig.colorbar(im, ax=ax, shrink=0.75)
    fig.suptitle(f"Chen2022 SSP1-RCP1.9  change {Y0}→{Y1} over SEUS "
                 f"(red = increase, blue = decrease)", fontsize=13)
    out = OUTDIR / "figures" / f"fig_chen_change_{Y0}_{Y1}_SEUS_ssp1.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")

    w = area[mask]
    print(f"\nSEUS area-weighted mean Δ ({Y0}→{Y1}), % of cell:")
    for gi, g in enumerate(GN):
        print(f"  Δ{g:<6} {np.average(dP[gi][mask], weights=w):+6.3f}")
    print(f"  ΔNATVEG {np.average(dnv[mask], weights=w):+6.3f}")
    ch.close()


if __name__ == "__main__":
    main()
