#!/usr/bin/env python
"""What does the LUH2 source actually look like? One example year, native grid.

Three things worth seeing side by side:

  row 1  the five *_harv transition variables on the native 0.25 deg grid.
         Only secmf_harv (secondary mature forest) carries anything in SEUS;
         the other four are structurally empty here.
  row 2  the LUH2 land STATE (states.nc, 2015) -- primf/secdf vs primn/secdn
         plus managed land. This is what decides whether harvest is possible
         at all: no forest state => no wood harvest, by construction.
  row 3  the 0.25 deg source next to our 1/24 deg downscaled product for the
         same year, and a zoom on the western-Arkansas cells where LUH2 has
         zero forest (and therefore zero harvest) inside otherwise forested
         country.

Time convention (stage B, k=-1): output label year Y <-> LUH2 calendar Y-1.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput")
LUH_DIR = Path("/projects/hpcl-cli185/proj-shared/zw5/luh")
PROC = ROOT / "outputs" / "processed"
STEM = "landuse.timeseries_SEUS_1_24deg_nlcd2elm_%s_simyr2024-2100.nc"

SCEN = "SSP2_RCP45"
LUH_F = "ssp2rcp45_transitions.nc"
LUH_YEAR = 2050                 # calendar year in the LUH2 file
OUT_YEAR = LUH_YEAR + 1         # the output label year it feeds (k=-1)
LUH_YEAR0 = 2015
STATES_YEAR = 2015              # states.nc is the historical file; last step

# SEUS window
LON0, LON1, LAT0, LAT1 = -95.0, -74.0, 24.0, 37.5
# the zero-harvest square found by 08_harvest_block_diag.py
HOLE = (-94.5, -94.0, 34.5, 35.0)

HARV = ["primf_harv", "primn_harv", "secmf_harv", "secyf_harv", "secnf_harv"]
HARV_LAB = ["primf_harv\nprimary forest", "primn_harv\nprimary non-forest",
            "secmf_harv\nsecondary mature forest", "secyf_harv\nsecondary young forest",
            "secnf_harv\nsecondary non-forest"]
STATE = ["primf", "secdf", "primn", "secdn"]
STATE_LAB = ["primf\nprimary FOREST", "secdf\nsecondary FOREST",
             "primn\nprimary NON-forest", "secdn\nsecondary NON-forest"]


def window(ds):
    """Return (lat_asc_idx, lon_idx, extent) for the SEUS window on a LUH2 grid."""
    lat, lon = ds.lat.values, ds.lon.values
    li = np.where((lat >= LAT0) & (lat <= LAT1))[0]
    lj = np.where((lon >= LON0) & (lon <= LON1))[0]
    return li, lj, (float(lon[lj].min()) - 0.125, float(lon[lj].max()) + 0.125,
                    float(lat[li].min()) - 0.125, float(lat[li].max()) + 0.125)


def show(ax, a, ext, cmap, vmin=None, vmax=None, title="", flip=True):
    if flip:
        a = a[::-1]                      # LUH2 lat descends -> plot ascending
    im = ax.imshow(a, origin="lower", extent=ext, cmap=cmap, vmin=vmin, vmax=vmax,
                   interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=9)
    return im


def mark_hole(ax, color="#00b0f0", label=False, pad=1.0):
    """Ring the western-Arkansas cells. At SEUS scale the box is 0.5 deg across --
    barely two pixels -- so draw a leader line and a label as well."""
    x0, x1, y0, y1 = HOLE
    ax.add_patch(Rectangle((x0 - 0.02, y0 - 0.02), x1 - x0 + 0.04, y1 - y0 + 0.04,
                           fill=False, ec=color, lw=2.0, zorder=6))
    if label:
        ax.annotate("Ouachita\n(no forest state)", xy=(x0, y1), xycoords="data",
                    xytext=(x0 + 1.2, y1 + pad), textcoords="data",
                    fontsize=8, color=color, fontweight="bold", ha="left",
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.4),
                    zorder=7)


def main():
    tr = xr.open_dataset(LUH_DIR / LUH_F, decode_times=False)
    li, lj, ext = window(tr)
    hidx = LUH_YEAR - LUH_YEAR0
    print(f"{LUH_F}  calendar {LUH_YEAR} -> time index {hidx}")
    print(f"window {len(li)} x {len(lj)} cells at 0.25 deg, extent {ext}")

    # Subfigures rather than one GridSpec: the wide SEUS panels and the near-square
    # zoom panels have very different aspect ratios, and mixing them in a single
    # grid leaves the row titles colliding with the axes.
    fig = plt.figure(figsize=(19, 15.5))
    sfs = fig.subfigures(5, 1, height_ratios=[0.10, 1.0, 1.0, 0.95, 1.35],
                         hspace=0.02)
    sfs[0].suptitle(f"What the LUH2 harvest forcing looks like — {SCEN}, example "
                    f"year {LUH_YEAR} (feeds output year {OUT_YEAR})", fontsize=16)

    # ---- row 1: the five harvest transition variables ---------------------
    axs = sfs[1].subplots(1, 5)
    hv = {}
    for k, v in enumerate(HARV):
        a = np.nan_to_num(tr[v].isel(time=hidx, lat=li, lon=lj).values.astype(np.float64))
        hv[v] = a
        nz = int((a > 0).sum())
        note = "ALL ZERO in window" if nz == 0 else f"max {a.max():.4f}, nonzero {nz} cells"
        im = show(axs[k], a, ext, "YlOrRd", 0, max(a.max(), 1e-12),
                  f"{HARV_LAB[k]}\n{note}")
        mark_hole(axs[k])
        if nz:
            sfs[1].colorbar(im, ax=axs[k], shrink=0.8, pad=0.02)
    sfs[1].suptitle(f"1. LUH2 v2f {LUH_F} — the five harvest variables, calendar "
                    f"{LUH_YEAR}, native 0.25°  [fraction of grid cell harvested "
                    f"that year].  Blue box = the zero-harvest square.", fontsize=13)

    # ---- row 2: the land state that permits harvest -----------------------
    st = xr.open_dataset(LUH_DIR / "states.nc", decode_times=False)
    sli, slj, sext = window(st)
    axs = sfs[2].subplots(1, 5)
    for k, v in enumerate(STATE):
        a = np.nan_to_num(st[v].isel(time=-1, lat=sli, lon=slj).values.astype(np.float64))
        im = show(axs[k], a, sext, "YlGn" if v.endswith("f") else "YlOrBr",
                  0, 1, STATE_LAB[k])
        mark_hole(axs[k])
        sfs[2].colorbar(im, ax=axs[k], shrink=0.8, pad=0.02)
    managed = sum(np.nan_to_num(st[v].isel(time=-1, lat=sli, lon=slj).values.astype(np.float64))
                  for v in ("pastr", "range", "c3ann", "c4ann", "c3per", "c4per",
                            "c3nfx", "urban") if v in st.data_vars)
    im = show(axs[4], managed, sext, "PuRd", 0, 1,
              "pastr+range+crops+urban\n(managed land)")
    mark_hole(axs[4])
    sfs[2].colorbar(im, ax=axs[4], shrink=0.8, pad=0.02)
    sfs[2].suptitle(f"2. LUH2 land state ({STATES_YEAR}) — harvest is only possible where "
                    f"a FOREST state exists. In the blue box primf = secdf = 0.", fontsize=13)
    st.close()

    # ---- row 3: source resolution vs our downscaled product ---------------
    axs = sfs[3].subplots(1, 2)
    a = hv["secmf_harv"]
    im = show(axs[0], a, ext, "YlOrRd", 0, a.max(),
              f"LUH2 secmf_harv {LUH_YEAR} — native 0.25°  ({len(li)}×{len(lj)} cells)")
    mark_hole(axs[0], label=True)
    sfs[3].colorbar(im, ax=axs[0], shrink=0.8, pad=0.02)

    ds = xr.open_dataset(PROC / (STEM % SCEN), decode_times=False)
    yrs = ds.YEAR.values.astype(int)
    t = int(np.where(yrs == OUT_YEAR)[0][0])
    ours = np.nan_to_num(ds.HARVEST_SH1.isel(time=t).values.astype(np.float64))
    olat = ds.LATIXY.values[:, 0]; olon = ds.LONGXY.values[0, :]
    oext = (olon[0], olon[-1], olat[0], olat[-1])
    ds.close()
    im = show(axs[1], np.where(ours > 0, ours, np.nan), oext, "YlOrRd",
              0, np.nanpercentile(ours[ours > 0], 99),
              f"ours HARVEST_SH1 {OUT_YEAR} — 1/24°  ({olat.size}×{olon.size} cells)",
              flip=False)
    mark_hole(axs[1], label=True)
    sfs[3].colorbar(im, ax=axs[1], shrink=0.8, pad=0.02)
    sfs[3].suptitle("3. The 0.25° source next to the 1/24° product it produces — "
                    "6×6 fine cells per source cell, so the source cell edges survive "
                    "as the visible squares.", fontsize=13)

    # ---- row 4: zoom on the hole, values and forest state ----------------
    zlon0, zlon1, zlat0, zlat1 = -96.0, -92.5, 33.5, 36.5
    zi = np.where((tr.lat.values >= zlat0) & (tr.lat.values <= zlat1))[0]
    zj = np.where((tr.lon.values >= zlon0) & (tr.lon.values <= zlon1))[0]
    za = np.nan_to_num(tr.secmf_harv.isel(time=hidx, lat=zi, lon=zj).values.astype(np.float64))
    zlatv = tr.lat.values[zi]; zlonv = tr.lon.values[zj]
    zext = (zlonv.min() - 0.125, zlonv.max() + 0.125,
            zlatv.min() - 0.125, zlatv.max() + 0.125)
    axs = sfs[4].subplots(1, 2)
    im = show(axs[0], za, zext, "YlOrRd", 0, za.max(),
              f"secmf_harv {LUH_YEAR} — each square is ONE 0.25° cell (value ×1000)")
    zaf = za[::-1]
    for r in range(zaf.shape[0]):
        for c in range(zaf.shape[1]):
            v = zaf[r, c] * 1000
            axs[0].text(zlonv.min() + c * 0.25, zlatv.min() + r * 0.25, f"{v:.1f}",
                        ha="center", va="center", fontsize=7,
                        color="w" if v > za.max() * 1000 * 0.6 else "k")
    mark_hole(axs[0])
    sfs[4].colorbar(im, ax=axs[0], shrink=0.8, pad=0.02)

    st = xr.open_dataset(LUH_DIR / "states.nc", decode_times=False)
    zi2 = np.where((st.lat.values >= zlat0) & (st.lat.values <= zlat1))[0]
    zj2 = np.where((st.lon.values >= zlon0) & (st.lon.values <= zlon1))[0]
    forest = sum(np.nan_to_num(st[v].isel(time=-1, lat=zi2, lon=zj2).values.astype(np.float64))
                 for v in ("primf", "secdf"))
    im = show(axs[1], forest, zext, "YlGn", 0, 1,
              f"LUH2 forest state primf+secdf ({STATES_YEAR}) — same zoom")
    ff = forest[::-1]
    for r in range(ff.shape[0]):
        for c in range(ff.shape[1]):
            axs[1].text(zlonv.min() + c * 0.25, zlatv.min() + r * 0.25,
                        f"{ff[r, c]:.2f}", ha="center", va="center", fontsize=7,
                        color="w" if ff[r, c] > 0.6 else "k")
    mark_hole(axs[1])
    sfs[4].colorbar(im, ax=axs[1], shrink=0.8, pad=0.02)
    sfs[4].suptitle("4. Western Arkansas: four cells with no forest state at all, so no "
                    "harvest is possible — while our NLCD-derived map has 77% tree cover "
                    "there.", fontsize=13)
    st.close()
    tr.close()



    out = ROOT / "outputs" / "figures" / "fig_luh2_source_look.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")

    # a few numbers for the log
    print("\nharvest variables in the SEUS window, calendar %d:" % LUH_YEAR)
    for v in HARV:
        a = hv[v]
        print(f"  {v:<12} nonzero cells {int((a>0).sum()):>5} / {a.size}   "
              f"max {a.max():.5f}   mean over nonzero "
              f"{a[a>0].mean() if (a>0).any() else 0:.5f}")


if __name__ == "__main__":
    main()
