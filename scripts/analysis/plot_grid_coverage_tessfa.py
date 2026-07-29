#!/usr/bin/env python
"""TESSFA_SE (climate forcing) vs SEUS (land use / surface) grid coverage.

The two forcings live on different grids -- TESSFA_SE is 361x625 at 4 km,
the SEUS target is 324x504 at 1/24 deg -- so datm has to remap. This checks
the prerequisite for that: does the climate domain contain every SEUS land
cell? Prints the four edge margins and counts land cells outside, then draws
the overlay.

TESSFA_SE stops at 25.0N while the SEUS grid runs to 24.02N, so the southern
edge is short by ~1 deg (24 rows). Those rows are entirely ocean, so coverage
of the land is complete. Same 25.0N floor as the NLCD source grid (REFERENCE.md
notes the SEUS crop is 300 rows, 24 short of the 324-row target) -- the target
grid deliberately extends a degree further south over water.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

TGT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_makeSurfdata/Make_surface_data/"
           "surfdata_results/landuse.timeseries_SEUS_1_24deg_nlcd2elm_simyr1850-2023_c260723.nc")
DOM = Path("/projects/hpcl-cli185/proj-shared/TESSFA/domain_surfdata/"
           "domain.lnd.TESSFA_SE.4km.2d.c240827.nc")
OUT = Path("/projects/hpcl-cli185/proj-shared/zw5/ELM_Futu_landuseInput/outputs/figures/"
           "grid_coverage_TESSFA_SE_vs_SEUS.png")

# palette: categorical slots 1-2 (validated all-pairs), neutral land, text inks
SURF, INK, INK2, INK3 = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8880"
BLUE, ORANGE, LAND = "#2a78d6", "#eb6834", "#d8d6cd"
RES = 1.0 / 24.0


def _wrap(a):
    a = np.asarray(a, dtype=float)
    return np.where(a > 180.0, a - 360.0, a)


def main() -> int:
    with xr.open_dataset(DOM, decode_times=False) as d:
        dlon, dlat = _wrap(d["xc"].values), np.asarray(d["yc"].values, float)
    TL0, TL1, TA0, TA1 = dlon.min(), dlon.max(), dlat.min(), dlat.max()

    with xr.open_dataset(TGT, decode_times=False) as t:
        lat, lon = t["LATIXY"].values, t["LONGXY"].values
        mask = t["PFTDATA_MASK"].values
    lo0, lo1, la0, la1 = lon.min(), lon.max(), lat.min(), lat.max()

    print(f"TESSFA_SE : {dlon.shape}  lon [{TL0:9.4f}, {TL1:9.4f}]  lat [{TA0:8.4f}, {TA1:8.4f}]")
    print(f"SEUS      : {lon.shape}  lon [{lo0:9.4f}, {lo1:9.4f}]  lat [{la0:8.4f}, {la1:8.4f}]")
    print("\nedge margins (positive = TESSFA_SE extends beyond SEUS):")
    for name, m in (("west ", lo0 - TL0), ("east ", TL1 - lo1),
                    ("north", TA1 - la1), ("south", TA0 - la0)):
        # south is reported as a shortfall: TESSFA starts north of the SEUS floor
        val = -m if name == "south" else m
        print(f"   {name}  {val:+7.4f} deg   {'OK' if val >= 0 else 'SHORT'}")

    island = mask > 0
    outside = island & ((lat < TA0) | (lat > TA1) | (lon < TL0) | (lon > TL1))
    print(f"\nSEUS land cells            : {int(island.sum()):,}")
    print(f"  outside TESSFA_SE        : {int(outside.sum()):,}")
    below = lat < TA0
    print(f"  cells south of {TA0:.1f}N       : {int(below.sum()):,} "
          f"({int(np.where(below.any(axis=1))[0].max()) + 1} rows), "
          f"of which land: {int((below & island).sum()):,}")

    ext = [lo0 - RES / 2, lo1 + RES / 2, la0 - RES / 2, la1 + RES / 2]
    fig, ax = plt.subplots(figsize=(11.6, 7.4), dpi=170)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)

    ax.imshow(np.where(island, 1.0, np.nan), origin="lower", extent=ext,
              cmap=matplotlib.colors.ListedColormap([LAND]),
              interpolation="nearest", zorder=2)
    ax.add_patch(Rectangle((lo0 - RES / 2, la0 - RES / 2), (lo1 - lo0) + RES,
                           TA0 - (la0 - RES / 2), facecolor=ORANGE, alpha=0.13,
                           hatch="///", edgecolor=ORANGE, linewidth=0, zorder=3))
    ax.add_patch(Rectangle((TL0, TA0), TL1 - TL0, TA1 - TA0, fill=False,
                           edgecolor=BLUE, linewidth=2.0, zorder=5))
    ax.add_patch(Rectangle((lo0 - RES / 2, la0 - RES / 2), (lo1 - lo0) + RES,
                           (la1 - la0) + RES, fill=False, edgecolor=ORANGE,
                           linewidth=2.0, zorder=6))

    ax.annotate(f"TESSFA_SE  ·  climate  ·  {dlon.shape[0]}×{dlon.shape[1]} @ 4 km",
                (TL0 + 0.35, TA1 - 0.55), color=BLUE, fontsize=10.5,
                fontweight="bold", zorder=8)
    ax.annotate(f"SEUS  ·  land use  ·  {lon.shape[0]}×{lon.shape[1]} @ 1/24°",
                (lo0 + 0.3, la1 - 0.55), color=ORANGE, fontsize=10.5,
                fontweight="bold", zorder=8)
    ax.annotate(f"gap: {int(np.where(below.any(axis=1))[0].max()) + 1} rows south of {TA0:.1f}°N\n"
                f"{int(below.sum()):,} cells — {int((below & island).sum())} of them land",
                (-88.0, 24.46), color=ORANGE, fontsize=9.4, ha="center",
                va="center", fontweight="bold", zorder=8)
    ax.annotate(f"north  +{TA1-la1:.2f}°", (TL1 - 0.3, TA1 + 0.28), color=INK2,
                fontsize=9, ha="right", zorder=8)
    ax.annotate(f"south  −{TA0-la0:.2f}°", (TL1 - 0.3, TA0 - 0.42), color=INK2,
                fontsize=9, ha="right", zorder=8)
    ax.annotate(f"west  +{lo0-TL0:.2f}°", (TL0 + 0.35, 31.0), color=INK2,
                fontsize=9, zorder=8)
    ax.annotate(f"east  +{TL1-lo1:.2f}°\n(≈ half a cell)", (TL1 - 0.35, 31.0),
                color=INK2, fontsize=9, ha="right", zorder=8)

    ax.legend(handles=[Line2D([], [], color=BLUE, lw=2.0, label="TESSFA_SE  (climate forcing)"),
                       Line2D([], [], color=ORANGE, lw=2.0, label="SEUS  (land use / surface)"),
                       Line2D([], [], color=LAND, lw=7, label=f"SEUS land cells  ({int(island.sum()):,})")],
              loc="upper left", frameon=False, fontsize=9.5, labelcolor=INK2,
              ncol=3, bbox_to_anchor=(0.0, -0.085), borderaxespad=0)

    ax.set_xlim(TL0 - 0.9, TL1 + 0.9)
    ax.set_ylim(la0 - 1.1, TA1 + 0.9)
    ax.set_xlabel("longitude (°E)", color=INK2, fontsize=9.5)
    ax.set_ylabel("latitude (°N)", color=INK2, fontsize=9.5)
    ax.set_title("TESSFA_SE covers every SEUS land cell — the 1° shortfall is all ocean",
                 color=INK, fontsize=13.5, fontweight="bold", pad=13, loc="left")
    ax.grid(True, color=INK3, alpha=0.22, linewidth=0.6, zorder=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK3)
    ax.set_aspect(1.18)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT, facecolor=SURF, bbox_inches="tight")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
