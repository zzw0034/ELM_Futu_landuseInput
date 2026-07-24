#!/usr/bin/env python
"""Plot a US map and overlay a target bounding box.

Needs cartopy, which is NOT in the make_surfdata_pf env. To enable:
    conda install -n make_surfdata_pf -c conda-forge cartopy

Example
-------
$PY scripts/plot_seus_bbox.py --out outputs/figures/seus_bbox.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


DEFAULT_BBOX = (-95.0, 24.0, -74.0, 37.5)  # west, south, east, north
US_EXTENT = (-130.0, -65.0, 23.0, 50.0)  # lower-48 framing


def _plot_with_cartopy(out: Path, bbox: tuple[float, float, float, float]) -> None:
    import cartopy.crs as ccrs  # pyright: ignore[reportMissingImports]
    import cartopy.feature as cfeature  # pyright: ignore[reportMissingImports]

    west, south, east, north = bbox
    fig = plt.figure(figsize=(10, 6), constrained_layout=True)
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent(US_EXTENT, crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f6f6f6")
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#dceefb")
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.7)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.7)
    ax.add_feature(cfeature.STATES.with_scale("50m"), linewidth=0.4, edgecolor="0.5")

    rect = Rectangle(
        (west, south),
        east - west,
        north - south,
        fill=False,
        linewidth=2.0,
        edgecolor="red",
        transform=ccrs.PlateCarree(),
        zorder=10,
    )
    ax.add_patch(rect)

    ax.gridlines(
        draw_labels=True,
        linewidth=0.4,
        color="0.4",
        alpha=0.4,
        linestyle="--",
    )
    ax.set_title(f"US map with bbox [{west}, {south}, {east}, {north}]")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, help="output figure (.png)")
    p.add_argument("--west", type=float, default=DEFAULT_BBOX[0])
    p.add_argument("--south", type=float, default=DEFAULT_BBOX[1])
    p.add_argument("--east", type=float, default=DEFAULT_BBOX[2])
    p.add_argument("--north", type=float, default=DEFAULT_BBOX[3])
    args = p.parse_args(argv)

    bbox = (args.west, args.south, args.east, args.north)
    out = Path(args.out)

    try:
        _plot_with_cartopy(out, bbox)
    except ModuleNotFoundError:
        print("need library cartopy.", file=sys.stderr)
        return 1
    print(f"[plot_us_bbox] wrote {out} (cartopy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
