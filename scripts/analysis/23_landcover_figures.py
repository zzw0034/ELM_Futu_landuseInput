#!/usr/bin/env python
"""Comparison figures: NLCD (30 m) vs Chen2022 (1 km).

  fig1  CONUS dominant class, NLCD 2015 | Chen 2015          (1200 m display)
  fig2  native-resolution zooms: NLCD at true 30 m | Chen at true 1 km
  fig3  area by class, 2015, NLCD vs Chen
  fig4  class-fraction difference maps, Chen - NLCD, 2015     (1200 m display)
  fig5  area by class, 2020, NLCD vs the four SSP scenarios

fig2 is the only one that shows the products as they actually are: no
decimation, no warping, each in its own projection at its own resolution.
The CONUS-wide panels necessarily use the 1200 m display grid built by
script 21 -- 160000 x 105000 does not fit in a figure. All *numbers*, here
and in script 22, come from the native-resolution counts of script 20.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from rasterio.transform import rowcol  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402
from rasterio.windows import Window  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from elm_landuse.common_legend import (  # noqa: E402
    COMMON_CLASSES,
    COMMON_COLORS,
    COMMON_NAMES,
    COMMON_NODATA,
    chen_lut,
    nlcd_lut,
)
from elm_landuse.raster_io import find_tif  # noqa: E402

_stats = import_module("20_landcover_native_stats")
_tables = import_module("22_landcover_tables")
nlcd_path = _stats.nlcd_path

NCLS = len(COMMON_CLASSES)
CMAP = ListedColormap([COMMON_COLORS[c] for c in COMMON_CLASSES] + ["#ffffff"])

SSPS = ["2020_SSP1_RCP19", "2020_SSP2_RCP45", "2020_SSP4_RCP60", "2020_SSP5_RCP85"]

# 80 km boxes chosen to expose the three structural disagreements.
ZOOMS = [
    ("Everglades, FL", -80.90, 25.90, "NLCD wetland; Chen has no wetland class"),
    ("Washington–Baltimore", -76.90, 39.10, "dispersed development"),
    ("Central Iowa", -93.60, 42.00, "cropland / pasture mosaic"),
]
ZOOM_HALF_KM = 40.0


def _legend_handles(include_nodata: bool = True):
    h = [
        mpatches.Patch(facecolor=COMMON_COLORS[c], edgecolor="0.3", label=COMMON_NAMES[c])
        for c in COMMON_CLASSES
    ]
    if include_nodata:
        h.append(mpatches.Patch(facecolor="#ffffff", edgecolor="0.3", label="No data"))
    return h


def _show_dom(ax, dom, extent, title):
    d = dom.astype(np.int16).copy()
    d[d == COMMON_NODATA] = NCLS
    ax.imshow(d, cmap=CMAP, vmin=0, vmax=NCLS, extent=extent, interpolation="nearest")
    ax.set_title(title, fontsize=11)
    ax.set_xticks([])
    ax.set_yticks([])


def fig1_conus(z, outdir: Path) -> None:
    tr = z["display_transform"]
    x0, dx, _, y0, _, dy = tr
    ny, nx = z["nlcd_2015_dom"].shape
    extent = (x0 / 1e3, (x0 + nx * dx) / 1e3, (y0 + ny * dy) / 1e3, y0 / 1e3)

    fig, axes = plt.subplots(2, 1, figsize=(13, 12.5))
    _show_dom(
        axes[0],
        z["nlcd_2015_dom"],
        extent,
        "NLCD 2015 — dominant class of each 1200 m cell\n"
        "(majority of 1600 native 30 m pixels; no resampling filter)",
    )
    _show_dom(
        axes[1],
        z["chen_2015_historical_dom"],
        extent,
        "Chen2022 2015 — dominant class\n(native 1 km EASE-Grid, warped to the "
        "same display grid)",
    )
    fig.legend(
        handles=_legend_handles(),
        loc="lower center",
        ncol=6,
        frameon=False,
        fontsize=10,
        bbox_to_anchor=(0.5, 0.005),
    )
    fig.suptitle(
        "CONUS land cover 2015: NLCD vs Chen2022, common 10-class legend",
        fontsize=14,
        y=0.98,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    p = outdir / "fig1_conus_dominant_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def _read_native_zoom(path: Path, lut, lon, lat, half_km, is_chen):
    """Read a lon/lat box from one product at its own native resolution."""
    with rasterio.open(path) as ds:
        # box in the product's own CRS, via a local metric approximation
        l, b, r, t = transform_bounds(
            "EPSG:4326",
            ds.crs,
            lon - half_km / (111.32 * np.cos(np.radians(lat))),
            lat - half_km / 110.57,
            lon + half_km / (111.32 * np.cos(np.radians(lat))),
            lat + half_km / 110.57,
            densify_pts=21,
        )
        row0, col0 = rowcol(ds.transform, l, t, op=int)
        row1, col1 = rowcol(ds.transform, r, b, op=int)
        col0, col1 = max(0, col0), min(ds.width, col1)
        row0, row1 = max(0, row0), min(ds.height, row1)
        win = Window(col0, row0, col1 - col0, row1 - row0)
        arr = ds.read(1, window=win)  # native resolution, no out_shape
        wt = ds.window_transform(win)
        res = abs(ds.transform.a)
    codes = lut[arr.view(np.uint8) if is_chen else arr]
    ny, nx = codes.shape
    extent = (0.0, nx * res / 1e3, 0.0, ny * res / 1e3)
    return codes, extent, arr.shape, res


def fig2_native_zoom(outdir: Path) -> None:
    nl_lut, ch_lut = nlcd_lut(), chen_lut()
    n = len(ZOOMS)
    fig, axes = plt.subplots(n, 2, figsize=(11, 4.7 * n))
    for i, (name, lon, lat, why) in enumerate(ZOOMS):
        a, ext_a, shp_a, res_a = _read_native_zoom(
            nlcd_path(2015), nl_lut, lon, lat, ZOOM_HALF_KM, is_chen=False
        )
        b, ext_b, shp_b, res_b = _read_native_zoom(
            find_tif(None, 2015), ch_lut, lon, lat, ZOOM_HALF_KM, is_chen=True
        )
        _show_dom(
            axes[i, 0],
            a,
            ext_a,
            f"{name} — NLCD 2015 @ native {res_a:.0f} m\n{shp_a[0]}×{shp_a[1]} pixels",
        )
        _show_dom(
            axes[i, 1],
            b,
            ext_b,
            f"{name} — Chen2022 2015 @ native {res_b:.0f} m\n{shp_b[0]}×{shp_b[1]} pixels",
        )
        axes[i, 0].set_ylabel(why, fontsize=9)
    fig.legend(
        handles=_legend_handles(),
        loc="lower center",
        ncol=6,
        frameon=False,
        fontsize=10,
        bbox_to_anchor=(0.5, 0.005),
    )
    fig.suptitle(
        "Same 80 km boxes at each product's true native resolution "
        "(30 m vs 1 km — no resampling)",
        fontsize=13,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.975))
    p = outdir / "fig2_native_resolution_zoom.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def fig3_bars_2015(d, outdir: Path) -> None:
    a, ta = _tables.nlcd_areas(d["nlcd"]["2015"])
    b, tb, nod = _tables.chen_areas(d["chen"]["2015_historical"])
    names = [COMMON_NAMES[c] for c in COMMON_CLASSES] + ["No data"]
    av = [a[c] / 1e3 for c in COMMON_CLASSES] + [0.0]
    bv = [b[c] / 1e3 for c in COMMON_CLASSES] + [nod / 1e3]

    x = np.arange(len(names))
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 9), gridspec_kw={"height_ratios": [2, 1]}
    )
    ax.bar(x - 0.2, av, 0.4, label="NLCD 2015 (30 m native)", color="#2c6fbb")
    ax.bar(x + 0.2, bv, 0.4, label="Chen2022 2015 (1 km native)", color="#d9822b")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "CONUS land-cover area by class, 2015 — computed at each product's "
        "native resolution",
        fontsize=12,
    )
    for xi, (u, v) in enumerate(zip(av, bv)):
        if u == 0 and v > 0:
            ax.annotate(
                "no NLCD\ncounterpart", (xi + 0.2, v), ha="center", va="bottom",
                fontsize=7, color="#8a4b00",
            )
        if v == 0 and u > 0:
            ax.annotate(
                "absent from\nChen2022", (xi - 0.2, u), ha="center", va="bottom",
                fontsize=7, color="#8a1a1a",
            )

    diff = [bb - aa for aa, bb in zip(av, bv)]
    cols = ["#c0392b" if v < 0 else "#27ae60" for v in diff]
    ax2.bar(x, diff, 0.6, color=cols)
    ax2.axhline(0, color="0.3", lw=0.8)
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha="right")
    ax2.set_ylabel("Chen − NLCD  [10³ km²]")
    ax2.grid(axis="y", alpha=0.3)
    ax2.set_title("Difference (Chen2022 − NLCD)", fontsize=11)
    fig.tight_layout()
    p = outdir / "fig3_area_by_class_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def fig4_diff_maps(z, outdir: Path) -> None:
    tr = z["display_transform"]
    x0, dx, _, y0, _, dy = tr
    ny, nx = z["nlcd_2015_dom"].shape
    extent = (x0 / 1e3, (x0 + nx * dx) / 1e3, (y0 + ny * dy) / 1e3, y0 / 1e3)

    nf = z["nlcd_2015_frac"]
    cf = z["chen_2015_historical_frac"]
    inside = z["nlcd_2015_valid"] > 0.5

    show = [4, 8, 6, 5, 2, 9]  # Forest, Cropland, Grass, Shrub, Developed, Wetland
    fig, axes = plt.subplots(3, 2, figsize=(13, 12))
    for ax, c in zip(axes.ravel(), show):
        d = (cf[c] - nf[c]) * 100.0
        d = np.where(inside, d, np.nan)
        im = ax.imshow(
            d, cmap="RdBu_r", vmin=-60, vmax=60, extent=extent, interpolation="nearest"
        )
        ax.set_title(f"{COMMON_NAMES[c]}", fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label("Chen − NLCD  [% of cell]", fontsize=8)
        cb.ax.tick_params(labelsize=8)
    fig.suptitle(
        "Where the two products disagree, 2015 — class cover fraction, "
        "Chen2022 minus NLCD\n"
        "(red = Chen has more, blue = NLCD has more; 1200 m comparison grid)",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p = outdir / "fig4_fraction_difference_2015.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def fig5_bars_2020(d, outdir: Path) -> None:
    a, _ = _tables.nlcd_areas(d["nlcd"]["2020"])
    ch = {s: _tables.chen_areas(d["chen"][s]) for s in SSPS}
    names = [COMMON_NAMES[c] for c in COMMON_CLASSES]
    x = np.arange(len(names))
    w = 0.16

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(13, 9.5), gridspec_kw={"height_ratios": [2, 1]}
    )
    ax.bar(
        x - 2 * w,
        [a[c] / 1e3 for c in COMMON_CLASSES],
        w,
        label="NLCD 2020 (30 m native)",
        color="#2c6fbb",
    )
    colors = ["#f6c026", "#d9822b", "#c0392b", "#7d3c98"]
    for i, s in enumerate(SSPS):
        ax.bar(
            x + (i - 1) * w,
            [ch[s][0][c] / 1e3 for c in COMMON_CLASSES],
            w,
            label=f"Chen2022 {_tables.SCENARIO_LABELS[s]} 2020 (1 km)",
            color=colors[i],
        )
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylabel("area  [10³ km²]")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(
        "CONUS land-cover area by class, 2020 — NLCD vs the four Chen2022 SSP "
        "scenarios (native resolution)",
        fontsize=12,
    )

    # The SSPs barely separate 5 years after their common 2015 start: show the
    # spread against the NLCD-Chen gap on the same axis.
    spread = [
        max(ch[s][0][c] for s in SSPS) - min(ch[s][0][c] for s in SSPS)
        for c in COMMON_CLASSES
    ]
    gap = [abs(np.mean([ch[s][0][c] for s in SSPS]) - a[c]) for c in COMMON_CLASSES]
    ax2.bar(x - 0.2, [g / 1e3 for g in gap], 0.4, color="#34495e",
            label="|Chen(mean of SSPs) − NLCD| : product disagreement")
    ax2.bar(x + 0.2, [s / 1e3 for s in spread], 0.4, color="#e67e22",
            label="max − min across the 4 SSPs : scenario spread")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha="right")
    ax2.set_ylabel("area  [10³ km²]")
    ax2.legend(frameon=False, fontsize=9)
    ax2.grid(axis="y", alpha=0.3)
    ax2.set_title(
        "At 2020 the choice of dataset dominates the choice of scenario",
        fontsize=11,
    )
    fig.tight_layout()
    p = outdir / "fig5_area_by_class_2020_ssps.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  {p}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--counts",
        type=Path,
        default=Path("outputs/interim/landcover_native_counts.json"),
    )
    ap.add_argument(
        "--mapdata", type=Path, default=Path("outputs/interim/landcover_map_data.npz")
    )
    ap.add_argument("--outdir", type=Path, default=Path("outputs/figures"))
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    d = json.loads(args.counts.read_text())
    print("figures:")
    fig3_bars_2015(d, args.outdir)
    fig5_bars_2020(d, args.outdir)
    fig2_native_zoom(args.outdir)

    z = np.load(args.mapdata, allow_pickle=False)
    fig1_conus(z, args.outdir)
    fig4_diff_maps(z, args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
